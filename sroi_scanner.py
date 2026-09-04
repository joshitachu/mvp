# sroi_analyzer.py

import os
import time
import re
import json
from typing import Dict, List, Optional, Tuple
from urllib.parse import urljoin, urlparse

import requests
from bs4 import BeautifulSoup
from dotenv import load_dotenv
import google.generativeai as genai

load_dotenv()

# --------------------------
# Configuration
# --------------------------

# SerpAPI (optional; paid but has free tier)
SERPAPI_KEY = os.environ.get("SERPAPI_API_KEY")

REQUEST_TIMEOUT = 10
DELAY_BETWEEN_REQUESTS = 1.5
MAX_PAGES_TO_CHECK = 7

# Gemini API key (free tier from Google AI Studio)
GEMINI_API_KEY = os.environ.get("GOOGLE_API_KEY") or os.environ.get("GEMINI_API_KEY")

# Google Programmable Search (Custom Search JSON API — 100 free queries/day)
GOOGLE_CSE_API_KEY = os.environ.get("GOOGLE_CSE_API_KEY")
GOOGLE_CSE_CX = os.environ.get("GOOGLE_CSE_CX")

# AI Provider Configuration
AI_PROVIDER = "groq"  # "gemini" or "groq"
GROQ_API_KEY = os.environ.get("GROQ_API_KEY")

TOGETHER_API_KEY = ""
OLLAMA_BASE_URL = ""
OLLAMA_MODEL = ""

# Debug: see if CSE keys are loaded
print("Google CSE key/cx:", GOOGLE_CSE_API_KEY, GOOGLE_CSE_CX)

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

# --------------------------
# Utility helpers
# --------------------------

def clean_url(url: Optional[str]) -> Optional[str]:
    """Ensure URL has proper scheme."""
    if not url:
        return None
    url = url.strip()
    if not url.startswith(("http://", "https://")):
        url = "https://" + url
    return url


def get_domain(url: str) -> str:
    """Extract domain from URL."""
    parsed = urlparse(url)
    return parsed.netloc



def normalize_url(url: str) -> str:
    """Normalize URL for comparison."""
    if not url:
        return url
    from urllib.parse import urlparse, urlunparse
    parsed = urlparse(url)
    parsed = parsed._replace(fragment="", query="")
    cleaned = urlunparse(parsed)
    return cleaned.rstrip("/")

def get_domain(url: str) -> str:
    """Extract domain from URL."""
    parsed = urlparse(url)
    return parsed.netloc

# --------------------------
# Search helpers
# --------------------------

def search_with_serpapi(company_name: str) -> Optional[str]:
    """Search for company using SerpAPI."""
    if not SERPAPI_KEY or SERPAPI_KEY == "YOUR_SERPAPI_KEY_HERE":
        print("⚠️ SERPAPI_KEY not set or placeholder; skipping SerpAPI search.")
        return None

    params = {
        "q": company_name,
        "api_key": SERPAPI_KEY,
        "engine": "google",
        "num": 1,
    }

    try:
        response = requests.get(
            "https://serpapi.com/search",
            params=params,
            timeout=REQUEST_TIMEOUT,
        )
        response.raise_for_status()
        results = response.json()
        organic_results = results.get("organic_results", [])
        if organic_results:
            url = organic_results[0].get("link")
            print(f"🔎 SerpAPI found URL: {url}")
            return url
        else:
            print("⚠️ SerpAPI returned no organic results.")
    except Exception as e:
        print(f"❌ SerpAPI error: {e}")

    return None


def search_with_google_cse(company_name: str) -> Optional[str]:
    """
    Search for company using Google Programmable Search (Custom Search JSON API).
    Free tier: ~100 queries/day.
    """
    if not GOOGLE_CSE_API_KEY or not GOOGLE_CSE_CX:
        print("❌ GOOGLE_CSE_API_KEY or GOOGLE_CSE_CX not set; skipping Google CSE search.")
        return None

    params = {
        "key": GOOGLE_CSE_API_KEY,
        "cx": GOOGLE_CSE_CX,
        "q": company_name,
        "num": 1,
    }

    try:
        response = requests.get(
            "https://www.googleapis.com/customsearch/v1",
            params=params,
            timeout=REQUEST_TIMEOUT,
        )
        response.raise_for_status()
        data = response.json()
        items = data.get("items", [])
        if items:
            url = items[0].get("link")
            print(f"🔍 Google CSE found URL: {url}")
            return url
        else:
            print("⚠️ Google CSE returned no items.")
    except Exception as e:
        print(f"❌ Google CSE error: {e}")

    return None


# --------------------------
# Scraping
# --------------------------

def fetch_page_content(url: str):
    """Fetch and parse HTML content from URL."""
    try:
        headers = {
            "User-Agent": (
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/120.0 Safari/537.36"
            )
        }
        response = requests.get(
            url,
            headers=headers,
            timeout=REQUEST_TIMEOUT,
            allow_redirects=True,
        )
        response.raise_for_status()
        return BeautifulSoup(response.text, "html.parser")
    except Exception as e:
        print(f"❌ Error fetching {url}: {e}")
        return None


def extract_text_content(soup) -> str:
    """Extract clean text from HTML."""
    if not soup:
        return ""

    for tag in soup(["script", "style", "nav", "footer", "header"]):
        tag.decompose()

    text = soup.get_text(separator=" ", strip=True)
    text = re.sub(r"\s+", " ", text)
    return text[:12000]


def company_identity_matches(soup, company_name: str) -> bool:
    """Reject search results that do not credibly identify the target company."""
    if not soup or not company_name:
        return False
    page_identity = " ".join([
        soup.title.get_text(" ", strip=True) if soup.title else "",
        (soup.find("meta", attrs={"name": "description"}) or {}).get("content", ""),
        extract_text_content(soup)[:3000],
    ]).lower()
    normalized_name = re.sub(r"\W", "", company_name).lower()
    if normalized_name and normalized_name in re.sub(r"\W", "", page_identity):
        return True
    ignored = {"bv", "b.v", "nv", "n.v", "the", "and", "van", "de", "het"}
    tokens = [token.lower() for token in re.findall(r"[\w-]+", company_name) if len(token) >= 4 and token.lower() not in ignored]
    return bool(tokens) and any(token in page_identity for token in tokens)





def find_first_working_url(company_name: str, initial_url: Optional[str]) -> Tuple[Optional[str], Optional[str]]:
    """
    Try the given URL; if it's missing or not reachable, fall back to:
    1) SerpAPI (if key present)
    2) Google CSE (free)

    Returns:
        (url, url_source) or (None, None)
    """
    # 1) Try the direct URL from the notice
    if initial_url:
        print(f"🌐 Trying direct URL: {initial_url}")
        if (soup := fetch_page_content(initial_url)) and company_identity_matches(soup, company_name):
            return initial_url, "direct_url"
        else:
            print("⚠️ Direct URL was unreachable or did not identify the company, falling back to search.")

    # 2) Try SerpAPI if configured
    serp_url = search_with_serpapi(company_name)
    if serp_url:
        if (soup := fetch_page_content(serp_url)) and company_identity_matches(soup, company_name):
            return serp_url, "serpapi_search"
        else:
            print("⚠️ SerpAPI URL not reachable, trying Google CSE.")

    # 3) Try Google CSE (100 free searches/day)
    cse_url = search_with_google_cse(company_name)
    if cse_url:
        if (soup := fetch_page_content(cse_url)) and company_identity_matches(soup, company_name):
            return cse_url, "google_cse_search"
        else:
            print("⚠️ Google CSE URL also not reachable.")

    # Nothing worked
    return None, None


# --------------------------
# Fallback keyword analysis
# --------------------------

def keyword_analysis(text: str) -> Dict:
    """Fallback keyword analysis with scoring."""
    text_lower = text.lower()

    scores = {
        "direct_sroi": 0,
        "procurement": 0,
        "general_sroi": 0,
        "kpi": 0,
    }

    found_keywords: List[str] = []

    for keyword in SROI_PHRASES_DIRECT:
        if keyword.lower() in text_lower:
            scores["direct_sroi"] += 3
            found_keywords.append(keyword)

    for keyword in PROCUREMENT_TERMS:
        if keyword.lower() in text_lower:
            scores["procurement"] += 1
            found_keywords.append(keyword)

    for keyword in SROI_TERMS:
        if keyword.lower() in text_lower:
            scores["general_sroi"] += 2
            found_keywords.append(keyword)

    for keyword in KPI_PHRASES:
        if keyword.lower() in text_lower:
            scores["kpi"] += 2
            found_keywords.append(keyword)

    total_score = sum(scores.values())
    sroi_compliant = total_score >= 5 or scores["direct_sroi"] >= 3

    if total_score >= 10:
        confidence = "high"
    elif total_score >= 5:
        confidence = "medium"
    else:
        confidence = "low"

    evidence_sentences = []
    for sentence in re.split(r"(?<=[.!?])\s+", text):
        if any(keyword.lower() in sentence.lower() for keyword in set(found_keywords)):
            evidence_sentences.append(sentence.strip()[:500])
        if len(evidence_sentences) == 5:
            break
    return {
        "sroi_compliant": sroi_compliant,
        "confidence": confidence,
        "evidence": evidence_sentences,
        "summary": f"Geen AI-compliance-oordeel: keyword-fallback met score {total_score} en {len(set(found_keywords))} unieke termen.",
        "score": total_score,
        "score_breakdown": scores,
        "analysis_method": "keyword_fallback",
        "verdict": "insufficient_evidence",
    }


# --------------------------
# Groq (optional)
# --------------------------

def analyze_with_groq(company_name: str, text_content: str) -> Dict:
    """Use Groq Cloud API (optional)."""
    print(text_content)
    if not GROQ_API_KEY or GROQ_API_KEY == "YOUR_GROQ_KEY_HERE":
        return keyword_analysis(text_content)

    prompt = f"""
## ROL
U bent een SROI-analist voor de Nederlandse aanbestedingsmarkt.  
U beoordeelt bedrijven **mild**, maar met **duidelijke nuance**.  
Bedrijven worden **niet automatisch** SROI-relevant: er moet ten minste **één sociaal signaal** aanwezig zijn — maar dit signaal mag **breed geïnterpreteerd** worden.

## DOEL
Bepaal voor bedrijf **"{company_name}"** hoe waarschijnlijk het is dat zij SROI kunnen invullen of eraan voldoen, ook als de term “SROI” niet wordt genoemd.

---

# ------------------------------------------------------------
# BALANCED MILD DEFINITIE VAN SROI
# ------------------------------------------------------------

Gebruik een **brede**, maar niet naïeve interpretatie van SROI.

### ✔ Sterke sociale signalen (zwaarder meewegen)
- Inclusieve arbeid  
  (statushouders, vluchtelingen, Wajong, re-integratie, garantiebaan, SW, mensen met afstand tot de arbeidsmarkt)
- Leer-werkplekken, BBL, stages, praktijkleren
- Jobcoaching, begeleiding naar werk
- Samenwerking met overheid / gemeenten / UWV / sociale partners
- Maatschappelijke missie, MVO-beleid, SDG’s
- Laagdrempelige vacatures  
  (schoonmaak, horeca, productie, logistiek, inpak, facilitaire functies)

### ✔ Zwakke sociale signalen (light indicators)
Deze tellen mee, maar verhogen de score **beperkt**.
- Algemene HR-teksten zoals: “ontwikkeling”, “groei”, “ruimte voor talent”
- Interne scholing, interne coaching
- Algemene opleidingsmogelijkheden
- Algemeen MVO zonder concrete mensgerichte voorbeelden

### ✖ Geen sociale signalen (terecht lage score)
- Puur commerciële of technische teksten zonder mensen
- Alleen product- of dienstenbeschrijvingen
- Geen HR/MVO/maatschappelijke elementen
- Geen verwijzing naar leren, werken, ontwikkelen of doelgroepen

---

# ------------------------------------------------------------
# SCORINGSSYSTEEM (Mild maar met nuance)
# ------------------------------------------------------------

**0–20** — Geen sociale signalen  
**21–40** — Zwakke sociale elementen (algemene HR-taal of MVO)  
**41–60** — Duidelijke sociale elementen, maar niet doelgroepgericht  
**61–80** — Sterke sociale componenten, begeleiding, stages, inclusie  
**81–100** — Structureel inclusief + sterk passend bij SROI

**SROI compliant (boolean):**
- **TRUE** = score > 20  
- **FALSE** = score ≤ 20 (echt nul sociale signalen)

Confidence: low / medium / high

---

## TE ANALYSEREN TEKST
{text_content[:8000]}

---
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
            "Content-Type": "application/json",
        }

        data = {
            "model": "llama-3.3-70b-versatile",
            "messages": [{"role": "user", "content": prompt}],
            "temperature": 0.1,
            "max_tokens": 800,
            "response_format": {"type": "json_object"},
        }

        response = requests.post(
            "https://api.groq.com/openai/v1/chat/completions",
            headers=headers,
            json=data,
            timeout=30,
        )

        if response.status_code == 200:
            result = response.json()
            analysis_text = result["choices"][0]["message"]["content"]
            analysis = json.loads(analysis_text)
            return analysis
        else:
            print("⚠️ Groq returned non-200:", response.status_code, response.text)
            return keyword_analysis(text_content)

    except Exception as e:
        print(f"❌ Groq error: {e}")
        return keyword_analysis(text_content)


# --------------------------
# Gemini
# --------------------------
def analyze_with_gemini(company_name: str, text_content: str) -> Dict:
    """Use Google Gemini API (free tier) and parse JSON response safely."""
    try:
        if not GEMINI_API_KEY:
            print("❌ Please set GOOGLE_API_KEY or GEMINI_API_KEY environment variable.")
            return keyword_analysis(text_content)

        genai.configure(api_key=GEMINI_API_KEY)

        prompt = f"""
## ROL
U bent een SROI-analist voor de Nederlandse aanbestedingsmarkt.  
U beoordeelt bedrijven **mild**, maar met **duidelijke nuance**.  
Bedrijven worden **niet automatisch** SROI-relevant: er moet ten minste **één sociaal signaal** aanwezig zijn — maar dit signaal mag **breed geïnterpreteerd** worden.

## DOEL
Bepaal voor bedrijf **"{company_name}"** hoe waarschijnlijk het is dat zij SROI kunnen invullen of eraan voldoen, ook als de term “SROI” niet wordt genoemd.

---

# ------------------------------------------------------------
# BALANCED MILD DEFINITIE VAN SROI
# ------------------------------------------------------------

Gebruik een **brede**, maar niet naïeve interpretatie van SROI.

### Sterke sociale signalen (zwaarder meewegen)
- Inclusieve arbeid  
  (statushouders, vluchtelingen, Wajong, re-integratie, garantiebaan, SW, mensen met afstand tot de arbeidsmarkt)
- Leer-werkplekken, BBL, stages, praktijkleren
- Jobcoaching, begeleiding naar werk
- Samenwerking met overheid / gemeenten / UWV / sociale partners
- Maatschappelijke missie, MVO-beleid, SDG’s
- Laagdrempelige vacatures  
  (schoonmaak, horeca, productie, logistiek, inpak, facilitaire functies)

### Zwakke sociale signalen (light indicators)
Deze tellen mee, maar verhogen de score **beperkt**.
- Algemene HR-teksten zoals: “ontwikkeling”, “groei”, “ruimte voor talent”
- Interne scholing, interne coaching
- Algemene opleidingsmogelijkheden
- Algemeen MVO zonder concrete mensgerichte voorbeelden

### Geen sociale signalen (terecht lage score)
- Puur commerciële of technische teksten zonder mensen
- Alleen product- of dienstenbeschrijvingen
- Geen HR/MVO/maatschappelijke elementen
- Geen verwijzing naar leren, werken, ontwikkelen of doelgroepen

---

# ------------------------------------------------------------
# SCORINGSSYSTEEM (Mild maar met nuance)
# ------------------------------------------------------------

**0–20** — Geen sociale signalen  
**21–40** — Zwakke sociale elementen (algemene HR-taal of MVO)  
**41–60** — Duidelijke sociale elementen, maar niet doelgroepgericht  
**61–80** — Sterke sociale componenten, begeleiding, stages, inclusie  
**81–100** — Structureel inclusief + sterk passend bij SROI

**SROI compliant (boolean):**
- **TRUE** = score > 20  
- **FALSE** = score ≤ 20 (echt nul sociale signalen)

Confidence: low / medium / high

---

## TE ANALYSEREN TEKST
{text_content[:8000]}

---
------------------------------------------------------------
**VERWACHTE JSON RESPONSE:** Lever **ALLEEN** het JSON-object, zonder enige andere tekst of uitleg. De 'evidence' moet de exacte zinnen of zinsdelen uit de tekst zijn die het bewijs leveren.

{{
  "sroi_compliant": true/false,
  "confidence": "high/medium/low",
  "evidence": ["lijst van de meest overtuigende bewijzen (max 5) uit de tekst, in het Nederlands"],
  "summary": "Een beknopte en professionele Nederlandse samenvatting van de bevindingen t.a.v. SROI.",
  "score": 0-100
}}
"""

        model = genai.GenerativeModel("gemini-2.5-flash")

        response = model.generate_content(
            prompt,
            generation_config=genai.types.GenerationConfig(
                temperature=0.2,
                max_output_tokens=2048,
            ),
        )

        # ---- 1. Tekst ophalen uit alle candidates/parts ----
        text_chunks = []

        if getattr(response, "candidates", None):
            for cand in response.candidates:
                # Als finish_reason aangeeft dat er geen content is (bv SAFETY), skippen we die candidate
                fr = getattr(cand, "finish_reason", None)
                # Optional: log dit als je wilt zien waarom hij stopt
                if str(fr) not in ("None", "0", "FINISH_REASON_STOP"):
                    # Je zou hier nog meer logging kunnen doen als je wilt debuggen
                    pass

                content = getattr(cand, "content", None)
                parts = getattr(content, "parts", None) if content else None
                if not parts:
                    continue

                for p in parts:
                    t = getattr(p, "text", None)
                    if t:
                        text_chunks.append(t)

        analysis_text = "".join(text_chunks).strip()

        if not analysis_text:
            print("❌ Gemini returned no text (likely safety / no parts); falling back to keyword_analysis.")
            return keyword_analysis(text_content)

        # ---- 2. Code fences opruimen ----
        if analysis_text.startswith("```json"):
            analysis_text = analysis_text[7:]
        if analysis_text.startswith("```"):
            analysis_text = analysis_text[3:]
        if analysis_text.endswith("```"):
            analysis_text = analysis_text[:-3]
        analysis_text = analysis_text.strip()

        # ---- 3. JSON robuust uit de tekst knippen ----
        # Soms zet het model nog commentaar voor/na de JSON → we pakken substring tussen eerste { en laatste }
        start = analysis_text.find("{")
        end = analysis_text.rfind("}")
        if start == -1 or end == -1 or end <= start:
            print("❌ Gemini response bevat geen duidelijk JSON-object, falling back. First 200 chars:")
            print(analysis_text[:200])
            return keyword_analysis(text_content)

        json_candidate = analysis_text[start:end + 1].strip()

        try:
            analysis = json.loads(json_candidate)
        except json.JSONDecodeError:
            print("❌ Gemini returned invalid JSON, falling back. First 200 chars van JSON-candidate:")
            print(json_candidate[:200])
            return keyword_analysis(text_content)

        return analysis

    except Exception as e:
        print(f"❌ Gemini error: {e}")
        return keyword_analysis(text_content)

# --------------------------
# AI router
# --------------------------

def analyze_with_ai(company_name: str, text_content: str) -> Dict:
    """Route to the selected AI provider."""
    # Rank passages before handing them to a model. The old code always sent
    # the first 8k characters, regardless of what the crawler had found.
    paragraphs = re.split(r"(?<=[.!?])\s+", text_content)
    ranked = sorted(
        paragraphs,
        key=lambda paragraph: sum(keyword.lower() in paragraph.lower() for keyword in SROI_PHRASES_DIRECT + SROI_TERMS + KPI_PHRASES),
        reverse=True,
    )
    selected_text = " ".join(ranked)[:8000] or text_content[:8000]
    if AI_PROVIDER == "groq":
        result = analyze_with_groq(company_name, selected_text)
    elif AI_PROVIDER == "gemini":
        result = analyze_with_gemini(company_name, selected_text)
    else:
        result = keyword_analysis(selected_text)
    if result.get("analysis_method") == "keyword_fallback":
        return result
    evidence = [item for item in result.get("evidence", []) if isinstance(item, str) and item.lower() in selected_text.lower()]
    if not evidence:
        return {
            **keyword_analysis(selected_text),
            "summary": "Geen AI-compliance-oordeel: model leverde geen controleerbaar bronbewijs.",
            "verdict": "insufficient_evidence",
        }
    result["evidence"] = evidence[:10]
    result["analysis_method"] = f"{AI_PROVIDER}_grounded"
    result["verdict"] = "assessed"
    return result

def smart_scrape_and_analyze_hybrid(company_name: str, start_url: str) -> Dict:
    """
    HYBRIDE STRATEGIE:
    
    1. Scrape homepage
    2. Probeer standaard URL's (/over-ons, /duurzaamheid, etc.)
    3. Voor elke gevonden standaard pagina: zoek sub-links
    4. Als te weinig gevonden: fallback naar homepage link-scanning
    5. Analyseer alle content samen
    """
    
    print(f"\n{'='*80}")
    print(f"🔍 Starting HYBRID SROI analysis for: {company_name}")
    print(f"🌐 Start URL: {start_url}")
    print(f"{'='*80}\n")

    all_text: List[str] = []
    pages_to_scrape: List[Tuple[str, str]] = []  # (url, source)
    pages_scraped: Set[str] = set()
    
    # ============================================================
    # STAP 1: Scrape homepage
    # ============================================================
    print("📍 STEP 1: Scraping homepage...")
    
    homepage_soup = fetch_page_content(start_url)
    if homepage_soup:
        homepage_text = extract_text_content(homepage_soup)
        all_text.append(homepage_text)
        pages_scraped.add(normalize_url(start_url))
        
        print(f"  ✅ Homepage OK ({len(homepage_text)} chars)\n")
    else:
        print("  ❌ Homepage failed\n")
        return {
            "error": "Could not fetch homepage",
            "pages_checked": 0,
            "sroi_compliant": False,
            "confidence": "none",
            "score": 0,
        }
    
    # ============================================================
    # STAP 2: Probeer standaard URL's
    # ============================================================
    standard_pages = discover_standard_pages(start_url)
    
    for url, category in standard_pages:
        if normalize_url(url) not in pages_scraped:
            pages_to_scrape.append((url, f"standard_{category}"))
    
    print(f"\n  📊 Found {len(standard_pages)} standard pages\n")
    
    # ============================================================
    # STAP 3: Voor elke standaard pagina, zoek sub-links
    # ============================================================
    print("🔗 STEP 2: Scanning standard pages for sub-links...")
    
    for page_url, category in standard_pages:
        if len(pages_to_scrape) >= MAX_PAGES_TO_CHECK:
            break
        
        time.sleep(DELAY_BETWEEN_REQUESTS)
        
        print(f"\n  📄 Scanning: {page_url}")
        page_soup = fetch_page_content(page_url)
        
        if page_soup:
            sublinks = find_sublinks_on_page(page_url, page_soup, max_depth=2)
            
            if sublinks:
                print(f"     Found {len(sublinks)} sub-links:")
                for sublink_url, sublink_cat in sublinks:
                    if normalize_url(sublink_url) not in pages_scraped and \
                       len(pages_to_scrape) < MAX_PAGES_TO_CHECK:
                        pages_to_scrape.append((sublink_url, f"sublink_{sublink_cat}"))
                        print(f"       ↳ [{sublink_cat}] {sublink_url}")
            else:
                print(f"     No relevant sub-links")
    
    # ============================================================
    # STAP 4: Fallback - scan homepage links als te weinig gevonden
    # ============================================================
    if len(pages_to_scrape) < 3:
        print(f"\n⚠️  STEP 3: Only {len(pages_to_scrape)} pages found, scanning homepage links as fallback...")
        
        homepage_links = find_relevant_links(
            homepage_soup, 
            start_url, 
            max_links=MAX_PAGES_TO_CHECK - len(pages_to_scrape)
        )
        
        for link in homepage_links:
            if normalize_url(link) not in pages_scraped:
                pages_to_scrape.append((link, "homepage_fallback"))
    
    # ============================================================
    # STAP 5: Scrape alle verzamelde pagina's
    # ============================================================
    print(f"\n{'='*80}")
    print(f"📥 STEP 4: Scraping {len(pages_to_scrape)} discovered pages...")
    print(f"{'='*80}\n")
    
    for i, (page_url, source) in enumerate(pages_to_scrape, 1):
        page_norm = normalize_url(page_url)
        
        if page_norm in pages_scraped:
            continue
        
        time.sleep(DELAY_BETWEEN_REQUESTS)
        
        print(f"{i}/{len(pages_to_scrape)} [{source}] {page_url}")
        
        page_soup = fetch_page_content(page_url)
        if page_soup:
            page_text = extract_text_content(page_soup)
            all_text.append(page_text)
            pages_scraped.add(page_norm)
            print(f"       ✅ {len(page_text)} chars\n")
        else:
            print(f"       ❌ Failed\n")
    
    # ============================================================
    # STAP 6: Check of we genoeg content hebben
    # ============================================================
    if not all_text:
        return {
            "error": "No content scraped",
            "pages_checked": 0,
            "sroi_compliant": False,
            "confidence": "none",
            "score": 0,
        }
    
    combined_text = " ".join(all_text)
    
    print(f"{'='*80}")
    print(f"📊 SCRAPING SUMMARY:")
    print(f"   • Total pages scraped: {len(pages_scraped)}")
    print(f"   • Total characters: {len(combined_text):,}")
    print(f"   • Avg chars per page: {len(combined_text) // len(pages_scraped):,}")
    print(f"{'='*80}\n")
    
    # ============================================================
    # STAP 7: AI Analysis
    # ============================================================
    print("🤖 STEP 5: Analyzing with AI...\n")
    analysis = analyze_with_ai(company_name, combined_text)
    
    analysis["pages_checked"] = len(pages_scraped)
    analysis["urls_checked"] = list(pages_scraped)
    
    return analysis


from urllib.parse import urlparse, urlunparse

def get_site_root(url: str) -> str:
    p = urlparse(url)
    return f"{p.scheme}://{p.netloc}/"


# --------------------------
# Notice-level helpers
# --------------------------

def analyze_notice_sroi(notice: Dict) -> Dict:
    """
    Analyze a single notice for SROI compliance.
    NU MET HYBRIDE STRATEGIE
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
        "error": None,
    }

    target_name = notice.get("win_bedrijf_naam")
    target_url = clean_url(notice.get("win_website"))

    if not target_name:
        target_name = notice.get("buyer_bedrijf_naam")
        target_url = clean_url(notice.get("buyer_website"))

    if not target_name:
        result["error"] = "Geen bedrijfsnaam beschikbaar"
        return result

    print(f"🔎 Resolving URL for: {target_name}")
    resolved_url, url_source = find_first_working_url(target_name, target_url)

    if not resolved_url:
        result["error"] = "Geen werkende URL gevonden"
        return result

    site_root = get_site_root(resolved_url)

    result["analyzed_url"] = site_root
    result["url_source"] = url_source

    try:
        # Gebruik hybride strategie
        analysis = smart_scrape_and_analyze_hybrid(target_name, site_root)
        
        result.update({
            "sroi_compliant": analysis.get("sroi_compliant", False),
            "confidence": analysis.get("confidence", "none"),
            "score": analysis.get("score", 0),
            "evidence": analysis.get("evidence", []),
            "summary": analysis.get("summary", ""),
            "pages_checked": analysis.get("pages_checked", 0),
            "error": analysis.get("error"),
            "analysis_method": analysis.get("analysis_method"),
            "verdict": analysis.get("verdict"),
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
    results: List[Dict] = []
    total = len(notices)

    print(f"Starting SROI analysis for {total} notices...")

    for idx, notice in enumerate(notices):
        print(f"\n{'=' * 80}")
        print(f"Analyzing {idx + 1}/{total}")

        result = analyze_notice_sroi(notice)
        results.append(result)

        if progress_callback:
            progress_callback(idx + 1, total, result)

        if idx < total - 1:
            time.sleep(1)

    compliant_count = sum(1 for r in results if r["sroi_compliant"])
    avg_score = sum(r.get("score", 0) for r in results) / len(results) if results else 0

    print(f"\n{'=' * 80}")
    print(f"✅ Analysis complete!")
    print(f"   SROI Compliant: {compliant_count}/{total} ({compliant_count / total * 100:.1f}%)")
    print(f"   Average Score: {avg_score:.1f}")
    print(f"{'=' * 80}")

    return results



import re
from urllib.parse import urljoin, urlparse
from typing import List, Set

def normalize_url(url: str) -> str:
    """Normalize URL for comparison."""
    if not url:
        return url
    from urllib.parse import urlparse, urlunparse
    parsed = urlparse(url)
    parsed = parsed._replace(fragment="", query="")
    cleaned = urlunparse(parsed)
    return cleaned.rstrip("/")

def get_domain(url: str) -> str:
    """Extract domain from URL."""
    parsed = urlparse(url)
    return parsed.netloc


def discover_standard_pages(base_url: str) -> List[Tuple[str, str]]:
    """
    Probeer systematisch standaard URL-paden.
    
    Returns:
        List van (url, category) tuples voor bestaande pagina's
    """
    
    STANDARD_PATHS = {
        'about': [
            '/over-ons', '/overons', '/over-ons/', '/about', '/about-us', '/about/',
            '/wie-zijn-wij', '/organisatie', '/bedrijf', '/company',
            '/nl/over-ons', '/en/about', '/nl/over-ons/', '/en/about/',
        ],
        'sustainability': [
            '/duurzaamheid', '/mvo', '/csr', '/sustainability', '/verantwoordelijkheid',
            '/maatschappelijk-verantwoord-ondernemen', '/impact', '/sociale-impact',
            '/duurzaam', '/nl/duurzaamheid', '/en/sustainability',
        ],
        'careers': [
            '/werken-bij', '/werkenbij', '/werken-bij-ons', '/vacatures', '/vacature',
            '/jobs', '/careers', '/carriere', '/werk', '/werken',
            '/nl/werken-bij', '/en/careers', '/nl/vacatures', '/en/jobs',
        ],
        'mission': [
            '/missie', '/visie', '/missie-visie', '/onze-missie',
            '/mission', '/vision', '/our-mission', '/strategie', '/strategy',
        ],
        'sroi': [
            '/sroi', '/social-return', '/sociale-return', '/participatie',
            '/maatschappelijke-participatie', '/inclusie', '/inclusief',
        ],
    }
    
    print(f"\n🔍 Step 1: Probing standard URL paths on {base_url}...")
    
    discovered: List[Tuple[str, str]] = []
    
    for category, paths in STANDARD_PATHS.items():
        for path in paths:
            time.sleep(0.2)  # Netjes blijven
            
            full_url = urljoin(base_url, path)
            
            try:
                response = requests.head(
                    full_url,
                    headers={'User-Agent': 'Mozilla/5.0'},
                    timeout=5,
                    allow_redirects=True
                )
                
                if response.status_code == 200:
                    discovered.append((full_url, category))
                    print(f"  ✅ [{category.upper()}] {full_url}")
                    break  # Stop na eerste hit per categorie
                    
            except:
                pass  # Stil falen
    
    return discovered


def find_sublinks_on_page(page_url: str, page_soup, max_depth: int = 2) -> List[Tuple[str, str]]:
    """
    Zoek op een specifieke pagina naar relevante sub-links.
    Bijvoorbeeld op /over-ons zoeken naar /over-ons/duurzaamheid
    
    Args:
        page_url: URL van de pagina die we aan het scrapen zijn
        page_soup: BeautifulSoup object van de pagina
        max_depth: Max aantal / in de URL-path vanaf de parent
        
    Returns:
        List van (url, category) tuples
    """
    
    if not page_soup:
        return []
    
    domain = get_domain(page_url)
    page_path = urlparse(page_url).path.rstrip('/')
    
    # Patronen voor sub-pagina's
    SUBPAGE_PATTERNS = {
        'sustainability': [
            r'duurzaam', r'mvo', r'csr', r'sustainability', r'verantwoord',
            r'impact', r'milieu', r'environment', r'klimaat', r'climate',
        ],
        'sroi': [
            r'sroi', r'social-return', r'participatie', r'inclusie', r'inclusief',
            r'sociale-return', r'maatschappelijk', r'sociaal',
        ],
        'mission': [
            r'missie', r'visie', r'mission', r'vision', r'strategie', r'strategy',
            r'waarden', r'values', r'kernwaarden',
        ],
        'team': [
            r'team', r'mensen', r'medewerkers', r'people', r'organisatie',
        ],
        'careers_sub': [
            r'diversiteit', r'diversity', r'inclusie', r'stage', r'trainee',
            r'ontwikkeling', r'development', r'cultuur', r'culture',
        ]
    }
    
    found_sublinks: List[Tuple[str, str]] = []
    seen: Set[str] = set()
    
    for a_tag in page_soup.find_all("a", href=True):
        raw_href = a_tag["href"]
        full_url = urljoin(page_url, raw_href)
        
        # Moet op zelfde domain zijn
        if get_domain(full_url) != domain:
            continue
        
        full_norm = normalize_url(full_url)
        
        # Skip dupes en zichzelf
        if full_norm in seen or full_norm == normalize_url(page_url):
            continue
        
        sub_path = urlparse(full_norm).path.rstrip('/')
        
        # Moet een sub-path zijn van de huidige pagina
        if not sub_path.startswith(page_path + '/'):
            continue
        
        # Check depth (max 2 niveaus dieper)
        relative_path = sub_path[len(page_path):].strip('/')
        depth = relative_path.count('/')
        if depth >= max_depth:
            continue
        
        # Skip bijlagen
        if any(ext in sub_path.lower() for ext in ['.pdf', '.jpg', '.png', '.doc', '.xls', '.zip']):
            continue
        
        # Match tegen patronen
        href_lower = raw_href.lower()
        text_lower = (a_tag.get_text(strip=True) or "").lower()
        
        for category, patterns in SUBPAGE_PATTERNS.items():
            for pattern in patterns:
                if re.search(pattern, href_lower, re.IGNORECASE) or \
                   re.search(pattern, text_lower, re.IGNORECASE):
                    found_sublinks.append((full_norm, category))
                    seen.add(full_norm)
                    break
            if full_norm in seen:
                break
    
    return found_sublinks


def find_relevant_links(soup, base_url: str, max_links: int) -> List[str]:
    """
    Zoek gericht naar pagina's in prioriteitsvolgorde:
    1) SROI / sociaal / participatie
    2) MVO / duurzaamheid / impact
    3) Over ons / missie / visie  ← PRIORITEIT!
    4) Werken bij / vacatures
    5) Nieuws / blogs (max 2)
    
    Verbeterde versie met betere pattern matching.
    """
    
    if not soup:
        return []

    domain = get_domain(base_url)
    base_norm = normalize_url(base_url)

    # Patronen per categorie - met word boundaries en specifiekere matches
    PATTERNS_SROI = {
        # Directe URL patronen (case insensitive via re.IGNORECASE later)
        'url': [
            r'/sroi\b',
            r'/social-return\b',
            r'/sociale-return\b',
            r'/participatie\b',
            r'/inclusie\b',
            r'/sociale-impact\b',
            r'/maatschappelijk\b',
        ],
        # Text patronen
        'text': ['social return', 'sroi', 'participatie', 'inclusie']
    }

    PATTERNS_MVO = {
        'url': [
            r'/mvo\b',
            r'/csr\b',
            r'/duurzaam',
            r'/sustainability\b',
            r'/impact\b',
            r'/maatschappelijk',
        ],
        'text': ['mvo', 'csr', 'duurzaamheid', 'sustainability', 'maatschappelijk']
    }

    PATTERNS_ABOUT = {
        'url': [
            r'/over-ons\b',
            r'/over-\w+\b',  # /over-bedrijfsnaam
            r'/about\b',
            r'/about-us\b',
            r'/wie-zijn-wij\b',
            r'/missie\b',
            r'/visie\b',
            r'/onze-missie\b',
            r'/mission\b',
            r'/vision\b',
            r'/company\b',
        ],
        'text': ['over ons', 'about us', 'wie zijn wij', 'missie', 'visie', 'onze organisatie']
    }

    PATTERNS_HR = {
        'url': [
            r'/werken-bij\b',
            r'/vacature',
            r'/jobs?\b',
            r'/careers?\b',
            r'/werkenbij\b',
        ],
        'text': ['werken bij', 'vacatures', 'careers', 'jobs', 'werken bij ons']
    }

    PATTERNS_NEWS = {
        'url': [
            r'/nieuws\b',
            r'/news\b',
            r'/blog\b',
            r'/artikel',
        ],
        'text': ['nieuws', 'news', 'blog', 'artikel']
    }

    def matches_url_patterns(patterns: List[str], href_lower: str) -> bool:
        """Check if URL matches any regex pattern."""
        for pattern in patterns:
            if re.search(pattern, href_lower, re.IGNORECASE):
                return True
        return False

    def matches_text_patterns(patterns: List[str], text_lower: str) -> bool:
        """Check if text contains any pattern (whole word)."""
        for pattern in patterns:
            # Use word boundaries for text matching
            if re.search(r'\b' + re.escape(pattern) + r'\b', text_lower, re.IGNORECASE):
                return True
        return False

    # Categorie-buckets
    sroi_links = []
    mvo_links = []
    about_links = []
    hr_links = []
    news_links = []
    other_links = []  # Fallback voor algemene interne links

    seen: Set[str] = set()

    print(f"\n🔗 Scanning links on {base_url}...")

    for a_tag in soup.find_all("a", href=True):
        raw_href = a_tag["href"]
        full_url = urljoin(base_url, raw_href)

        # Skip externe domains
        if get_domain(full_url) != domain:
            continue

        full_norm = normalize_url(full_url)
        
        # Skip homepage en dupes
        if full_norm == base_norm or full_norm in seen:
            continue

        href_lower = raw_href.lower()
        text_lower = (a_tag.get_text(strip=True) or "").lower()

        # Skip duidelijke bijlagen
        if any(ext in href_lower for ext in ['.pdf', '.jpg', '.jpeg', '.png', '.gif', '.doc', '.docx', '.xls', '.xlsx', '.zip']):
            continue

        # Skip anchors zonder path (bijv. #sectie)
        if raw_href.strip().startswith('#'):
            continue

        # Determine bucket - prioritize URL patterns over text
        bucket = None
        category = None
        
        # Check in priority order
        if matches_url_patterns(PATTERNS_SROI['url'], href_lower) or matches_text_patterns(PATTERNS_SROI['text'], text_lower):
            bucket = sroi_links
            category = "SROI"
        elif matches_url_patterns(PATTERNS_MVO['url'], href_lower) or matches_text_patterns(PATTERNS_MVO['text'], text_lower):
            bucket = mvo_links
            category = "MVO"
        elif matches_url_patterns(PATTERNS_ABOUT['url'], href_lower) or matches_text_patterns(PATTERNS_ABOUT['text'], text_lower):
            bucket = about_links
            category = "ABOUT"
        elif matches_url_patterns(PATTERNS_HR['url'], href_lower) or matches_text_patterns(PATTERNS_HR['text'], text_lower):
            bucket = hr_links
            category = "HR"
        elif matches_url_patterns(PATTERNS_NEWS['url'], href_lower) or matches_text_patterns(PATTERNS_NEWS['text'], text_lower):
            bucket = news_links
            category = "NEWS"
        else:
            # Fallback: algemene interne link (niet te diep genest)
            path_depth = full_url.count('/') - 2  # -2 voor https://
            if path_depth <= 2:  # Max 2 niveaus diep
                bucket = other_links
                category = "OTHER"

        if bucket is not None:
            bucket.append(full_norm)
            seen.add(full_norm)
            print(f"  ✓ [{category}] {full_norm[:80]}")

    # Print summary
    print(f"\n📊 Link categorieën gevonden:")
    print(f"   SROI: {len(sroi_links)}")
    print(f"   MVO: {len(mvo_links)}")
    print(f"   ABOUT: {len(about_links)}")
    print(f"   HR: {len(hr_links)}")
    print(f"   NEWS: {len(news_links)}")
    print(f"   OTHER: {len(other_links)}")

    # Nu in prioriteitsvolgorde vullen
    selected: List[str] = []

    def take_from(bucket: List[str], limit: int = 999, label: str = ""):
        """Take links from bucket up to limit."""
        taken = 0
        for url in bucket:
            if len(selected) >= max_links:
                return
            if taken >= limit:
                return
            selected.append(url)
            taken += 1
            if label:
                print(f"  → Selected [{label}]: {url[:80]}")

    print(f"\n🎯 Selecting top {max_links} links...")

    # Prioriteitsvolgorde met limieten per categorie
    take_from(sroi_links, limit=2, label="SROI")
    take_from(mvo_links, limit=2, label="MVO")
    take_from(about_links, limit=2, label="ABOUT")  # ← BELANGRIJKSTE!
    take_from(hr_links, limit=1, label="HR")
    take_from(news_links, limit=1, label="NEWS")
    
    # Als we nog ruimte hebben, vul aan met OTHER
    if len(selected) < max_links:
        take_from(other_links, limit=max_links - len(selected), label="OTHER")

    print(f"\n✅ Total selected: {len(selected)} links\n")

    return selected
