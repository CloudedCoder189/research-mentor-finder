"""Read-only structural audit of public researcher columns. No app imports/API calls."""
import ast
import hashlib
import json
import math
import re
import sqlite3
from collections import Counter, defaultdict
from urllib.parse import urlsplit
from typing import Any

from scripts.real_acceptance_snapshot import ROOT, SOURCE, DEST, fingerprint

OUTPUT = ROOT / 'evidence/data-audit-2026-10-04'
FIELDS = ('id name university department department_category title research_interests '
          'profile_url website_url data_source_url categories ai_categories ai_summary '
          'embedding_json embedding_model embedding_source_hash verification_status '
          'verification_issues website_status opportunity_level opportunity_signals '
          'opportunity_source_url source_type').split()
MISSING = {'', 'not publicly available', 'not available', 'n/a', 'none', 'unknown'}
TITLE_NOISE = re.compile(r'\b(?:expert directory|skip to content|privacy policy|cookie policy|'
                        r'click here|read more|learn more|site navigation)\b', re.I)
TITLE_PROSE = re.compile(r'\b(?:his research|her research|research interests|research focuses|'
                        r'he is|she is|focuses on)\b', re.I)


def absent(value):
    return str(value or '').strip().lower() in MISSING


def normalized(value):
    return ' '.join(str(value or '').casefold().split())


def document_hash(row):
    pairs = [('Department', 'department'), ('Title', 'title'),
             ('Published research interests', 'research_interests'),
             ('Rule-based topics', 'categories'), ('AI topics', 'ai_categories'),
             ('Research summary', 'ai_summary')]
    text = '\n'.join(f'{label}: {row.get(key, "")}'.strip() for label, key in pairs)[:12000]
    return hashlib.sha256(text.encode('utf-8')).hexdigest()


def run():
    before = fingerprint(SOURCE)
    with sqlite3.connect(DEST.as_uri() + '?mode=ro', uri=True) as db:
        db.execute('PRAGMA query_only=ON')
        db.row_factory = sqlite3.Row
        rows = [dict(row) for row in db.execute('SELECT ' + ','.join(FIELDS) + ' FROM professors ORDER BY id')]
    # Execute only the two pure academic-text hash functions, avoiding the app's
    # imports/configuration. Reject audit drift if that implementation changes.
    parsed = ast.parse((ROOT / 'services/ai_enrichment.py').read_text(encoding='utf-8'))
    pure_functions = [node for node in parsed.body if isinstance(node, ast.FunctionDef)
                      and node.name in ('build_embedding_text', 'source_hash')]
    scope = {'hashlib': hashlib, 'Any': Any}
    exec(compile(ast.Module(body=pure_functions, type_ignores=[]), '<pure academic hash functions>', 'exec'), scope)
    assert all(document_hash(row) == scope['source_hash'](row) for row in rows)
    flags = []
    counts = Counter()
    dimensions = Counter()
    duplicates = defaultdict(list)
    urls = defaultdict(list)

    def flag(row, rule, detail):
        counts[rule] += 1
        flags.append({'id': row['id'], 'name': row['name'], 'university': row['university'],
                      'rule': rule, 'detail': detail, 'profile_url': row['profile_url'],
                      'data_source_url': row['data_source_url']})

    for row in rows:
        for key in ['name', 'university', 'title', 'research_interests', 'profile_url',
                    'data_source_url', 'ai_summary', 'categories', 'ai_categories']:
            if absent(row[key]):
                counts['missing_' + key] += 1
        title = row['title']
        if TITLE_NOISE.search(title):
            flag(row, 'title_navigation_noise', title)
        if TITLE_PROSE.search(title):
            flag(row, 'title_prose_candidate', title)
        if len(title) > 180:
            flag(row, 'title_long_candidate', title)
        duplicates[(normalized(row['name']), normalized(row['university']))].append(row['id'])
        for key in ['profile_url', 'website_url', 'data_source_url', 'opportunity_source_url']:
            if absent(row[key]):
                continue
            parsed = urlsplit(row[key])
            if parsed.scheme not in ('http', 'https') or not parsed.netloc:
                flag(row, 'malformed_' + key, row[key])
            if key == 'profile_url':
                urls[row[key].rstrip('/').casefold()].append(row['id'])
        try:
            vector = json.loads(row['embedding_json'])
            if (not isinstance(vector, list) or not vector or
                    not all(isinstance(v, (int, float)) and not isinstance(v, bool) and math.isfinite(v) for v in vector)):
                raise ValueError('Invalid vector')
            dimensions[str(len(vector))] += 1
        except (ValueError, TypeError):
            flag(row, 'invalid_or_missing_embedding', 'Embedding is not a nonempty finite numeric array')
        if row['embedding_source_hash'] != document_hash(row):
            flag(row, 'embedding_document_hash_mismatch', 'Stored embedding source hash differs from current academic text')
        if row['verification_status'] == 'Verified' and absent(row['profile_url']):
            flag(row, 'verified_without_profile_url', 'Verified record has no profile URL')
        if row['opportunity_level'] in ('Strong', 'Moderate') and absent(row['opportunity_source_url']):
            flag(row, 'opportunity_without_source_url', row['opportunity_level'])

    # Explicit source-check candidates: known risky records plus one from each
    # stored verification status, then different institutions. Purposive, not random.
    selected = []
    def select(row):
        if row and row['id'] not in {r['id'] for r in selected}:
            selected.append(row)
    select(next((r for r in rows if r['id'] == 1126), None))
    select(next((r for r in rows if 'aditya grover' in normalized(r['name'])), None))
    for item in flags:
        if item['rule'] in ('title_navigation_noise', 'title_prose_candidate', 'embedding_document_hash_mismatch'):
            select(next(r for r in rows if r['id'] == item['id']))
        if len(selected) >= 6:
            break
    for status in ('Verified', 'Review', 'Failed'):
        select(next((r for r in rows if r['verification_status'] == status and not absent(r['profile_url'])), None))
    for row in rows:
        if row['university'] not in {r['university'] for r in selected} and not absent(row['profile_url']):
            select(row)
        if len(selected) >= 10:
            break
    sample_fields = ('id name university title department department_category research_interests '
                     'categories ai_categories ai_summary profile_url data_source_url verification_status '
                     'verification_issues opportunity_level opportunity_signals opportunity_source_url').split()
    after = fingerprint(SOURCE)
    assert before == after
    OUTPUT.mkdir(parents=True, exist_ok=True)
    result = {'rows': len(rows), 'verification_statuses': dict(Counter(r['verification_status'] for r in rows)),
              'website_statuses': dict(Counter(r['website_status'] for r in rows)),
              'opportunity_levels': dict(Counter(r['opportunity_level'] for r in rows)),
              'universities': len({r['university'] for r in rows}),
              'embedding_models': dict(Counter(r['embedding_model'] for r in rows)),
              'embedding_dimensions': dict(dimensions), 'counts': dict(counts),
              'hash_calculation_matches_exact_app_functions': True,
              'normalized_name_university_duplicate_groups': [ids for ids in duplicates.values() if len(ids) > 1],
              'shared_profile_url_groups': [ids for ids in urls.values() if len(ids) > 1],
              'flags': flags, 'source_sample': [{k: r[k] for k in sample_fields} for r in selected],
              'original_db_unchanged': before == after,
              'database_opened_read_only': True, 'database_writes': 0, 'provider_calls': 0,
              'limitations': ['Structural checks are not factual verification.',
                              'Long/prose-like titles and shared URLs require review, not automatic deletion.',
                              'Source-check sample is purposive and cannot establish an overall accuracy rate.']}
    (OUTPUT / 'structural-audit.json').write_text(json.dumps(result, indent=2), encoding='utf-8')
    print(json.dumps({k:result[k] for k in ['rows','universities','verification_statuses','website_statuses','embedding_dimensions','counts','original_db_unchanged']},indent=2))


if __name__ == '__main__':
    run()
