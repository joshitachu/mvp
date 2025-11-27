# sroi_analyzer.py
import requests
from bs4 import BeautifulSoup
import time
from urllib.parse import urljoin, urlparse
import re
import json
from typing import Dict, List, Optional
import os
# --------------------------
# Configuration
# --------------------------
SERPAPI_KEY = os.environ.get("SERPAPI_KEY")  # Set
REQUEST_TIMEOUT = 10
DELAY_BETWEEN_REQUESTS = 1.5
MAX_PAGES_TO_CHECK = 7

# AI Provider Configuration
AI_PROVIDER = "groq"
GROQ_API_KEY = os.environ.get("GROQ_API_KEY")

TOGETHER_API_KEY = ""
OLLAMA_BASE_URL = "http://192.168.2.168:11434/api/chat" 
OLLAMA_MODEL = "llama3.1:8b" 

# --------------------------
# SROI Keywords
# --------------------------
SROI_PHRASES_DIRECT = [
    "social return verplichting", "sroi verplichting", "social return bij aanbestedingen",
    "verplichte sroi", "sroi percentage", "sroi realisatie", "sroi verplicht opgelegd",
    "verplichte inzet participatiedoelgroepen", "sroi verplichting"
]

PROCUREMENT_TERMS = [
    "opdracht gegund", "voornemen tot gunning", "aanbesteding", "inschrijver",
    "opdrachtnemer", "leverancier", "contractant", "best value winnaar",
    "emvi winnaar", "gunningsbesluit"
]

SROI_TERMS = ["social return", "sroi", "participatie-werkzaamheden", "participatiedoelgroepen"]

KPI_PHRASES = [
    "fte ingevuld", "uren social return", "sroi inzet", "prestatielevering social return",
    "monitoring social return", "uren social return gerealiseerd", "fte via social return"
]


def clean_url(url: Optional[str]) -> Optional[str]:
    """Ensure URL has proper scheme"""
    if not url:
        return None
    url = url.strip()
    if not url.startswith(('http://', 'https://')):
        url = 'https://' + url
    return url


def get_domain(url: str) -> str:
    """Extract domain from URL"""
    parsed = urlparse(url)
    return parsed.netloc


def search_with_serpapi(company_name: str) -> Optional[str]:
    """Search for company using SerpAPI"""
    if not SERPAPI_KEY or SERPAPI_KEY == 'YOUR_SERPAPI_KEY_HERE':
        return None
    
    params = {
        'q': company_name,
        'api_key': SERPAPI_KEY,
        'engine': 'google',
        'num': 1
    }
    
    try:
        response = requests.get('https://serpapi.com/search', params=params, timeout=REQUEST_TIMEOUT)
        if response.status_code == 200:
            results = response.json()
            organic_results = results.get('organic_results', [])
            if organic_results:
                return organic_results[0].get('link')
    except Exception as e:
        print(f"❌ SerpAPI error: {e}")
    
    return None


def fetch_page_content(url: str):
    """Fetch and parse HTML content from URL"""
    try:
        headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'
        }
        response = requests.get(url, headers=headers, timeout=REQUEST_TIMEOUT, allow_redirects=True)
        response.raise_for_status()
        return BeautifulSoup(response.text, 'html.parser')
    except Exception as e:
        print(f"❌ Error fetching {url}: {e}")
        return None


def extract_text_content(soup) -> str:
    """Extract clean text from HTML"""
    if not soup:
        return ""
    
    for script in soup(["script", "style", "nav", "footer", "header"]):
        script.decompose()
    
    text = soup.get_text(separator=' ', strip=True)
    text = re.sub(r'\s+', ' ', text)
    return text[:12000]


def normalize_url(url: str) -> str:
    """Normalize URL for comparison"""
    if not url:
        return url
    return url.rstrip('/')


def find_relevant_links(soup, base_url: str, max_links: int) -> List[str]:
    """Find internal links to check, prioritizing SROI-related pages"""
    if not soup:
        return []
    
    relevant_keywords = [
        'social', 'sroi', 'maatschappelijk', 'duurzaam', 'sustainability',
        'participatie', 'inclusie', 'over-ons', 'about', 'beleid', 'policy',
        'verantwoord', 'csr', 'mvo', 'about us', 'sustainability', 'impact', 'responsibility', 'diversity', 'Maatschappelijk verantwoord', 'Welkom Bij', "Over Ons" ,'Onze Missie', 'Onze Visie', 'Nieuws', 'Blog',"Projecten"
    ]
    
    domain = get_domain(base_url)
    base_norm = normalize_url(base_url)
    
    relevant_links = []
    all_internal_links = []
    
    for a_tag in soup.find_all('a', href=True):
        raw_href = a_tag['href']
        full_url = urljoin(base_url, raw_href)
        
        if get_domain(full_url) != domain:
            continue
        
        full_norm = normalize_url(full_url)
        if full_norm == base_norm:
            continue
        
        href_lower = raw_href.lower()
        text_lower = a_tag.get_text().lower()
        
        if full_url not in all_internal_links:
            all_internal_links.append(full_url)
        
        if any(keyword in href_lower or keyword in text_lower for keyword in relevant_keywords):
            if full_url not in relevant_links:
                relevant_links.append(full_url)
    
    selected_links = []
    
    for link in relevant_links:
        if link not in selected_links:
            selected_links.append(link)
        if len(selected_links) >= max_links:
            return selected_links
    
    for link in all_internal_links:
        if link not in selected_links:
            selected_links.append(link)
        if len(selected_links) >= max_links:
            break
    
    return selected_links


def keyword_analysis(text: str) -> Dict:
    """Fallback keyword analysis with scoring"""
    text_lower = text.lower()
    
    scores = {
        'direct_sroi': 0,
        'procurement': 0,
        'general_sroi': 0,
        'kpi': 0
    }
    
    found_keywords = []
    
    for keyword in SROI_PHRASES_DIRECT:
        if keyword.lower() in text_lower:
            scores['direct_sroi'] += 3
            found_keywords.append(keyword)
    
    for keyword in PROCUREMENT_TERMS:
        if keyword.lower() in text_lower:
            scores['procurement'] += 1
            found_keywords.append(keyword)
    
    for keyword in SROI_TERMS:
        if keyword.lower() in text_lower:
            scores['general_sroi'] += 2
            found_keywords.append(keyword)
    
    for keyword in KPI_PHRASES:
        if keyword.lower() in text_lower:
            scores['kpi'] += 2
            found_keywords.append(keyword)
    
    total_score = sum(scores.values())
    sroi_compliant = total_score >= 5 or scores['direct_sroi'] >= 3
    
    if total_score >= 10:
        confidence = "high"
    elif total_score >= 5:
        confidence = "medium"
    else:
        confidence = "low"
    
    return {
        "sroi_compliant": sroi_compliant,
        "confidence": confidence,
        "evidence": list(set(found_keywords))[:10],
        "summary": f"Keyword analyse: score {total_score}, gevonden {len(set(found_keywords))} unieke termen.",
        "score": total_score,
        "score_breakdown": scores
    }


def analyze_with_groq(company_name: str, text_content: str) -> Dict:
    """Use Groq Cloud API"""
    if not GROQ_API_KEY or GROQ_API_KEY == "YOUR_GROQ_KEY_HERE":
        return keyword_analysis(text_content)
    
    prompt = f"""
ROL: U bent een SROI-analist voor de Nederlandse aanbestedingsmarkt. U beoordeelt bedrijven ZEER RUIM en ZEER MILD. Elk bedrijf dat op enige manier sociale inzet toont, wordt gezien als potentieel SROI-relevant.

DOEL: Bepaal voor bedrijf "{company_name}" hoe waarschijnlijk het is dat zij SROI kunnen invullen of eraan voldoen, zelfs als SROI NIET expliciet wordt genoemd.

------------------------------------------------------------
🎯 HERDEFINITIE: EXTREEM MILDE SROI-INTERPRETATIE
------------------------------------------------------------

LET OP: Gebruik een **zeer brede** en **inclusieve** definitie van SROI.

✔ Een bedrijf is al SROI-relevant wanneer één of meer van deze signalen voorkomen:
- Inclusieve arbeid (bijv. statushouders, vluchtelingen, Wajong, re-integratie)
- Leer-werkplekken, stages, praktijkleren, BBL, mbo
- Jobcoaching, begeleiding naar werk, participatieprojecten
- HR-teksten over diversiteit, inclusie of “ruimte voor talent”
- Sociale missie, MVO, SDG’s, maatschappelijke waarde
- Opleidingen, scholing, kansen voor mensen
- Samenwerking met overheid, gemeenten, sociale partners
- Vacatures op laagdrempelniveau (schoonmaak, logistiek, productie, etc.)
- Teams met veel instroommogelijkheden of lage instap

✔ Alleen bedrijven die écht helemaal GEEN ENKEL sociaal element tonen krijgen een lage score.

Het woord "SROI" hoeft NIET te worden genoemd om toch als compliant te worden gezien.

------------------------------------------------------------
📊 SCORINGSSYSTEEM
------------------------------------------------------------

Score (0–100):
- 0–20: Helemaal geen sociale signalen  
- 21–40: Een klein beetje sociaal of MVO  
- 41–60: Duidelijke sociale elementen, maar geen expliciete doelgroepen  
- 61–80: Sterk inclusief beleid, participatie, begeleiding, stages  
- 81–100: Expliciet inclusief + zeer geschikt voor SROI, ook zonder term “SROI”

SROI compliant (boolean):
- TRUE = bijna altijd, behalve als er echt geen enkel sociaal signaal is.

Confidence: low / medium / high

------------------------------------------------------------
TE ANALYSEREN TEKST:
{text_content[:1600]}

------------------------------------------------------------
**VERWACHTE JSON RESPONSE:** Lever **ALLEEN** het JSON-object, zonder enige andere tekst of uitleg. De 'evidence' moet de exacte zinnen of zinsdelen uit de tekst zijn die het bewijs leveren.
json
{{
  "sroi_compliant": true/false,
  "confidence": "high/medium/low",
  "evidence": ["lijst van de meest overtuigende bewijzen (max 7-10) uit de tekst, in het Nederlands"],
  "summary": "Een beknopte en professionele Nederlandse samenvatting van de bevindingen t.a.v. SROI.",
  "score": 0-100
}}

"""

    try:
        headers = {
            "Authorization": f"Bearer {GROQ_API_KEY}",
            "Content-Type": "application/json"
        }
        
        data = {
            "model": "llama-3.3-70b-versatile",
            "messages": [{"role": "user", "content": prompt}],
            "temperature": 0.1,
            "max_tokens": 800,
            "response_format": {"type": "json_object"}
        }
        
        response = requests.post(
            "https://api.groq.com/openai/v1/chat/completions",
            headers=headers,
            json=data,
            timeout=30
        )
        
        if response.status_code == 200:
            result = response.json()
            analysis_text = result['choices'][0]['message']['content']
            analysis = json.loads(analysis_text)
            return analysis
        else:
            return keyword_analysis(text_content)
            
    except Exception as e:
        print(f"❌ Groq error: {e}")
        return keyword_analysis(text_content)
    

def analyze_with_ollama(company_name: str, text_content: str) -> Dict:
    """Use local Ollama API instead of Groq"""
    try:
        prompt = f"""
ROL: U bent een SROI-analist voor de Nederlandse aanbestedingsmarkt. U beoordeelt bedrijven ZEER RUIM en ZEER MILD. Elk bedrijf dat op enige manier sociale inzet toont, wordt gezien als potentieel SROI-relevant.

DOEL: Bepaal voor bedrijf "{company_name}" hoe waarschijnlijk het is dat zij SROI kunnen invullen of eraan voldoen, zelfs als SROI NIET expliciet wordt genoemd.

------------------------------------------------------------
🎯 HERDEFINITIE: EXTREEM MILDE SROI-INTERPRETATIE
------------------------------------------------------------

LET OP: Gebruik een **zeer brede** en **inclusieve** definitie van SROI.

✔ Een bedrijf is al SROI-relevant wanneer één of meer van deze signalen voorkomen:
- Inclusieve arbeid (bijv. statushouders, vluchtelingen, Wajong, re-integratie)
- Leer-werkplekken, stages, praktijkleren, BBL, mbo
- Jobcoaching, begeleiding naar werk, participatieprojecten
- HR-teksten over diversiteit, inclusie of “ruimte voor talent”
- Sociale missie, MVO, SDG’s, maatschappelijke waarde
- Opleidingen, scholing, kansen voor mensen
- Samenwerking met overheid, gemeenten, sociale partners
- Vacatures op laagdrempelniveau (schoonmaak, logistiek, productie, etc.)
- Teams met veel instroommogelijkheden of lage instap

✔ Alleen bedrijven die écht helemaal GEEN ENKEL sociaal element tonen krijgen een lage score.

Het woord "SROI" hoeft NIET te worden genoemd om toch als compliant te worden gezien.

------------------------------------------------------------
📊 SCORINGSSYSTEEM (VEEL MILDER)
------------------------------------------------------------

Score (0–100):
- 0–20: Helemaal geen sociale signalen  
- 21–40: Een klein beetje sociaal of MVO  
- 41–60: Duidelijke sociale elementen, maar geen expliciete doelgroepen  
- 61–80: Sterk inclusief beleid, participatie, begeleiding, stages  
- 81–100: Expliciet inclusief + zeer geschikt voor SROI, ook zonder term “SROI”

SROI compliant (boolean):
- TRUE = bijna altijd, behalve als er echt geen enkel sociaal signaal is.

Confidence: low / medium / high

------------------------------------------------------------
📄 TE ANALYSEREN TEKST:
{text_content[:1600]}

------------------------------------------------------------
**VERWACHTE JSON RESPONSE:** Lever **ALLEEN** het JSON-object, zonder enige andere tekst of uitleg. De 'evidence' moet de exacte zinnen of zinsdelen uit de tekst zijn die het bewijs leveren.
json
{{
  "sroi_compliant": true/false,
  "confidence": "high/medium/low",
  "evidence": ["lijst van de meest overtuigende bewijzen (max 5) uit de tekst, in het Nederlands"],
  "summary": "Een beknopte en professionele Nederlandse samenvatting van de bevindingen t.a.v. SROI.",
  "score": 0-100
}}

"""
        # Ollama expects a single message with 'role' and 'content'
        payload = {
            "model": OLLAMA_MODEL,
            "messages": [
                {"role": "user", "content": prompt}
            ],
            "stream": False  # We want a single JSON response back
        }

        response = requests.post(
            OLLAMA_BASE_URL,
            json=payload,
            timeout=60
        )

        if response.status_code != 200:
            return keyword_analysis(text_content)

        data = response.json()

        # Ollama returns the model response in `message["content"]`
        analysis_text = data["message"]["content"]

        # Parse the returned JSON
        analysis = json.loads(analysis_text)
        return analysis

    except Exception as e:
        print(f"❌ Ollama error: {e}")
        return keyword_analysis(text_content)



def analyze_with_ai(company_name: str, text_content: str) -> Dict:
    """Route to the selected AI provider"""
    if AI_PROVIDER == "groq":
        return analyze_with_groq(company_name, text_content)
    # if AI_PROVIDER == "together":
    #     return analyze_with_together(company_name, text_content)
    # if AI_PROVIDER == "ollama":
    #     return analyze_with_ollama(company_name, text_content)
    else:
        return keyword_analysis(text_content)


def smart_scrape_and_analyze(company_name: str, start_url: str) -> Dict:
    """Smart scraping: check homepage + several internal pages, then analyze"""
    print(f"🔍 Analyzing: {company_name}")
    
    all_text = []
    pages_checked = []
    
    soup = fetch_page_content(start_url)
    if soup:
        homepage_text = extract_text_content(soup)
        all_text.append(homepage_text)
        pages_checked.append(start_url)
        
        max_extra_pages = max(0, MAX_PAGES_TO_CHECK - 1)
        relevant_links = find_relevant_links(soup, start_url, max_extra_pages)
        
        for link in relevant_links:
            time.sleep(DELAY_BETWEEN_REQUESTS)
            page_soup = fetch_page_content(link)
            if page_soup:
                page_text = extract_text_content(page_soup)
                all_text.append(page_text)
                pages_checked.append(link)
    
    if not all_text:
        return {
            "error": "Could not fetch any content",
            "pages_checked": 0,
            "sroi_compliant": False,
            "confidence": "none",
            "score": 0
        }
    
    combined_text = " ".join(all_text)
    analysis = analyze_with_ai(company_name, combined_text)
    analysis['pages_checked'] = len(pages_checked)
    analysis['urls_checked'] = pages_checked
    
    return analysis


def analyze_notice_sroi(notice: Dict) -> Dict:
    """
    Analyze a single notice for SROI compliance.
    Expected fields in notice:
    - win_bedrijf_naam
    - win_website
    - buyer_bedrijf_naam
    - buyer_website
    """
    result = {
        "notice_id": notice.get("notice_id"),
        "publicatie_id": notice.get("publicatieId"),
        "winner_name": notice.get("win_bedrijf_naam"),
        "winner_website": notice.get("win_website"),
        "buyer_name": notice.get("buyer_bedrijf_naam"),
        "buyer_website": notice.get("buyer_website"),
        "analyzed_url": None,
        "url_source": None,
        "sroi_compliant": False,
        "confidence": "none",
        "score": 0,
        "evidence": [],
        "summary": "Geen analyse uitgevoerd",
        "pages_checked": 0,
        "error": None
    }
    
    # Determine which company to analyze (winner preferred)
    target_name = notice.get("win_bedrijf_naam")
    target_url = clean_url(notice.get("win_website"))
    
    if not target_name:
        target_name = notice.get("buyer_bedrijf_naam")
        target_url = clean_url(notice.get("buyer_website"))
    
    if not target_name:
        result["error"] = "Geen bedrijfsnaam beschikbaar"
        return result
    
    # Try to get URL
    if not target_url:
        print(f"🔎 Searching for: {target_name}")
        target_url = search_with_serpapi(target_name)
        result["url_source"] = "serpapi_search"
    else:
        result["url_source"] = "direct_url"
    
    if not target_url:
        result["error"] = "Geen URL gevonden"
        return result
    
    result["analyzed_url"] = target_url
    
    # Perform analysis
    try:
        analysis = smart_scrape_and_analyze(target_name, target_url)
        result.update({
            "sroi_compliant": analysis.get("sroi_compliant", False),
            "confidence": analysis.get("confidence", "none"),
            "score": analysis.get("score", 0),
            "evidence": analysis.get("evidence", []),
            "summary": analysis.get("summary", ""),
            "pages_checked": analysis.get("pages_checked", 0),
            "error": analysis.get("error")
        })
    except Exception as e:
        result["error"] = str(e)
    
    return result


def analyze_import_sroi(notices: List[Dict], progress_callback=None) -> List[Dict]:
    """
    Analyze all notices from an import for SROI compliance.
    
    Args:
        notices: List of notice dictionaries from the database
        progress_callback: Optional callback function(current, total, result)
    
    Returns:
        List of SROI analysis results
    """
    results = []
    total = len(notices)
    
    print(f"Starting SROI analysis for {total} notices...")
    
    for idx, notice in enumerate(notices):
        print(f"\n{'='*80}")
        print(f"Analyzing {idx + 1}/{total}")
        
        result = analyze_notice_sroi(notice)
        results.append(result)
        
        if progress_callback:
            progress_callback(idx + 1, total, result)
        
        # Small delay to avoid rate limiting
        if idx < total - 1:
            time.sleep(1)
    
    # Calculate summary statistics
    compliant_count = sum(1 for r in results if r["sroi_compliant"])
    avg_score = sum(r.get("score", 0) for r in results) / len(results) if results else 0
    
    print(f"\n{'='*80}")
    print(f"✅ Analysis complete!")
    print(f"   SROI Compliant: {compliant_count}/{total} ({compliant_count/total*100:.1f}%)")
    print(f"   Average Score: {avg_score:.1f}")
    print(f"{'='*80}")
    
    return results