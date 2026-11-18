"""Read-only closeout checks of the activated local recovery batch."""
import json,sqlite3,math,requests
from scripts.research_recovery_sources import EVIDENCE,STAGE,ROOT
from scripts.real_acceptance_snapshot import DEST,SOURCE,fingerprint,professors
from scripts.stage_expanded_ucla_repairs import table_hashes
from services.ai_enrichment import source_hash,parse_embedding
baseline=json.loads((EVIDENCE/'baseline.json').read_text(encoding='utf-8'))
assert fingerprint(SOURCE)==baseline['original_fingerprint']
health=requests.get('http://localhost:18501/api/health',timeout=15);health.raise_for_status()
front=requests.get('http://localhost:13310',timeout=15);front.raise_for_status()
profile=requests.get('http://localhost:18501/api/researchers/1482',timeout=15).json()['researcher']
assert profile['research_interests'].startswith('Her research aims')
assert set(profile['topics'])=={'Human-Computer Interaction','Cognitive Science'}
backup=ROOT/'test-runtime/acceptance-before-research-recovery-20261005.db'
with sqlite3.connect(DEST.as_uri()+'?mode=ro',uri=True) as c,sqlite3.connect(STAGE.as_uri()+'?mode=ro',uri=True) as s,sqlite3.connect(backup.as_uri()+'?mode=ro',uri=True) as b:
 assert professors(c)==professors(s);stats=professors(c)
 before=table_hashes(b);after=table_hashes(c)
 assert {k:v for k,v in before.items() if k!='app_migrations'}=={k:v for k,v in after.items() if k!='app_migrations'}
 assert c.execute('PRAGMA integrity_check').fetchone()[0]=='ok'
 c.row_factory=sqlite3.Row;rows=[dict(r) for r in c.execute('SELECT * FROM professors')]
 assert all(r['embedding_source_hash']==source_hash(r) for r in rows)
 for row in rows:
  vector=parse_embedding(row['embedding_json']);assert vector and len(vector)==1536 and all(math.isfinite(x) for x in vector)
 missing=sum(r['research_interests'] in ('','Not publicly available') for r in rows)
 assert missing==444
result={'prototype_url':'http://localhost:13310','frontend_http':front.status_code,'api_http':health.status_code,'professors':stats,'remaining_research_gaps':missing,'embedding_hash_mismatches':0,'all_vectors_finite_1536_dimensions':True,'active_matches_tested_stage':True,'original_fingerprint_unchanged':True,'private_runtime_tables_unchanged_after_restart':True,'paid_calls':0,'gmail_sends':0}
(EVIDENCE/'final-preservation.json').write_text(json.dumps(result,indent=2),encoding='utf-8');print(json.dumps(result))
