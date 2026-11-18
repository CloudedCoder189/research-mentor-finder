import hashlib,json
from scripts.research_recovery_sources import EVIDENCE,CAPTURES,university_host
from services.research_evidence import extract_research_evidence
rows=json.loads((EVIDENCE/'baseline.json').read_text())['records'];results=[]
for row in rows:
 if not row['missing_research']:continue
 key=hashlib.sha256(row['profile_url'].encode()).hexdigest()[:20];meta=CAPTURES/(key+'.json')
 result={k:row[k] for k in ('id','name','university','profile_url')}
 if not meta.exists():result.update(status='source_not_yet_captured' if university_host(row['profile_url']) else 'no_official_profile_url',text='')
 else:
  metadata=json.loads(meta.read_text());result.update(http_status=metadata.get('status'),source_sha256=metadata.get('sha256'))
  if metadata.get('status')==200 and metadata.get('file'):
   raw=(CAPTURES/metadata['file']).read_bytes();assert hashlib.sha256(raw).hexdigest()==metadata['sha256']
   result.update(extract_research_evidence(raw.decode('utf-8',errors='replace'),row['name']))
  else:result.update(status='source_unavailable',text='')
 results.append(result)
(EVIDENCE/'research-candidates.json').write_text(json.dumps(results,indent=2),encoding='utf-8')
print(json.dumps({'assessed':len(results),'candidates':sum(bool(r['text']) for r in results),'counts':{s:sum(r['status']==s for r in results) for s in sorted(set(r['status'] for r in results))}}))
for r in results:
 if r['text']:print(json.dumps(r))
