"""Promote tested professor rows only; preserve all private runtime tables."""
import argparse
import json
import math
import sqlite3
from scripts.real_acceptance_snapshot import ROOT, SOURCE, DEST, EVIDENCE as BASELINE, fingerprint, professors
from scripts.stage_expanded_ucla_repairs import STAGE, table_hashes
from services.ai_enrichment import source_hash, parse_embedding

EVIDENCE = ROOT / 'evidence/ucla-expanded-repair-2026-10-05'
BACKUP = ROOT / 'test-runtime/acceptance-before-ucla-expanded-20261005.db'
ALLOWED = set('name department title research_interests website_url profile_url data_source_url categories department_category school_or_college discipline field subfield ai_categories ai_summary embedding_json embedding_model embedding_source_hash ai_enriched_at verification_status verification_issues verified_at website_status website_issue website_checked_at website_final_url updated_at'.split())

def main():
    parser=argparse.ArgumentParser(); parser.add_argument('--apply', action='store_true'); args=parser.parse_args()
    baseline=json.loads((BASELINE/'snapshot.json').read_text(encoding='utf-8'))
    assert fingerprint(SOURCE)==baseline['source_before'], 'Original database changed'
    ai=json.loads((EVIDENCE/'ai-regeneration-results.json').read_text(encoding='utf-8'))
    ids=set(ai['records']); assert len(ids)==51 and ai['status']=='completed'
    browser=json.loads((EVIDENCE/'browser/results.json').read_text(encoding='utf-8'))
    assert len(browser['results'])==11 and all(r['passed'] for r in browser['results'])
    with sqlite3.connect(DEST.as_uri()+'?mode=ro', uri=True) as active, sqlite3.connect(STAGE.as_uri()+'?mode=ro', uri=True) as stage:
        assert professors(active)==baseline['professors'], 'Active professor rows departed from approved baseline'
        active.row_factory=sqlite3.Row; stage.row_factory=sqlite3.Row
        old={r['id']:dict(r) for r in active.execute('SELECT * FROM professors ORDER BY id')}
        new={r['id']:dict(r) for r in stage.execute('SELECT * FROM professors ORDER BY id')}
        assert old.keys()==new.keys() and len(new)==2063
        changes={}
        for record_id in old:
            fields={k:new[record_id][k] for k in old[record_id] if old[record_id][k]!=new[record_id][k]}
            if fields:
                assert record_id in ids and set(fields)<=ALLOWED, 'Unexpected row or column change'
                changes[record_id]=fields
        assert set(changes)==ids
        for record_id in ids:
            row=new[record_id]; vector=parse_embedding(row['embedding_json'])
            assert vector and len(vector)==1536 and all(math.isfinite(v) for v in vector)
            assert source_hash(row)==row['embedding_source_hash']
            assert row['verification_status'] in ('Verified','Review')
        active.row_factory=None; stage.row_factory=None
        expected=professors(stage)
    if not args.apply:
        print(json.dumps({'ready':True,'records':len(changes),'professor_columns_only':True,'stage':expected})); return
    with sqlite3.connect(DEST) as active:
        assert professors(active)==baseline['professors']
        private_before=table_hashes(active)
        if BACKUP.exists():
            with sqlite3.connect(BACKUP.as_uri()+'?mode=ro', uri=True) as backup:
                assert professors(backup)==baseline['professors']
                assert table_hashes(backup)==private_before, 'Existing backup differs from active private tables'
                assert backup.execute('PRAGMA integrity_check').fetchone()[0]=='ok'
        else:
            with sqlite3.connect(BACKUP) as backup:
                active.backup(backup)
                assert backup.execute('PRAGMA integrity_check').fetchone()[0]=='ok'
        try:
            active.execute('BEGIN IMMEDIATE')
            assert professors(active)==baseline['professors']
            for record_id, fields in changes.items():
                active.execute('UPDATE professors SET '+','.join('"'+k+'"=?' for k in fields)+' WHERE id=?', (*fields.values(),record_id))
            assert professors(active)==expected
            active.execute("INSERT INTO app_migrations(migration_key,applied_at,details) VALUES('professors_data_revision',CURRENT_TIMESTAMP,'1') ON CONFLICT(migration_key) DO UPDATE SET applied_at=CURRENT_TIMESTAMP,details=CAST(CAST(details AS INTEGER)+1 AS TEXT)")
            private_after=table_hashes(active)
            assert {k:v for k,v in private_before.items() if k!='app_migrations'}=={k:v for k,v in private_after.items() if k!='app_migrations'}
            assert active.execute('PRAGMA integrity_check').fetchone()[0]=='ok'
            active.commit()
        except Exception:
            active.rollback(); raise
        assert professors(active)==expected
    assert fingerprint(SOURCE)==baseline['source_before']
    report={'status':'activated','records':sorted(ids),'professors':expected,'private_tables_unchanged':True,'migration_exception':'professors_data_revision increment only','original_fingerprint_unchanged':True,'rollback_backup_relative_path':str(BACKUP.relative_to(ROOT)),'paid_calls':0}
    (EVIDENCE/'activation.json').write_text(json.dumps(report,indent=2),encoding='utf-8')
    print(json.dumps(report))

if __name__=='__main__': main()
