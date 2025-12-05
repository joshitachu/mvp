# sroi_ai_utils.py
import re
import json
import requests
import os

# --------------------------
# Config
# --------------------------
AI_PROVIDER = "groq"   # or "ollama", "together", or "none"
GROQ_API_KEY = os.environ.get("GROQ_API_KEY")
TOGETHER_API_KEY = "YOUR_TOGETHER_KEY_HERE"
OLLAMA_BASE_URL = ""
OLLAMA_MODEL = ""

# --------------------------
# Keyword definitions
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

ALL_KEYWORDS = list(set(
    SROI_PHRASES_DIRECT + PROCUREMENT_TERMS + SROI_TERMS + KPI_PHRASES
))

# --------------------------
# Keyword analysis (no LLM cost)
# --------------------------

def keyword_analysis(text: str):
    """Fallback / primary cheap analysis."""
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
        "score_breakdown": scores,
        "raw_score": total_score
    }

# --------------------------
# Cheap chunking to reduce LLM tokens
# --------------------------

def select_relevant_chunks(text: str, max_chars: int = 6000) -> str:
    """
    Split text in paragraphs, score them by # of SROI keywords,
    and keep the best ones until max_chars is reached.
    """
    paragraphs = re.split(r'(\n\s*\n|\. )', text)  # rough split
    scored = []
    text_lower = text.lower()
    
    for p in paragraphs:
        p_lower = p.lower()
        score = sum(1 for kw in ALL_KEYWORDS if kw.lower() in p_lower)
        if score > 0:
            scored.append((score, p))
    
    if not scored:
        # no SROI-like paragraphs, just truncate text
        return text[:max_chars]
    
    scored.sort(key=lambda x: x[0], reverse=True)
    
    selected = []
    total_len = 0
    for score, p in scored:
        if total_len + len(p) > max_chars:
            break
        selected.append(p)
        total_len += len(p)
    
    return "\n".join(selected)

# --------------------------
# LLM backends (optional)
# --------------------------

def analyze_with_ollama(company_name, text_content):
    filtered_text = select_relevant_chunks(text_content, max_chars=6000)
    prompt = f"""Analyseer of bedrijf "{company_name}" SROI-compliant is.

SROI = Social Return on Investment (sociale werkgelegenheid, participatiedoelgroepen)

Relevante tekst:
{filtered_text}

Geef JSON response:
{{
  "sroi_compliant": true/false,
  "confidence": "high/medium/low",
  "evidence": ["gevonden bewijzen"],
  "summary": "korte Nederlandse samenvatting"
}}

ALLEEN JSON, geen extra tekst."""
    try:
        resp = requests.post(
            f"{OLLAMA_BASE_URL}/api/generate",
            json={"model": OLLAMA_MODEL, "prompt": prompt, "stream": False, "format": "json"},
            timeout=60
        )
        if resp.status_code == 200:
            result = resp.json()
            return json.loads(result["response"])
    except Exception as e:
        print("❌ Ollama error:", e)
    # fallback
    return keyword_analysis(text_content)

def analyze_with_groq(company_name, text_content):
    if not GROQ_API_KEY or GROQ_API_KEY.startswith("YOUR_"):
        return keyword_analysis(text_content)
    
    filtered_text = select_relevant_chunks(text_content, max_chars=6000)

    prompt = f"""Analyseer of bedrijf "{company_name}" SROI-compliant is.

SROI = Social Return on Investment (sociale werkgelegenheid, participatiedoelgroepen)

Relevante (gefilterde) tekst:
{filtered_text}

Geef JSON response:
{{
  "sroi_compliant": true/false,
  "confidence": "high/medium/low",
  "evidence": ["lijst van bewijzen"],
  "summary": "Nederlandse samenvatting"
}}

ALLEEN JSON response."""
    try:
        headers = {
            "Authorization": f"Bearer {GROQ_API_KEY}",
            "Content-Type": "application/json"
        }
        data = {
            "model": "llama-3.3-70b-versatile",
            "messages": [{"role": "user", "content": prompt}],
            "temperature": 0.1,
            "max_tokens": 600,
            "response_format": {"type": "json_object"}
        }
        resp = requests.post(
            "https://api.groq.com/openai/v1/chat/completions",
            headers=headers,
            json=data,
            timeout=30
        )
        if resp.status_code == 200:
            result = resp.json()
            txt = result["choices"][0]["message"]["content"]
            return json.loads(txt)
    except Exception as e:
        print("❌ Groq error:", e)
    return keyword_analysis(text_content)

def analyze_with_together(company_name, text_content):
    if not TOGETHER_API_KEY or TOGETHER_API_KEY.startswith("YOUR_"):
        return keyword_analysis(text_content)
    
    filtered_text = select_relevant_chunks(text_content, max_chars=6000)
    prompt = f"""Analyseer of bedrijf "{company_name}" SROI-compliant is.

Relevante tekst:
{filtered_text}

Geef JSON:
{{
  "sroi_compliant": true/false,
  "confidence": "high/medium/low",
  "evidence": ["bewijzen"],
  "summary": "samenvatting"
}}

ALLEEN JSON."""
    try:
        headers = {
            "Authorization": f"Bearer {TOGETHER_API_KEY}",
            "Content-Type": "application/json"
        }
        data = {
            "model": "meta-llama/Meta-Llama-3.1-8B-Instruct-Turbo",
            "messages": [{"role": "user", "content": prompt}],
            "temperature": 0.1,
            "max_tokens": 600
        }
        resp = requests.post(
            "https://api.together.xyz/v1/chat/completions",
            headers=headers,
            json=data,
            timeout=30
        )
        if resp.status_code == 200:
            result = resp.json()
            txt = result["choices"][0]["message"]["content"]
            txt = re.sub(r'```json\s*|\s*```', '', txt)
            return json.loads(txt)
    except Exception as e:
        print("❌ Together error:", e)
    return keyword_analysis(text_content)

def analyze_with_ai(company_name: str, text_content: str):
    """
    ROUTER: first do keyword analysis, only call LLM if score is "maybe".
    This keeps costs low.
    """
    base = keyword_analysis(text_content)
    
    # If clearly no SROI (very low score) or clearly yes (very high), skip LLM:
    if base["raw_score"] <= 2:
        base["verdict_source"] = "keyword_only_low_score"
        return base
    if base["raw_score"] >= 12:
        base["verdict_source"] = "keyword_only_high_score"
        return base
    
    # Ambiguous middle → optional LLM refinement
    if AI_PROVIDER == "ollama":
        llm = analyze_with_ollama(company_name, text_content)
    elif AI_PROVIDER == "groq":
        llm = analyze_with_groq(company_name, text_content)
    elif AI_PROVIDER == "together":
        llm = analyze_with_together(company_name, text_content)
    else:
        base["verdict_source"] = "keyword_only_provider_none"
        return base
    
    # Merge LLM result with base score
    llm["keyword_score"] = base["raw_score"]
    llm["keyword_evidence"] = base["evidence"]
    llm["verdict_source"] = f"{AI_PROVIDER}_plus_keywords"
    return llm
