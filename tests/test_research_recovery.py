import json
import pytest
from services.ai_enrichment import source_hash
from services.search import rank_professors
from services.research_evidence import extract_research_evidence

@pytest.mark.parametrize('stored',['','outdated'])
def test_stale_vectors_do_not_influence_semantic_ranking(stored):
 row={'name':'Researcher','department':'Computer Science','title':'Professor','research_interests':'machine learning','categories':'Machine Learning','embedding_json':json.dumps([1,0]),'embedding_source_hash':stored}
 result=rank_professors([row],'machine learning',query_embedding=[1,0])[0]
 assert result['search_mode']=='Keyword' and result['semantic_score']==0
 row['embedding_source_hash']=source_hash(row)
 assert rank_professors([row],'machine learning',query_embedding=[1,0])[0]['search_mode']=='AI semantic + keyword'
 row['research_interests']='machine learning for health'
 assert rank_professors([row],'machine learning',query_embedding=[1,0])[0]['search_mode']=='Keyword'

def test_profile_research_scoped_to_person_and_section():
 html='<nav><h2>Research</h2><p>Navigation research on chemistry.</p></nav><main><h1>Ada Example</h1><h2>Research Interests</h2><ul><li>Machine learning</li><li>Computer vision</li></ul><h2>Publications</h2><p>Not interests</p></main>'
 result=extract_research_evidence(html,'Ada Example')
 assert result['text']=='Machine learning; Computer vision'
 assert extract_research_evidence(html,'Other Person')['text']==''

def test_directory_identity_does_not_authorize_other_person_interests():
 html='<main><h1>Faculty Directory</h1><h2>Ada Example</h2><p>No research</p><h2>Other Person</h2><h3>Research Interests</h3><p>Machine learning</p></main>'
 assert extract_research_evidence(html,'Ada Example')['text']==''

def test_empty_research_parent_does_not_collect_other_sections():
 html='<main><h1>Ada Example</h1><h2>Research</h2><h3>Research Interests</h3><h3>Research Groups</h3><p>Machine learning laboratory</p></main>'
 assert extract_research_evidence(html,'Ada Example')['text']==''

def test_biography_only_recovers_supported_research_sentence():
 html='<main><h1>Ada Example</h1><h2>Biography</h2><p>Ada joined in 2024. Her research focuses on trustworthy machine learning. She teaches two courses.</p></main>'
 result=extract_research_evidence(html,'Ada Example')
 assert result['text']=='Her research focuses on trustworthy machine learning.'

def test_footer_outside_main_cannot_supply_research():
 html='<main><h1>Ada Example</h1><h2>Research Interests</h2></main><footer><p>Machine learning and robotics</p></footer>'
 assert extract_research_evidence(html,'Ada Example')['text']==''

def test_plain_research_text_and_navigation_siblings_are_bounded():
 html='<main><h1>Ada Example</h1><h2>Research Areas</h2><div>Computer vision and robotic learning</div><p>Back to Top</p><h2>Contact</h2><p>ada@example.edu</p></main>'
 assert extract_research_evidence(html,'Ada Example')['text']=='Computer vision and robotic learning'

def test_university_header_suffix_and_duplicate_name_subheading():
 html='<main><h1>Ada Example: Faculty Home Page</h1><h2>Ada Example</h2><h2>Research Interests</h2><p>Computer vision and robotic learning</p></main>'
 assert extract_research_evidence(html,'Ada Example')['text']=='Computer vision and robotic learning'

def test_research_funding_alone_does_not_supply_topics():
 html='<main><h1>Ada Example</h1><h2>Biography</h2><p>Her research has been funded by the NSF and private industry.</p></main>'
 assert extract_research_evidence(html,'Ada Example')['text']==''

def test_recovery_budget_enforces_new_job_cap_before_request(tmp_path):
 from scripts.regenerate_research_recovery import RecoveryBudget
 from scripts.regenerate_reviewed_ai import BudgetError
 budget=RecoveryBudget(tmp_path/'ledger.json')
 assert str(budget.cap)=='0.50'
 budget.entries.append({'charge_usd':'0.499999'})
 called=[]
 with pytest.raises(BudgetError):
  budget.request(lambda **kw:called.append(kw),{'model':'text-embedding-3-small','input':['x'*10000]})
 assert called==[]
 with pytest.raises(BudgetError):RecoveryBudget(tmp_path/'ledger.json')

def test_generated_ai_claims_require_source_evidence():
 from services.ai_enrichment import source_supported_topics
 thermal={'department':'Mechanical Engineering','research_interests':'Numerical simulations of turbulent flows and thermal management'}
 assert source_supported_topics(['Computational Biology','Artificial Intelligence','Machine Learning','Human-Centered AI'],thermal)==[]
 biomedical={'research_interests':'Machine learning for wearable biomedical devices'}
 assert source_supported_topics(['Machine Learning','Artificial Intelligence','Healthcare AI'],biomedical)==['Machine Learning','Artificial Intelligence','Healthcare AI']
 assert source_supported_topics(['Reinforcement Learning'],{'research_interests':'decision making in engineering under uncertainty'})==[]
 assert source_supported_topics(['Human-Centered AI'],{'research_interests':'cognitive processes of humans and inclusive technology'})==[]
