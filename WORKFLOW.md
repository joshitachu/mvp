## Project workflow — van A naar B

Dit document beschrijft hoe data in dit project stroomt, welke componenten betrokken zijn en wat de belangrijke foutafhandelings- en teststappen zijn. De workflow is geschreven op basis van de huidige codebase (bestanden zoals `server.py`, `sroi_scanner.py`, `insert_db.py`, `data.py`, en de XML-bestanden in `xml_gegund/`).

### Kernbegrippen (contract)
- Input (A): raw notice data — dit kan komen uit:
  - XML-bestanden in `xml_gegund/` (voor lokale imports)
  - de TenderNed scraper via `final_tenderned.run_import()` die door `server.py` wordt aangeroepen
- Output (B): opgeslagen records en analyses in Supabase:
  - `notices` tabel (notices/upserts via `server.py`)
  - `imports` tabel (import metadata)
  - optioneel: `sroi_results` tabel (resultaten van SROI-analyse uitgevoerd door `sroi_scanner.py`)
- Succescriteria: B is zichtbaar in Supabase (records aanwezig), import heeft juiste `import_id`, en SROI-analyse (indien aangevinkt) is afgerond of in foutstatus met logging.

### Stappen in de pipeline (lineair)
1. Ontvangst / starten import
   - Actor: `server.py` endpoint POST `/imports`.
   - Input: `ImportRequest` payload (date_from, date_to, region, cpv_codes, etc.).
   - Actie: maakt `imports` record in Supabase en roept `run_import(...)` aan (in `final_tenderned.py`).

2. Scrape / lees notices (run_import)
   - Actor: `final_tenderned.run_import()` (scraper code, buitenstaand bestand).
   - Output: lijst met notice-dicts (velden zoals `notice_id`, `titel`, `URL`, `win_bedrijf_naam`, `win_plaats`, etc.).

3. Mapping & filter
   - Actor: `server.py` (in `start_import`): berekent province via `map_city_to_province`, filtert op `region` indien opgegeven, en bepaalt historische aanbestedingen met `_search_companies_in_db`.

4. Upsert naar Supabase
   - Actor: `server.py` — deduplicate op `notice_id` en `upsert` naar `notices` tabel.
   - Update: `imports.total_records` bijgewerkt met aantal verwerkte notices.

5. SROI-analyse (optioneel/asynchroon)
   - Actor: `sroi_scanner.py` (functie `analyze_import_sroi` wordt vanuit `server.py` verwacht te kunnen worden aangeroepen als achtergrondtask).
   - Acties: voor elk bedrijf wordt geprobeerd een werkende bedrijfs-URL te vinden (direct URL, SerpAPI, Google CSE), sitecontent wordt gefetcht en geanalyseerd (keyword fallback of LLM via Groq/Gemini). Resultaat wordt geschreven naar `sroi_results`.

6. Notificatie & monitoring
   - Actor: `server.py` en observability (logs/prints). Gebruik correlation-id `import_id` om events traceerbaar te maken.

7. Cleanup
   - Temporary files verwijderen, resources vrijgeven. Eventuele mislukte notices markeren voor handmatige review.

### Beslispunten & retrybeleid
- Validatie van input (in `server.py`) → bij invalid: zet import op `failed` of `invalid` en notify.
- Externe request failures in `sroi_scanner.py`: retry met exponential backoff (bv. 1s, 2s, 4s) max N=5.
- Idempotentie: endpoints en jobs moeten een idempotency-key gebruiken (gebruik `import_id` + `notice_id`).
- Lange taken: voer SROI-analyse als achtergrondtaak (FastAPI `BackgroundTasks` of een queue zoals RQ/Celery).

### Observability & metrics (aanbevolen)
- Log events per stap met `import_id` en `notice_id`.
- Metrics: aantal records per import, latency per stap, aantal retries, error-rate.
- Alerts: hoge error-rate, lange looptijd taken, of max retries bereikt.

### Mermaid diagram (plakbaar in editors die Mermaid ondersteunen)
```mermaid
flowchart TD
  A[Start: POST /imports (payload)] -->|create imports row| RUN[run_import()
  ]
  RUN -->|notices list| MAP[Mapping & filter in server.py]
  MAP --> DB[Upsert naar Supabase notices table]
  DB --> SROI[SROI-analyse (sroi_scanner.py) — background]
  SROI --> SR[Write sroi_results to Supabase]
  DB --> Notify[Notificatie & logging]
  Notify --> End[Cleanup & done]
  MAP -->|skip invalid| Invalid[Store invalid / manual review]
  SROI -->|fail after retries| Esc[Escalatie -> operator]
```

### Concrete file-referenties en waar wat gebeurt
- `server.py`: API endpoints, import-orchestratie, mapping, upsert naar `notices` en `imports`.
- `final_tenderned.py`: scraper die notices verzamelt (wordt door `server.py` aangeroepen).
- `sroi_scanner.py`: SROI-analyse en scraping/enrichment van bedrijfswebsites.
- `insert_db.py` / `data.py`: tools om historische datasets en Excel-imports naar Supabase te brengen.
- `xml_gegund/`: lokale XML notices (mogelijke inputbron voor offline import).

### Edge-cases en aanbevelingen
- Dubbele ingestuurde notices: gebruik `upsert` met `on_conflict=notice_id` (reeds gebruikt in `server.py`).
- Grote payloads: shift naar asynchrone verwerking en opslag in batches.
- Rate-limiting en blocking: implementeer polite scraping (delay, retries, user-agent) — `sroi_scanner.py` heeft DELAY en timeout constants.
- Externe API keys/private keys: bewaar in `.env` (zoals nu) en zorg dat niet in repo komt.

### Implementatie-checklist (directe acties)
1. Definieer officieel datastromen A→B: (A = XML / run_import output) → (B = `notices` + `sroi_results`).
2. Voeg correlation-id propagation toe: zorg dat `import_id` in logs en backgroundjobs meegaat.
3. Implementeer retry/backoff util (hergebruik in `sroi_scanner.py`).
4. Maak SROI-analyse async (BackgroundTasks of queue). Behandel idempotency.
5. Schrijf tests:
   - Unit: `map_city_to_province`, keyword_analysis
   - Integration: simulateer run_import -> upsert -> check Supabase mocks
   - Failure test: externe site 5xx -> retry -> fail
6. Voeg een eenvoudige dashboard-metric (prometheus or print) voor import durations.

### Testsuggesties (kort)
- Test 1 (happy path): run `start_import` met mock `run_import` (3 notices) en controleer dat `imports.total_records` en 3 `notices` worden ge-upsert.
- Test 2 (validation fail): geef ongeldige datum; verwacht 400/failed import.
- Test 3 (SROI fallback): simuleer website zonder LLM-toegang; verwacht keyword_analysis output en `sroi_results` geschreven.

---
Als je wilt, kan ik nu:
1) dit bestand committen naar de repo (gedaan) — en/of
2) extra taken uitvoeren: idempotency-key toevoegen in `server.py`, retry util in `sroi_scanner.py`, of tests toevoegen. Geef prioriteit en ik voer ze uit.

Opmerking: ik heb aannames gemaakt over de precieze inputs/outputs op basis van de code. Als je wilt dat ik het nauwkeuriger maak, geef dan aan of "A" specifiek de XML-bestanden in `xml_gegund/` zijn of de online scraper-output (`final_tenderned.run_import`).
