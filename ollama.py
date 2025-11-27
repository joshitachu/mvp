import requests
import json
import time

# --------------------------
# CONFIG
# --------------------------
OLLAMA_URL = "http://192.168.2.168:11434/api/chat"  # PC IP with Ollama
MODEL_NAME = "llama3.1:8b"  # or whatever model you’re actually running

# --------------------------
# TEST INPUT FOR YOUR USE CASE
# --------------------------
company_name = "Voorbeeld BV"

# Replace this with real scraped text when testing for real
text_content = """
Voorbeeld BV is een sociaal betrokken organisatie. Wij werken samen met gemeenten en sociale partners
om mensen met een afstand tot de arbeidsmarkt te begeleiden naar werk. Via leer-werktrajecten, stageplaatsen
en beschut werk creëren wij kansen voor participatiedoelgroepen. In diverse aanbestedingen hebben wij
Social Return afspraken gemaakt over het inzetten van FTE en opleidingsuren.
"""

# Build the same kind of prompt you use in analyze_with_groq
prompt = f"""
**ROL:** U bent een ervaren SROI (Social Return on Investment) compliance analist voor de Nederlandse aanbestedingsmarkt. Uw taak is om de publieke website van een bedrijf te analyseren op bewijs van een actief en meetbaar SROI-beleid.

**DOEL:** Bepaal of bedrijf "{company_name}" waarschijnlijk SROI-compliant is, gebaseerd op de onderstaande criteria en de geleverde webtekst.

---

### SROI DEFINITIE & FOCUS (Nederlandse Context)
SROI in deze context betekent de verplichte inzet of bijdrage aan sociale doelstellingen, meestal in het kader van een gegunde overheidsopdracht (aanbesteding). Dit omvat:
1.  **Arbeidsplaatsen:** Het creëren van werkgelegenheid voor personen met een afstand tot de arbeidsmarkt (participatiedoelgroepen).
2.  **Meting:** Het aantoonbaar meten en rapporteren van de SROI-prestatie (uren, FTE, ingevulde leer-werkplekken).
3.  **Beleid:** Expliciete vermelding van Social Return, SROI, of een vergelijkbaar Maatschappelijk Verantwoord Ondernemen (MVO) beleid dat zich richt op *inclusieve arbeid*.

### CRITERIA VOOR 'SROI-COMPLIANT':
Het bedrijf is 'sroi_compliant: true' als het bewijs levert voor **een of meer** van de volgende punten:
* **Directe vermelding:** Expliciete vermelding van "Social Return", "SROI", of "SROI-verplichting" in relatie tot aanbestedingen, projecten of beleid.
* **Meetbare Inzet:** Vermelding van KPI's, targets, of gerealiseerde cijfers zoals "x FTE ingevuld", "uren sociale inzet", "monitoring van SROI-resultaten".
* **Doelgroep Focus:** Actieve communicatie over het werken met "participatiedoelgroepen", "mensen met een afstand tot de arbeidsmarkt", "Wajong", of "leer-werkplekken" in een beleidsmatige context.
* **Gunning Relatie:** De vermelding van SROI als onderdeel van het winnen of uitvoeren van een overheidsopdracht.

### INSTRUCTIES
1. Lees de volledige webtekst grondig.
2. Zoek specifiek naar de termen en concepten zoals hierboven gedefinieerd.
3. Wijs een 'score' toe van 0 tot 100.
    * **Score 0-30:** Geen tot minimale aanwijzingen. (Vb. Alleen algemeen MVO.)
    * **Score 31-60:** Enkele aanwijzingen, maar niet meetbaar of expliciet SROI. (Vb. Goede doelen steunen.)
    * **Score 61-85:** Duidelijk SROI-beleid of -activiteit, maar zonder harde KPI's.
    * **Score 86-100:** Expliciet SROI-beleid met concrete, meetbare resultaten of sterke commitment.

Website tekst om te analyseren:
---
{text_content[:8000]}
---

**BELANGRIJK:**
Geef **ALLEEN** een geldig JSON-object terug, zonder extra tekst, uitleg of codeblokken.

Schema:

{{
  "sroi_compliant": true/false,
  "confidence": "high" | "medium" | "low",
  "evidence": ["max 5 zinnen of zinsdelen uit de tekst, in het Nederlands"],
  "summary": "Korte professionele Nederlandse samenvatting van de bevindingen t.a.v. SROI.",
  "score": 0-100
}}
"""

# --------------------------
# BUILD PAYLOAD FOR OLLAMA /api/chat
# --------------------------
payload = {
    "model": MODEL_NAME,
    "messages": [
        # You can also add a system message here if you like:
        # {"role": "system", "content": "You are a JSON-only SROI compliance analyzer."},
        {"role": "user", "content": prompt}
    ],
    # Ollama supports streaming for /api/chat
    "stream": True
}

print(f"Sending request to {OLLAMA_URL} using model '{MODEL_NAME}' ...")

start_time = time.time()
first_token_time = None
all_content = []

response = requests.post(OLLAMA_URL, json=payload, stream=True)

if response.status_code == 200:
    print("Streaming response from Ollama:\n")
    for line in response.iter_lines(decode_unicode=True):
        if line:
            if first_token_time is None:
                first_token_time = time.time()
            try:
                json_data = json.loads(line)
                # Each chunk may contain new content
                if "message" in json_data and "content" in json_data["message"]:
                    chunk = json_data["message"]["content"]
                    all_content.append(chunk)
                    print(chunk, end="")  # stream to console
            except json.JSONDecodeError:
                print(f"\nFailed to parse line: {line}")
    print("\n")  # newline after streaming

    end_time = time.time()

    total_time = end_time - start_time
    ttfb = (first_token_time - start_time) if first_token_time else None
    stream_duration = (end_time - first_token_time) if first_token_time else None

    print("---------- TIMING ----------")
    print(f"Total request time      : {total_time:.2f} s")
    if ttfb is not None:
        print(f"Time to first token     : {ttfb:.2f} s")
        print(f"Streaming duration      : {stream_duration:.2f} s")
    print("----------------------------")

    # Join all chunks into a single string
    full_response = "".join(all_content)

    # Try to parse as JSON (since your use case expects JSON only)
    print("Trying to parse response as JSON ...")
    try:
        parsed = json.loads(full_response)
        print("✅ Valid JSON received.")
        print(json.dumps(parsed, indent=2, ensure_ascii=False))
    except json.JSONDecodeError as e:
        print("❌ Response was not valid JSON.")
        print("Raw response:\n", full_response)
        print("JSON error:", e)

else:
    print(f"Error: {response.status_code}")
    print(response.text)
