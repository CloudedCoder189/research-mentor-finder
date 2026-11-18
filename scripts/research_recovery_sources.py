"""Private baseline and anonymous official-source capture for remaining data gaps."""
import argparse,hashlib,json,sqlite3,time,threading
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime,timezone
from urllib.parse import urlparse,urljoin
import requests
from scripts.real_acceptance_snapshot import ROOT,DEST,SOURCE,fingerprint,professors
from services.ai_enrichment import source_hash

EVIDENCE=ROOT/'evidence/research-recovery-2026-10-05'
PRIVATE=ROOT/'test-runtime/research-recovery-20261005'
SNAPSHOT=PRIVATE/'before.db'; STAGE=PRIVATE/'stage.db'; CAPTURES=PRIVATE/'sources'
locks={};lock_guard=threading.Lock();blocked_hosts=set()

def missing(value): return str(value or '').strip().lower() in {'','not publicly available','not available','n/a','none','unknown'}
def university_host(url):
 p=urlparse(url);return p.scheme in {'http','https'} and p.hostname and p.hostname.endswith('.edu') and not p.username and not p.password and (p.port is None or p.port in (80,443))
def origin(url): return '.'.join(urlparse(url).hostname.split('.')[-2:])
def capture(url):
 key=hashlib.sha256(url.encode()).hexdigest()[:20]; metadata=CAPTURES/(key+'.json'); rawpath=CAPTURES/(key+'.html')
 if metadata.exists():return json.loads(metadata.read_text(encoding='utf-8'))
 result={'url':url,'retrieved_at_utc':datetime.now(timezone.utc).isoformat()};taskurl=url
 try:
  if not university_host(url):raise ValueError('Not an official university source')
  host=origin(url)
  with lock_guard: lock=locks.setdefault(host,threading.Semaphore(2))
  with lock:
   if host in blocked_hosts:raise ValueError("University rate-limited; remaining captures deferred")
   time.sleep(.5)
   for hop in range(5):
    if not university_host(taskurl) or origin(taskurl)!=host:raise ValueError('Redirect leaves university source')
    with requests.get(taskurl,timeout=(5,12),allow_redirects=False,stream=True,headers={'User-Agent':'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/150.0.0.0 Safari/537.36','Accept':'text/html'}) as response:
     if response.is_redirect:taskurl=urljoin(taskurl,response.headers['Location']);continue
     result.update(status=response.status_code,response_url=taskurl)
     if response.status_code==429:
      with lock_guard:blocked_hosts.add(host)
     if response.status_code==200:
      if 'html' not in response.headers.get('Content-Type','').lower():raise ValueError('Not HTML')
      chunks=[];size=0
      for chunk in response.iter_content(65536):
       size+=len(chunk)
       if size>3_000_000:raise ValueError('Page exceeds capture limit')
       chunks.append(chunk)
      raw=b''.join(chunks);rawpath.write_bytes(raw); result.update(sha256=hashlib.sha256(raw).hexdigest(),file=rawpath.name)
     break
   else:raise ValueError('Too many redirects')
 except Exception as exc:result['error_type']=type(exc).__name__
 metadata.write_text(json.dumps(result,indent=2),encoding='utf-8');return result

def setup():
 EVIDENCE.mkdir(parents=True,exist_ok=True);CAPTURES.mkdir(parents=True,exist_ok=True)
 if not SNAPSHOT.exists():
  with sqlite3.connect(DEST.as_uri()+'?mode=ro',uri=True) as active,sqlite3.connect(SNAPSHOT) as snapshot:
   active.backup(snapshot);assert snapshot.execute('PRAGMA integrity_check').fetchone()[0]=='ok'
  with sqlite3.connect(SNAPSHOT.as_uri()+'?mode=ro',uri=True) as snapshot,sqlite3.connect(STAGE) as stage:snapshot.backup(stage)
  with sqlite3.connect(SNAPSHOT.as_uri()+'?mode=ro',uri=True) as c:
   before=professors(c);c.row_factory=sqlite3.Row; rows=[dict(r) for r in c.execute('SELECT * FROM professors')]
  gaps=[r for r in rows if missing(r['research_interests'])]; stale=[r for r in rows if r['embedding_source_hash']!=source_hash(r)]
  public=[{k:r[k] for k in ('id','name','university','department','title','profile_url','research_interests','verification_status')} | {'missing_research':r in gaps,'stale_embedding':r in stale} for r in rows if r in gaps or r in stale]
  (EVIDENCE/'baseline.json').write_text(json.dumps({'professors':before,'original_fingerprint':fingerprint(SOURCE),'missing_research':len(gaps),'stale_embeddings':len(stale),'records':public},indent=2),encoding='utf-8')
 return json.loads((EVIDENCE/'baseline.json').read_text(encoding='utf-8'))

def main():
 p=argparse.ArgumentParser();p.add_argument('--fetch',action='store_true');args=p.parse_args();baseline=setup()
 for metadata in CAPTURES.glob('*.json'):
  saved=json.loads(metadata.read_text(encoding='utf-8'))
  if saved.get('status')==429:blocked_hosts.add(origin(saved['url']))
 urls=sorted({r['profile_url'] for r in baseline['records'] if university_host(r['profile_url'])})
 if args.fetch:
  with ThreadPoolExecutor(max_workers=8) as pool:
   for i,result in enumerate(pool.map(capture,urls),1):
    if i%25==0 or i==len(urls):print(json.dumps({'captured':i,'total':len(urls)}),flush=True)
 captures=[json.loads((CAPTURES/(hashlib.sha256(url.encode()).hexdigest()[:20]+'.json')).read_text(encoding='utf-8')) for url in urls if (CAPTURES/(hashlib.sha256(url.encode()).hexdigest()[:20]+'.json')).exists()]
 (EVIDENCE/'source-captures.json').write_text(json.dumps(captures,indent=2),encoding='utf-8')
 print(json.dumps({'missing_research':baseline['missing_research'],'stale_embeddings':baseline['stale_embeddings'],'official_urls':len(urls),'http_200':sum(c.get('status')==200 for c in captures),'paid_calls':0}))

if __name__=='__main__':main()
