"""Read explicitly labelled research evidence from a single person's public profile."""
import re,unicodedata
from bs4 import BeautifulSoup

LABELS={'research interests','research areas','areas of interest','fields of interest','research expertise','research focus','research topics','research topic','research','expertise'}

def normalize_name(value):
 value=re.sub(r'^(?:Dr\.?|Prof\.?|Professor)\s+','',value,flags=re.I)
 value=re.sub(r':\s*Faculty Home Page$', '', value, flags=re.I)
 value=re.sub(r',?\s+(?:Ph\.?D\.?|PhD)$','',value,flags=re.I)
 return re.sub(r'[^a-z0-9]','',unicodedata.normalize('NFKD',value).encode('ascii','ignore').decode().lower())

def extract_research_evidence(html,name):
 soup=BeautifulSoup(html,'html.parser');root=soup.select_one('main') or soup.select_one('article') or soup.select_one('[role=main]') or soup.select_one('.region-content') or soup
 for tag in root.select('nav,footer,header,script,style,aside,.element-invisible,.visually-hidden'):tag.decompose()
 expected=normalize_name(name)
 identities=[h for h in root.find_all('h1') if normalize_name(h.get_text(' ',strip=True))==expected]
 if len(identities)!=1 or identities[0].name!='h1':return {'status':'identity_unconfirmed','text':''}
 if len(root.find_all('h1'))>1:return {'status':'ambiguous_profile','text':''}
 headings=root.find_all(re.compile('^h[1-6]$'))
 def section(heading):
  level=int(heading.name[1]);parts=[];plain=[]
  for element in heading.next_elements:
   if root not in element.parents:break
   if getattr(element,'name',None) and re.fullmatch('h[1-6]',element.name) and int(element.name[1])<=level:break
   if not getattr(element,'name',None) and heading not in element.parents:
    value=' '.join(str(element).split())
    if value:plain.append(value)
   if getattr(element,'name',None) in ('p','li'):
    if element.find_parent(['p','li']):continue
    text=' '.join(element.get_text(' ',strip=True).split())
    if text:parts.append(text)
  parts=[part for part in parts if len(part)>=15 and part.lower()!='back to top']
  return list(dict.fromkeys(parts)) if parts else [' '.join(plain).replace('Back to Top','').strip()]
 for heading in headings:
  label=heading.get_text(' ',strip=True).lower().strip(': ')
  if label not in LABELS:continue
  parts=section(heading)
  # A broad Research parent must not sweep in publications, lab members or website links.
  if label=='research':
   following=heading.find_next(re.compile('^h[1-6]$'))
   if following and int(following.name[1])>int(heading.name[1]):continue
  text='; '.join(parts)
  if not 15<=len(text)<=2400:continue
  if re.search(r'@|https?://|\b(?:publications|selected papers|office hours|contact us|research groups|research website)\b',text,re.I):continue
  if re.search(r'\b(?:no research|not available|no interests)\b',text,re.I):continue
  return {'status':'explicit_section','label':label,'text':text}
 for heading in headings:
  if heading.get_text(' ',strip=True).lower().strip(': ') not in {'biography','bio','about'}:continue
  sentences=[]
  for paragraph in section(heading):
   for sentence in re.split(r'(?<![A-Z]\.[A-Z]\.)(?<!Dr\.)(?<!Ph\.D\.)(?<=[.!?])\s+(?=[A-Z])',paragraph):
    if re.search(r'\b(?:research (?:interests|focus|focuses|examines|explores|investigates)|(?:his|her|their|my) research|studies (?:the|how)|research is (?:on|in|focused))\b',sentence,re.I) and 25<=len(sentence)<=1000 and not re.search(r'@|https?://|research has been (?:funded|supported)',sentence,re.I):sentences.append(sentence)
  text=' '.join(dict.fromkeys(sentences))
  if 25<=len(text)<=2000:return {'status':'biography_research_sentences','label':heading.get_text(' ',strip=True),'text':text}
 return {'status':'no_supported_research_section','text':''}
