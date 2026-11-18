import json
import sqlite3
from contextlib import closing

import pytest

import database
from api.retention import initialize
from api.schemas.researcher import profile_dto
from deploy.pilot.repair_links import PLAN, apply_reviewed_links, load_plan


@pytest.fixture
def batch(tmp_path, monkeypatch):
    path = tmp_path / 'runtime.db'
    monkeypatch.setattr(database, 'DB_PATH', path)
    monkeypatch.setenv('RETENTION_ROOT', str(tmp_path / 'managed'))
    monkeypatch.setenv('RETENTION_KEY_FILE', str(tmp_path / 'key'))
    database.initialize_database(run_maintenance=False)
    item = load_plan()['records'][0]
    database.upsert_professors([{'name': item['name'], 'university': item['university'], 'email': 'academic@example.test',
                               **{k: v['before'] for k, v in item['changes'].items()}}])
    with closing(sqlite3.connect(path)) as c:
        c.execute('UPDATE professors SET id=?,embedding_json=?,ai_summary=?',
                  (item['id'], '[0.1,0.2]', 'Synthetic summary to preserve'))
        c.commit()
    database.upsert_user(user_id='google:synthetic', email='synthetic@example.test')
    store = initialize()
    store.maintain()
    return path, store, item


def snapshot(path):
    with closing(sqlite3.connect(path)) as c:
        return {name: c.execute('SELECT * FROM "'+name+'" ORDER BY rowid').fetchall()
                for (name,) in c.execute("SELECT name FROM sqlite_master WHERE type='table'")}


def test_repair_preserves_private_data_and_embedding_with_encrypted_rollback(batch):
    path, store, item = batch
    before = snapshot(path)
    report = apply_reviewed_links(path)
    assert report['updated_records'] == 1 and report['fresh_encrypted_backup']
    after = snapshot(path)
    for table in before.keys() - {'professors', 'app_migrations'}:
        assert after[table] == before[table]
    with closing(sqlite3.connect(path)) as c:
        c.row_factory = sqlite3.Row
        row = dict(c.execute('SELECT * FROM professors').fetchone())
        assert row['embedding_json'] == '[0.1,0.2]'
        assert row['ai_summary'] == 'Synthetic summary to preserve'
        for field, change in item['changes'].items():
            assert row[field] == change['after']
    with closing(store.connect()) as c:
        backups = c.execute('SELECT name FROM backups ORDER BY created_at DESC').fetchall()
    assert len(backups) == 2
    encrypted = (store.root/'backups'/backups[0][0]).read_bytes()
    with closing(sqlite3.connect(':memory:')) as restored:
        restored.deserialize(store.cipher.decrypt(encrypted))
        assert restored.execute('SELECT * FROM professors ORDER BY rowid').fetchall() == before['professors']
        assert restored.execute('SELECT * FROM users ORDER BY rowid').fetchall() == before['users']


def test_repeat_is_noop_without_another_backup(batch):
    path, _, _ = batch
    apply_reviewed_links(path)
    before = snapshot(path)
    def forbidden():
        raise AssertionError('Repeated repair must not create another backup')
    assert apply_reviewed_links(path, backup=forbidden)['idempotent']
    assert snapshot(path) == before


def test_backup_failure_leaves_every_table_unchanged(batch):
    path, _, _ = batch
    before = snapshot(path)
    with pytest.raises(ValueError, match='backup'):
        apply_reviewed_links(path, backup=lambda: False)
    assert snapshot(path) == before


@pytest.mark.parametrize('change', ["name='Another person'", "website_url='https://newly-corrected.example.test/'"])
def test_changed_identity_or_link_refuses_before_backup(batch, change):
    path, _, _ = batch
    with closing(sqlite3.connect(path)) as c:
        c.execute('UPDATE professors SET '+change); c.commit()
    before = snapshot(path)
    with pytest.raises(ValueError, match='changed'):
        apply_reviewed_links(path, backup=lambda: pytest.fail('Backup should not run'))
    assert snapshot(path) == before


def test_update_failure_rolls_back_all_tables(batch):
    path, _, _ = batch
    with closing(sqlite3.connect(path)) as c:
        c.execute("CREATE TRIGGER reject_repair BEFORE UPDATE ON professors BEGIN SELECT RAISE(ABORT,'synthetic failure'); END")
        c.commit()
    before = snapshot(path)
    with pytest.raises(sqlite3.IntegrityError):
        apply_reviewed_links(path)
    assert snapshot(path) == before


def test_different_database_refused(batch, tmp_path):
    path, _, _ = batch
    other = tmp_path/'other.db'; other.write_bytes(path.read_bytes())
    with pytest.raises(ValueError, match='identity'):
        apply_reviewed_links(other)


@pytest.mark.parametrize('value', [None, '', ' Not publicly available '])
def test_absent_link_placeholders_never_become_clickable_urls(value):
    dto = profile_dto({'id': 1, 'name': 'Synthetic researcher', 'university': 'Test University',
                       **{k: value for k in ('website_url','profile_url','data_source_url','opportunity_source_url')}})
    assert dto.website_url == dto.profile_url == dto.researcher.data_source_url == dto.opportunity_source_url == ''


def test_repair_plan_cannot_change_academic_or_private_fields(tmp_path):
    plan = load_plan()
    plan['records'][0]['changes']['title'] = {'before':'Old title','after':'New title'}
    file = tmp_path/'unsafe.json'; file.write_text(json.dumps(plan), encoding='utf-8')
    with pytest.raises(ValueError, match='Only reviewed URL'):
        load_plan(file)


def test_legacy_fixes_do_not_reintroduce_dead_tantalo_links():
    fix = database.KNOWN_RECORD_FIXES[('University of California, Santa Cruz', 'Patrick Tantalo')]
    assert 'profile_url' not in fix and 'website_url' not in fix
