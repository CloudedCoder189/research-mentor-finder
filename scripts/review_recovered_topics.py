"""Source-reviewed topic correction and append-only embedding refresh for this same job."""
import hashlib,json,os,sqlite3
from decimal import Decimal
from types import SimpleNamespace
from scripts.research_recovery_sources import EVIDENCE,STAGE
from scripts.real_acceptance_snapshot import SOURCE
from scripts.regenerate_research_recovery import RecoveryBudget
from services.ai_enrichment import build_embedding_text,source_hash,parse_embedding
from services.categorization import CATEGORY_KEYWORDS
from services.taxonomy import infer_taxonomy

TOPICS={79:['Computer Vision'],1240:['Artificial Intelligence','Systems'],1482:['Human-Computer Interaction','Cognitive Science'],1487:['Systems'],1495:['Large Language Models','Artificial Intelligence'],1498:['Computer Vision','Robotics'],1501:['Education Technology','Human-Computer Interaction'],1502:['Education Technology'],1508:['Education Technology'],1524:[],1537:['Climate & Sustainability'],1539:[],1550:['Machine Learning','Artificial Intelligence','Data Science','Climate & Sustainability'],1563:['Systems'],1564:['Human-Computer Interaction'],1566:['Other Computing Research'],1571:['Security & Privacy','Theory'],1588:['Systems','Security & Privacy'],1633:['Machine Learning','Artificial Intelligence','Data Science','Systems'],1634:['Education Technology','Human-Computer Interaction','Graphics'],1635:['Climate & Sustainability'],1648:['Climate & Sustainability'],1649:[],1658:['Climate & Sustainability'],1665:[],1668:[],1675:['Robotics'],1677:[],1680:['Artificial Intelligence','Climate & Sustainability'],1683:[],1687:['Robotics'],1688:['Robotics','Autonomous Systems'],1689:['Climate & Sustainability'],1692:['Optimization'],1694:[],1705:[],1720:[],1732:[],1741:[],1744:[],2107:[],2482:['Machine Learning','Artificial Intelligence','Healthcare AI'],2483:[],2484:['Autonomous Systems'],2485:['Machine Learning','Artificial Intelligence','Computer Vision'],2486:['Security & Privacy'],2487:['Systems'],2489:['Machine Learning','Artificial Intelligence','Theory','Security & Privacy','Autonomous Systems'],2490:['Machine Learning','Artificial Intelligence','Healthcare AI'],2491:[],2492:['Artificial Intelligence','Security & Privacy','Systems']}

def main():
    evidence_path=EVIDENCE/'reviewed-topic-corrections.json'
    assert not evidence_path.exists(), 'Refusing repeated topic correction'
    result=json.loads((EVIDENCE/'ai-results.json').read_text(encoding='utf-8'));assert set(TOPICS)==set(result['research_records'])
    ledger_path=EVIDENCE/'spending-ledger.json';ledger=json.loads(ledger_path.read_text(encoding='utf-8'))
    assert ledger['approved_cap_usd']=='0.50' and all(e['status']=='usage_confirmed' for e in ledger['entries'])
    budget=object.__new__(RecoveryBudget);budget.path=ledger_path;budget.cap=Decimal('0.50');budget.entries=ledger['entries'];budget.blocked=False
    assert str(budget.charged)==result['spent_usd']
    from dotenv import dotenv_values
    from openai import OpenAI
    key=dotenv_values(SOURCE.parents[1]/'.env').get('OPENAI_API_KEY','');assert key
    client=OpenAI(api_key=key,max_retries=0,timeout=45)
    with sqlite3.connect(STAGE) as c:
        c.row_factory=sqlite3.Row;rows={r['id']:dict(r) for r in c.execute('SELECT * FROM professors')}
    changed=[]
    for i,topics in TOPICS.items():
        assert all(t in CATEGORY_KEYWORDS or t=='Other Computing Research' for t in topics)
        row=rows[i];value=', '.join(topics)
        if row['categories']!=value or row['ai_categories']!=value:
            changed.append(row|{'categories':value,'ai_categories':value})
    evidence={'scope':'51 recovered records only; all topic assignments reviewed against their accepted source excerpts','old_spend_usd':str(budget.charged),'initial_ledger_sha256':hashlib.sha256(ledger_path.read_bytes()).hexdigest(),'decisions':[{'id':r['id'],'name':r['name'],'source_text':r['research_interests'],'old_rule_topics':rows[r['id']]['categories'],'old_ai_topics':rows[r['id']]['ai_categories'],'reviewed_topics':r['ai_categories'],'reason':'Omit unsupported category assignments; an empty list preserves research outside the computing-focused category catalog'} for r in changed]}
    evidence_path.write_text(json.dumps(evidence,indent=2),encoding='utf-8')
    try:
        for start in range(0,len(changed),16):
            batch=changed[start:start+16]
            response=budget.request(client.embeddings.create,{'model':'text-embedding-3-small','input':[build_embedding_text(r) for r in batch]})
            vectors=sorted(response.data,key=lambda r:r.index);assert len(vectors)==len(batch)
            with sqlite3.connect(STAGE) as c:
                for row,item in zip(batch,vectors):
                    vector=list(map(float,item.embedding));assert len(vector)==1536
                    taxonomy=infer_taxonomy(university=row['university'],department=row['department'],categories=row['categories'],ai_categories=row['ai_categories'])
                    c.execute('UPDATE professors SET categories=?,ai_categories=?,embedding_json=?,embedding_source_hash=?,school_or_college=?,discipline=?,field=?,subfield=? WHERE id=?',(row['categories'],row['ai_categories'],json.dumps(vector,separators=(',',':')),source_hash(row),*taxonomy,row['id']))
        with sqlite3.connect(STAGE) as c:
            from scripts.real_acceptance_snapshot import professors
            result['professors']=professors(c);c.row_factory=sqlite3.Row
            assert all(r['embedding_source_hash']==source_hash(dict(r)) for r in c.execute('SELECT * FROM professors'))
        result.update(spent_usd=str(budget.charged),source_reviewed_topic_corrections=len(changed))
        (EVIDENCE/'ai-results.json').write_text(json.dumps(result,indent=2),encoding='utf-8')
        print(json.dumps({'topic_corrections':len(changed),'total_job_spend_usd':str(budget.charged)}))
    finally:client.close()

if __name__=='__main__':main()
