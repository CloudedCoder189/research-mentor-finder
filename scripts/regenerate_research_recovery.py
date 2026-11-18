"""Regenerate reviewed research text and 61 stale vectors under the approved $0.50 cap."""
import argparse,hashlib,json,math,os,sqlite3
from decimal import Decimal
from types import SimpleNamespace
from scripts.research_recovery_sources import ROOT,STAGE,SNAPSHOT,EVIDENCE,CAPTURES
from scripts.real_acceptance_snapshot import SOURCE,professors
from scripts.regenerate_reviewed_ai import Budget,BudgetError,EMBEDDING_RATE,TEXT_INPUT_RATE,TEXT_OUTPUT_RATE
from services import ai_enrichment as ai
from services.categorization import categorize_with_keywords,categories_to_text
from services.taxonomy import infer_taxonomy
from services.research_evidence import extract_research_evidence

class RecoveryBudget(Budget):
    def __init__(self,path):
        self.path=path;self.cap=Decimal('0.50');self.entries=[];self.blocked=False
        if path.exists():raise BudgetError('Existing recovery ledger: refusing to reset spending')
        self.write()

def main():
    p=argparse.ArgumentParser();p.add_argument('--run',action='store_true');args=p.parse_args()
    reviewed=json.loads((EVIDENCE/'reviewed-research.json').read_text(encoding='utf-8'))
    baseline=json.loads((EVIDENCE/'baseline.json').read_text(encoding='utf-8'))
    research_ids={r['id'] for r in reviewed['accepted']};stale_ids={r['id'] for r in baseline['records'] if r['stale_embedding']};allowed_ids=research_ids|stale_ids
    with sqlite3.connect(STAGE) as c:
        assert professors(c)==baseline['professors'], 'Stage changed; checkpoint review required'
        c.row_factory=sqlite3.Row;records={r['id']:dict(r) for r in c.execute('SELECT * FROM professors')}
    planned=[]
    for review in reviewed['accepted']:
        capture=CAPTURES/(hashlib.sha256(review['source_url'].encode()).hexdigest()[:20]+'.html')
        raw=capture.read_bytes();assert hashlib.sha256(raw).hexdigest()==review['source_sha256']
        evidence=extract_research_evidence(raw.decode('utf-8',errors='replace'),review['name'])
        assert review['new_value'] in evidence['text']
        row=records[review['id']]
        assert row['name']==review['name'] and row['research_interests']==review['old_value']
        planned.append(row|{'research_interests':review['new_value'],'categories':categories_to_text(categorize_with_keywords(review['new_value'])),'ai_summary':'','ai_categories':'','embedding_json':''})
    maximum=Decimal(len(planned))*Decimal('0.008')+Decimal(sum(len(ai.build_embedding_text(row).encode()) for row in planned+[records[i] for i in stale_ids-research_ids]))*EMBEDDING_RATE
    assert maximum<Decimal('0.50')
    projection={'research_records':len(planned),'stale_embedding_records':len(stale_ids),'unique_records':len(allowed_ids),'approved_cap_usd':'0.50','conservative_estimate_usd':str(maximum),'request_reservations':'Exact UTF-8 input bound and max output reserved before each request','models':['gpt-5-mini','text-embedding-3-small']}
    (EVIDENCE/'ai-projection.json').write_text(json.dumps(projection,indent=2),encoding='utf-8')
    if not args.run:print(json.dumps(projection));return
    from dotenv import dotenv_values
    key=dotenv_values(SOURCE.parents[1]/'.env').get('OPENAI_API_KEY','')
    if not key:raise SystemExit('No key available; no provider calls')
    from openai import OpenAI
    os.environ.update(OPENAI_API_KEY=key,OPENAI_TEXT_MODEL='gpt-5-mini',OPENAI_EMBEDDING_MODEL='text-embedding-3-small',PROFESSOR_DB_PATH=str(STAGE))
    budget=RecoveryBudget(EVIDENCE/'spending-ledger.json');client=OpenAI(api_key=key,max_retries=0,timeout=45)
    wrapper=SimpleNamespace(responses=SimpleNamespace(create=lambda **kw:budget.request(client.responses.create,kw)),embeddings=SimpleNamespace(create=lambda **kw:budget.request(client.embeddings.create,kw)))
    ai._new_client=lambda:wrapper
    with sqlite3.connect(STAGE) as c:
        backup=STAGE.with_name('before-ai.db')
        assert not backup.exists()
        with sqlite3.connect(backup) as b:c.backup(b)
        for row in planned:
            c.execute("UPDATE professors SET research_interests=?,categories=?,ai_summary='',ai_categories='',embedding_json='',embedding_source_hash='',embedding_model='',ai_enriched_at='Not publicly available' WHERE id=?",(row['research_interests'],row['categories'],row['id']))
    phase='research'
    def save(rows):
        with sqlite3.connect(STAGE) as c:
            for row in rows:
                assert row['id'] in allowed_ids
                if phase=='research':
                    assert row['id'] in research_ids
                    taxonomy=infer_taxonomy(university=row['university'],department=row['department'],categories=row['categories'],ai_categories=row['ai_categories'])
                    c.execute('UPDATE professors SET ai_summary=?,ai_categories=?,embedding_json=?,embedding_model=?,embedding_source_hash=?,ai_enriched_at=?,school_or_college=?,discipline=?,field=?,subfield=? WHERE id=?',(row['ai_summary'],row['ai_categories'],row['embedding_json'],row['embedding_model'],row['embedding_source_hash'],row['ai_enriched_at'],*taxonomy,row['id']))
                else:
                    original=records[row['id']]
                    assert row['ai_summary']==original['ai_summary'] and row['ai_categories']==original['ai_categories'], 'Embedding-only metadata changed'
                    c.execute('UPDATE professors SET embedding_json=?,embedding_model=?,embedding_source_hash=?,ai_enriched_at=? WHERE id=?',(row['embedding_json'],row['embedding_model'],row['embedding_source_hash'],row['ai_enriched_at'],row['id']))
        return len(rows)
    ai.update_ai_enrichment=save
    try:
        research=ai.enrich_records_with_openai(planned,only_missing=False,progress_callback=lambda msg:print(msg,flush=True))
        assert research['saved']==research['text_enriched']==len(planned) and not research['text_errors']
        phase='embedding'
        stale=ai.enrich_records_with_openai([records[i] for i in sorted(stale_ids-research_ids)],only_missing=False,generate_topics_and_summaries=False,progress_callback=lambda msg:print(msg,flush=True))
        assert stale['saved']==len(stale_ids-research_ids)
        with sqlite3.connect(STAGE) as c:
            assert c.execute('PRAGMA integrity_check').fetchone()[0]=='ok';stats=professors(c);c.row_factory=sqlite3.Row
            after={r['id']:dict(r) for r in c.execute('SELECT * FROM professors')}
            for i,row in after.items():
                if i not in allowed_ids:assert row==records[i]
                if i in allowed_ids:
                    v=ai.parse_embedding(row['embedding_json']);assert v and len(v)==1536 and all(math.isfinite(x) for x in v)
                    assert row['embedding_source_hash']==ai.source_hash(row)
            assert all(r['embedding_source_hash']==ai.source_hash(r) for r in after.values())
        result={'status':'completed','records':sorted(allowed_ids),'research_records':sorted(research_ids),'stale_embedding_records':sorted(stale_ids),'research_result':research,'embedding_only_result':stale,'spent_usd':str(budget.charged),'cap_usd':'0.50','professors':stats,'all_embedding_hashes_current':True,'unrelated_professor_rows_unchanged':True,'verification_statuses':'Preserved; this is research-field repair, not a new comprehensive verification audit'}
        (EVIDENCE/'ai-results.json').write_text(json.dumps(result,indent=2),encoding='utf-8');print(json.dumps({'research_recovered':len(research_ids),'stale_refreshed':len(stale_ids),'spent_usd':str(budget.charged)}))
    except Exception as exc:
        (EVIDENCE/'ai-stop.json').write_text(json.dumps({'error_type':type(exc).__name__,'reserved_or_spent_usd':str(budget.charged),'automatic_retries':0}),encoding='utf-8');raise
    finally:client.close();os.environ.pop('OPENAI_API_KEY',None)

if __name__=='__main__':main()
