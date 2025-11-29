# serve.py
import os
import io
import json
import datetime as dt
from typing import Optional, List, Dict
from fastapi import FastAPI, HTTPException, Query, BackgroundTasks
from fastapi.responses import StreamingResponse
from pydantic import BaseModel
from supabase import create_client, Client
from datetime import datetime, timedelta
from collections import defaultdict
import csv

from dotenv import load_dotenv




# importeer run_import en helpers uit je scraper-bestand:
from final_tenderned import run_import  # pas de bestandsnaam aan
from sroi_scanner import analyze_import_sroi  # nieuwe SROI analyzer

# Load .env file
load_dotenv()

SUPABASE_URL = os.getenv("SUPABASE_URL")
SUPABASE_KEY = os.getenv("SUPABASE_KEY")

print(SUPABASE_KEY)
# Optional debug (verwijder later):

supabase: Client = create_client(SUPABASE_URL, SUPABASE_KEY)
app = FastAPI(title="TenderNed Import Backend")

# In-memory store voor SROI analysis progress tracking
sroi_analysis_status: Dict[str, Dict] = {}


# --------- Pydantic modellen ---------
class ImportRequest(BaseModel):
    date_from: str
    date_to: str
    publicatie_type: Optional[str] = "AGO"
    cpv_codes: Optional[List[str]] = None
    max_pages: Optional[int] = None
    region: Optional[str] = None  # ✅ Add this



class ImportResponse(BaseModel):
    import_id: str
    name: str
    total_records: int
    created_at: str


class SROIAnalysisStatus(BaseModel):
    import_id: str
    status: str  # "pending", "running", "completed", "failed"
    progress: int  # 0-100
    current: int
    total: int
    started_at: Optional[str] = None
    completed_at: Optional[str] = None
    results_summary: Optional[Dict] = None
    error: Optional[str] = None


# --------- Helpers ---------
def generate_import_name() -> str:
    now = dt.datetime.utcnow().replace(microsecond=0)
    return "import_" + now.isoformat().replace(":", "-")


def ensure_sroi_table():
    """
    Maak SROI results tabel als die niet bestaat.
    Supabase SQL migrations zijn beter, maar dit werkt voor snelle setup.
    """
    # Note: Je moet deze tabel handmatig aanmaken in Supabase dashboard:
    """
    CREATE TABLE IF NOT EXISTS sroi_results (
        id BIGSERIAL PRIMARY KEY,
        import_id TEXT NOT NULL REFERENCES imports(id) ON DELETE CASCADE,
        notice_id TEXT,
        publicatie_id TEXT,
        winner_name TEXT,
        analyzed_url TEXT,
        url_source TEXT,
        sroi_compliant BOOLEAN DEFAULT FALSE,
        confidence TEXT,
        score INTEGER DEFAULT 0,
        evidence JSONB,
        summary TEXT,
        pages_checked INTEGER DEFAULT 0,
        error TEXT,
        created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
    );
    
    CREATE INDEX IF NOT EXISTS idx_sroi_import_id ON sroi_results(import_id);
    CREATE INDEX IF NOT EXISTS idx_sroi_compliant ON sroi_results(sroi_compliant);
    """
    pass


# -----------------------------------------------
# Region / Province mapping helpers
# -----------------------------------------------
# A small mapping of Dutch provinces to example cities. This
# is not exhaustive but covers common cities seen in the dataset.
PROVINCE_TO_CITIES = {
    "Noord-Holland": [
        "Amsterdam", "Haarlem", "Alkmaar", "Zaanstad", "Hilversum", "Purmerend", "Hoorn", "Beverwijk", "Diemen", "Velsen",
        "Amstelveen", "Haarlemmermeer", "Heerhugowaard", "Langedijk", "Medemblik", "Schagen", "Enkhuizen", "Edam-Volendam",
        "Texel", "Bussum", "Huizen", "Blaricum", "Naarden", "Weesp", "Muiden", "Heemstede", "Bloemendaal", "Zandvoort",
        "Castricum", "Uitgeest", "Heiloo", "Bergen", "Ouder-Amstel", "Uithoorn", "Aalsmeer", "Landsmeer", "Waterland",
        "Oostzaan", "Wormerland", "Beemster", "Zeevang", "Koggenland", "Stede Broec", "Drechterland", "Opmeer", "Hollands Kroon",
        "Den Helder", "Heemskerk", "Uitgeest"
    ],
    "Zuid-Holland": [
        "Rotterdam", "Den Haag", "Leiden", "Delft", "Zoetermeer", "Dordrecht", "Gouda", "Schiedam", "Spijkenisse", "Vlaardingen",
        "Capelle aan den IJssel", "Alphen aan den Rijn", "Rijswijk", "Leidschendam-Voorburg", "Westland", "Katwijk", "Maassluis",
        "Krimpen aan den IJssel", "Pijnacker-Nootdorp", "Papendrecht", "Ridderkerk", "Hellevoetsluis", "Nissewaard", "Waddinxveen",
        "Nieuwkoop", "Voorschoten", "Wassenaar", "Zoeterwoude", "Lisse", "Noordwijk", "Teylingen", "Hillegom", "Oegstgeest",
        "Bodegraven-Reeuwijk", "Zuidplas", "Krimpenerwaard", "Alblasserdam", "Sliedrecht", "Zwijndrecht", "Hendrik-Ido-Ambacht",
        "Barendrecht", "Albrandswaard", "Lansingerland", "Westvoorne", "Brielle", "Goeree-Overflakkee", "Molenlanden",
        "Hoeksche Waard", "Gorinchem", "Hardinxveld-Giessendam", "Giessenlanden"
    ],
    "Utrecht": [
        "Utrecht", "Amersfoort", "Nieuwegein", "Veenendaal", "Zeist", "Houten", "Soest",
        "IJsselstein", "Woerden", "Wijk bij Duurstede", "De Bilt", "Bunnik", "Stichtse Vecht",
        "Vijfheerenlanden", "Montfoort", "Oudewater", "Lopik", "Renswoude", "Rhenen", "Woudenberg",
        "Leusden", "Bunschoten", "Baarn", "Eemnes", "De Ronde Venen", "Utrechtse Heuvelrug"
    ],
    "Noord-Brabant": [
        "Eindhoven", "Breda", "Tilburg", "s-Hertogenbosch", "Helmond", "Roosendaal", "Oss", "Bergen op Zoom", "Waalwijk",
        "Veldhoven", "Oosterhout", "Etten-Leur", "Uden", "Best", "Veghel", "Valkenswaard", "Boxmeer", "Geldrop-Mierlo",
        "Cuijk", "Heusden", "Boxtel", "Bernheze", "Eersel", "Oirschot", "Bladel", "Reusel-De Mierden", "Hilvarenbeek",
        "Goirle", "Oisterwijk", "Baarle-Nassau", "Alphen-Chaam", "Gilze en Rijen", "Dongen", "Loon op Zand", "Heeze-Leende",
        "Cranendonck", "Nuenen", "Son en Breugel", "Deurne", "Asten", "Someren", "Laarbeek", "Gemert-Bakel", "Sint-Michielsgestel",
        "Schijndel", "Meierijstad", "Landerd", "Boekel", "Mill en Sint Hubert", "Sint Anthonis", "Grave", "Wijchen", "Drimmelen",
        "Geertruidenberg", "Altena", "Werkendam", "Woudrichem", "Steenbergen", "Moerdijk", "Halderberge", "Zundert", "Rucphen",
        "Oosterhout", "Vught", "Oisterwijk"
    ],
    "Gelderland": [
        "Arnhem", "Nijmegen", "Apeldoorn", "Ede", "Doetinchem", "Zutphen",
        "Harderwijk", "Tiel", "Wageningen", "Zevenaar", "Duiven", "Barneveld", "Winterswijk", "Aalten", "Berkelland",
        "Bronckhorst", "Montferland", "Oude IJsselstreek", "Lochem", "Voorst", "Epe", "Hattem", "Heerde", "Oldebroek",
        "Elburg", "Ermelo", "Nunspeet", "Putten", "Nijkerk", "Scherpenzeel", "Renkum", "Rheden", "Rozendaal", "Lingewaard",
        "Overbetuwe", "West Maas en Waal", "Druten", "Wijchen", "Beuningen", "Heumen", "Mook en Middelaar", "Groesbeek",
        "Berg en Dal", "Culemborg", "Buren", "Neder-Betuwe", "West Betuwe", "Lingewaal", "Neerijnen", "Zaltbommel",
        "Maasdriel", "Tiel", "Brummen", "Westervoort", "Zevenaar", "Doesburg", "Oost Gelre", "Montferland", "Oude IJsselstreek"
    ],
    "Overijssel": [
        "Enschede", "Zwolle", "Deventer", "Almelo", "Hengelo", "Oldenzaal",
        "Kampen", "Hardenberg", "Dalfsen", "Raalte", "Hellendoorn", "Wierden", "Rijssen-Holten", "Borne", "Losser",
        "Haaksbergen", "Tubbergen", "Dinkelland", "Twenterand", "Olst-Wijhe", "Staphorst", "Zwartewaterland", "Steenwijkerland",
        "Ommen", "Olst-Wijhe"
    ],
    "Limburg": [
        "Maastricht", "Venlo", "Sittard-Geleen", "Heerlen", "Roermond", "Weert",
        "Venray", "Kerkrade", "Brunssum", "Landgraaf", "Voerendaal", "Simpelveld", "Vaals", "Gulpen-Wittem", "Valkenburg aan de Geul",
        "Eijsden-Margraten", "Maastricht", "Meerssen", "Beek", "Stein", "Meerssen", "Nederweert", "Leudal", "Echt-Susteren",
        "Maasgouw", "Roerdalen", "Peel en Maas", "Horst aan de Maas", "Venray", "Bergen", "Gennep", "Beesel", "Mook en Middelaar"
    ],
    "Friesland": [
        "Leeuwarden", "Heerenveen", "Drachten", "Sneek",
        "Smallingerland", "Súdwest-Fryslân", "Harlingen", "Franeker", "Dokkum", "Bolsward", "Lemsterland", "Skarsterlân",
        "Opsterland", "Ooststellingwerf", "Weststellingwerf", "Achtkarspelen", "Tytsjerksteradiel", "Kollumerland en Nieuwkruisland",
        "Dantumadiel", "Ferwerderadiel", "Menameradiel", "Het Bildt", "Franekeradeel", "Littenseradiel", "Wymbritseradiel",
        "Gaasterland-Sloten", "Lemsterland", "Nijefurd", "De Fryske Marren", "Waadhoeke", "Noardeast-Fryslân", "Ameland", "Schiermonnikoog", "Terschelling", "Vlieland"
    ],
    "Groningen": [
        "Groningen", "Delfzijl", "Hoogezand-Sappemeer",
        "Veendam", "Stadskanaal", "Winschoten", "Appingedam", "Pekela", "Oldambt", "Menterwolde", "Slochteren", "Haren",
        "Ten Boer", "Bedum", "Winsum", "De Marne", "Eemsmond", "Loppersum", "Zuidhorn", "Leek", "Marum", "Grootegast",
        "Vlagtwedde", "Bellingwedde", "Westerwolde", "Het Hoogeland", "Westerkwartier", "Midden-Groningen", "Eemsdelta"
    ],
    "Drenthe": [
        "Assen", "Emmen", "Hoogeveen",
        "Meppel", "Coevorden", "Borger-Odoorn", "Aa en Hunze", "Noordenveld", "Tynaarlo", "Midden-Drenthe", "Westerveld",
        "De Wolden"
    ],
    "Flevoland": [
        "Almere", "Lelystad", "Dronten",
        "Zeewolde", "Urk", "Noordoostpolder"
    ],
    "Zeeland": [
        "Middelburg", "Vlissingen", "Goes", "Terneuzen",
        "Hulst", "Sluis", "Borsele", "Kapelle", "Reimerswaal", "Veere", "Schouwen-Duiveland", "Tholen", "Noord-Beveland"
    ],
}

# Build reverse mapping city -> province for fast lookup (normalize to lower-case)
CITY_TO_PROVINCE = {}
for prov, cities in PROVINCE_TO_CITIES.items():
    for c in cities:
        CITY_TO_PROVINCE[c.lower()] = prov


def map_city_to_province(city: Optional[str]) -> Optional[str]:
    """
    Return province name for a given city string (case-insensitive).
    If city contains extra text (e.g. 'Amsterdam (NL)') we try to match substring.
    """
    if not city:
        return None
    city_norm = city.strip().lower()

    # Direct lookup
    if city_norm in CITY_TO_PROVINCE:
        return CITY_TO_PROVINCE[city_norm]

    # Try to match by startswith or contains for multi-word fields
    for known_city, prov in CITY_TO_PROVINCE.items():
        if known_city in city_norm:
            return prov

    return None


# --------- Endpoints ---------

@app.get("/health")
def health():
    return {"status": "ok"}


@app.get("/imports")
def list_imports():
    """
    Lijst eerdere imports (voor UI-overzicht).
    """
    resp = supabase.table("imports") \
        .select("*") \
        .order("created_at", desc=True) \
        .limit(50) \
        .execute()

    return resp.data
@app.post("/imports", response_model=ImportResponse)
def start_import(payload: ImportRequest):
    """
    Start een nieuwe import-run:
    - roept run_import(date_from, date_to, ...)
    - slaat import-meta + notices op in Supabase
    - zorgt via unieke constraint / upsert dat er geen dubbele records komen
    - filtert op region (province) als opgegeven
    - checkt per bedrijf of ze eerder aanbestedingen hebben gehad in TenderNed_filtered.csv
    """
    # 1) Maak import record
    name = generate_import_name()
    insert_resp = supabase.table("imports").insert({
        "name": name,
        "date_from": payload.date_from,
        "date_to": payload.date_to,
        "publicatie_type": payload.publicatie_type,
        "cpv_codes": payload.cpv_codes,
        "region": payload.region,
    }).execute()

    if not insert_resp.data:
        raise HTTPException(500, "Kon import-record niet aanmaken")

    import_row = insert_resp.data[0]
    import_id = import_row["id"]

    # 2) Run scraper (haalt ALLE data op)
    records = run_import(
        date_from=payload.date_from,
        date_to=payload.date_to,
        publicatie_type=payload.publicatie_type,
        cpv_codes=payload.cpv_codes,
        max_pages=payload.max_pages,
    )

    # 3) Map records & voeg import_id toe + check historische aanbestedingen
    notice_rows = []
    for r in records:
        # Bereken province EERST
        province = map_city_to_province(r.get("win_plaats"))
        print(r.get("win_plaats"))
        
        # Skip dit record als region filter actief is EN province niet matcht
        if payload.region:
            if not province:
                print(f"SKIPPED: No province for {r.get('win_plaats')}")
                continue
            if province.strip().lower() != payload.region.strip().lower():
                print(f"SKIPPED: province={province} != {payload.region}")
                continue

        
        # ✅ Check of bedrijf eerder aanbestedingen heeft gehad
        bedrijf_naam = (r.get("win_bedrijf_naam") or "").strip()
        heeft_eerdere_aanbestedingen = False
        aantal_eerdere_aanbestedingen = 0
        
        if bedrijf_naam:
            try:
                # Zoek in historische data (laatste 5 jaar)
                historische_records = _search_companies_in_db(
                    q=bedrijf_naam,
                    years=5,
                    max_results=100
                )
                
                if historische_records:
                    heeft_eerdere_aanbestedingen = True
                    aantal_eerdere_aanbestedingen = len(historische_records)
            except Exception as e:
                # Log error maar laat import doorgaan
                print(f"Fout bij zoeken historische data voor {bedrijf_naam}: {e}")
        
        notice_rows.append({
            "import_id": import_id,
            "notice_id": r.get("notice_id"),
            "publicatie_id": r.get("publicatieId"),
            "url": r.get("URL"),
            "titel": r.get("titel"),
            "omschrijving": r.get("omschrijving"),

            "win_bedrijf_naam": r.get("win_bedrijf_naam"),
            "win_kvk": r.get("win_kvk"),
            "win_straat": r.get("win_straat"),
            "win_postcode": r.get("win_postcode"),
            "win_plaats": r.get("win_plaats"),
            "win_land": r.get("win_land"),
            "win_contact_naam": r.get("win_contact_naam"),
            "win_contact_email": r.get("win_contact_email"),
            "win_contact_tel": r.get("win_contact_tel"),
            "win_website": r.get("win_website"),

            "buyer_bedrijf_naam": r.get("buyer_bedrijf_naam"),
            "buyer_kvk": r.get("buyer_kvk"),
            "buyer_straat": r.get("buyer_straat"),
            "buyer_postcode": r.get("buyer_postcode"),
            "buyer_plaats": r.get("buyer_plaats"),
            "buyer_land": r.get("buyer_land"),
            "buyer_contact_naam": r.get("buyer_contact_naam"),
            "buyer_contact_email": r.get("buyer_contact_email"),
            "buyer_contact_tel": r.get("buyer_contact_tel"),
            "buyer_website": r.get("buyer_website"),

            "bedrag": r.get("bedrag"),
            "valuta": r.get("valuta"),
            "province": province,
            
            # ✅ Nieuwe velden voor historische data
            "heeft_eerdere_aanbestedingen": heeft_eerdere_aanbestedingen,
            "aantal_eerdere_aanbestedingen": aantal_eerdere_aanbestedingen,
        })

    total_records = len(notice_rows)

    # 4) Upsert naar Supabase (skip dubbele notice_id)
    unique_rows = {}
    for row in notice_rows:
        nid = row.get("notice_id")
        if not nid:
            continue
        unique_rows[nid] = row

    deduped_notice_rows = list(unique_rows.values())

    if deduped_notice_rows:
        supabase.table("notices") \
            .upsert(deduped_notice_rows, on_conflict="notice_id") \
            .execute()

    # 5) Update total_records in imports
    supabase.table("imports") \
        .update({"total_records": total_records}) \
        .eq("id", import_id) \
        .execute()

    return ImportResponse(
        import_id=import_id,
        name=name,
        total_records=total_records,
        created_at=import_row["created_at"],
    )


@app.delete("/imports/{import_id}")
def delete_import(import_id: str):
  """
  Verwijder een import en alle gekoppelde data uit Supabase.
  - notices (import_id = import_id)
  - optioneel: SROI resultaten
  - imports record zelf
  """

  # 1) Bestaat de import?
  imp_resp = supabase.table("imports").select("id").eq("id", import_id).execute()
  if not imp_resp.data:
    raise HTTPException(status_code=404, detail="Import niet gevonden")

  # 2) Verwijder gekoppelde notices
  try:
    notices_resp = supabase.table("notices").delete().eq("import_id", import_id).execute()
  except Exception as e:
    print("Error deleting notices for import", import_id, e)
    raise HTTPException(status_code=500, detail="Fout bij verwijderen van notices")

  # 3) (Optioneel) Verwijder gekoppelde SROI resultaten, als je een tabel hebt
  #    en daar een import_id of notice_id-relatie in hebt.
  #    Hier ga ik ervan uit dat er een import_id kolom is in sroi_results:
  try:
    supabase.table("sroi_results").delete().eq("import_id", import_id).execute()
  except Exception as e:
    # Niet fatally als de tabel/kolom niet bestaat; loggen is genoeg
    print("Optional: error deleting sroi_results for import", import_id, e)

  # 4) Verwijder de import zelf
  try:
    delete_resp = supabase.table("imports").delete().eq("id", import_id).execute()
  except Exception as e:
    print("Error deleting import", import_id, e)
    raise HTTPException(status_code=500, detail="Fout bij verwijderen van import")

  if not delete_resp.data:
    # Als er niets verwijderd is (race condition bijvoorbeeld)
    raise HTTPException(status_code=404, detail="Import niet gevonden (bij verwijderen)")

  return {
    "detail": "Import en gekoppelde data verwijderd",
    "import_id": import_id,
    "deleted_notices": len(notices_resp.data or []),
  }



@app.get("/imports/{import_id}/notices")
def get_import_notices(import_id: str, region: Optional[str] = Query(None, description="Filter op provincie/regio")):
    """
    Fetch all notices for a specific import to display in the UI.
    """
    print("\n=== FETCH NOTICES START ===")
    print(f"Import ID received: {import_id!r}")

    try:
        resp = (
            supabase.table("notices")
            .select("*")
            .eq("import_id", import_id)
            .order("created_at", desc=False)
            .execute()
        )

        rows = resp.data or []
        print(f"Supabase returned {len(rows)} rows for import_id={import_id!r}")

        # If region filter provided, apply server-side filtering using province or win_plaats
        if region:
            region_norm = region.strip().lower()
            filtered = []
            for row in rows:
                # prefer stored province, fallback to mapping from win_plaats
                prov = (row.get("province") or map_city_to_province(row.get("win_plaats")))
                if prov and prov.strip().lower() == region_norm:
                    filtered.append(row)
            print(f"Filtered down to {len(filtered)} rows for region={region!r}")
            rows = filtered

    except Exception as e:
        print(f"ERROR while fetching notices for import_id={import_id!r}: {e}")
        raise

    print("=== FETCH NOTICES END ===\n")
    return rows


@app.get("/imports/{import_id}/download")
def download_import(
    import_id: str,
    format: str = Query("excel", pattern="^(excel|csv)$"),
    region: Optional[str] = Query(None, description="Filter op provincie/regio voor download")
):
    """
    Genereer Excel of CSV op basis van Supabase-data.
    Geen DB details in de UI, alleen een download.
    """
    resp = supabase.table("notices") \
        .select("*") \
        .eq("import_id", import_id) \
        .execute()

    rows = resp.data or []
    if not rows:
        raise HTTPException(404, "Geen records voor deze import")

    # Apply region filter if requested
    if region:
        region_norm = region.strip().lower()
        filtered = []
        for row in rows:
            prov = (row.get("province") or map_city_to_province(row.get("win_plaats")))
            if prov and prov.strip().lower() == region_norm:
                filtered.append(row)
        rows = filtered
        if not rows:
            raise HTTPException(404, "Geen records voor deze import en regio")

    if format == "csv":
        return _make_csv_response(rows, filename=f"import_{import_id}.csv")
    else:
        return _make_excel_response(rows, filename=f"import_{import_id}.xlsx")


def _make_csv_response(rows, filename: str):
    import csv

    output = io.StringIO()
    writer = None
    for row in rows:
        if writer is None:
            fieldnames = list(row.keys())
            writer = csv.DictWriter(output, fieldnames=fieldnames)
            writer.writeheader()
        writer.writerow(row)

    output.seek(0)
    return StreamingResponse(
        iter([output.getvalue().encode("utf-8")]),
        media_type="text/csv",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'}
    )


def _make_excel_response(rows, filename: str):
    import openpyxl
    from openpyxl.utils import get_column_letter

    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = "notices"

    if not rows:
        pass
    else:
        headers = list(rows[0].keys())
        ws.append(headers)
        for row in rows:
            ws.append([row.get(h) for h in headers])

        # Optioneel: auto column width
        for i, col in enumerate(ws.columns, start=1):
            max_len = max(len(str(cell.value)) if cell.value is not None else 0 for cell in col)
            ws.column_dimensions[get_column_letter(i)].width = min(max_len + 2, 60)

    buf = io.BytesIO()
    wb.save(buf)
    buf.seek(0)

    return StreamingResponse(
        buf,
        media_type=("application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"),
        headers={"Content-Disposition": f'attachment; filename="{filename}"'}
    )


def _search_companies_in_db(q: str, years: int = 5, max_results: int = 1000):
    """
    Doorzoek de tabel tenderned_raw op bedrijfsnaam (case-insensitive substring)
    en filter op Publicatiedatum binnen de afgelopen `years` jaren.
    Dedupliceert op basis van bedrijf + KVK + omschrijving en behoudt alleen
    de meest recente publicatie.
    Extraheert begin- en einddatum van de aanbesteding.

    Return-format (nu met bedrag) sluit aan op de frontend:

    [
      {
        'publicatiedatum': '2024-03-10',
        'year': '2024',
        'bedrijf': 'Studytube B.V.',
        'kvk': '51290901',
        'omschrijving': '...',
        'begindatum_opdracht': '2024-12-01',
        'einddatum_opdracht': '2029-02-28',
        'aantal_publicaties': 3,
        'bedrag': 123456.78,   # <-- NIEUW
      },
      ...
    ]
    """
    if not q:
        return []

    cutoff = (datetime.utcnow() - timedelta(days=365 * int(years))).date().isoformat()

    # 1) Haal ruwe rijen op uit de DB
    #    - "Waarde - bedrag" toegevoegd aan select
    resp = (
        supabase.table("tenderned_raw")
        .select(
            'Publicatiedatum, "Officiële benaming", Kvknummer, '
            '"Omschrijving aanbesteding", "Aanvang opdracht", "Voltooiing opdracht", '
            '"bedrag"'
        )
        .ilike("Officiële benaming", f"%{q}%")
        .gte("Publicatiedatum", cutoff)
        .limit(max_results * 5)  # wat extra, i.v.m. deduplicatie
        .execute()
    )
    if getattr(resp, "error", None):
        # hier kun je loggen
        print("Supabase error:", resp.error)
        raise RuntimeError(resp.error)

    rows = resp.data or []
    if not rows:
        return []

    # Helper voor datums
    def parse_date(raw):
        if not raw:
            return None
        if isinstance(raw, str):
            try:
                return datetime.fromisoformat(raw)
            except ValueError:
                try:
                    return datetime.strptime(raw, "%d-%m-%Y")
                except ValueError:
                    return None
        return None

    # Helper voor bedrag
    def parse_amount(raw):
        if raw is None:
            return None
        # Als Supabase al numeric/float teruggeeft:
        if isinstance(raw, (int, float)):
            return float(raw)
        # Als het een string is, probeer te parsen
        if isinstance(raw, str):
            # simpele replace voor komma-decimalen, indien nodig
            txt = raw.replace(".", "").replace(",", ".") if "," in raw else raw
            try:
                return float(txt)
            except ValueError:
                return None
        return None

    # 2) Groepeer per unieke combinatie (bedrijf, kvk, omschrijving[:100])
    all_matches = defaultdict(list)

    q_lower = q.lower()
    for row in rows:
        company = (row.get("Officiële benaming") or "").strip()
        if not company:
            continue

        # extra safeguard (ilike doet dit al, maar just in case)
        if q_lower not in company.lower():
            continue

        kvk = (row.get("Kvknummer") or "").strip()
        omschrijving = (row.get("Omschrijving aanbesteding") or "").strip()

        pub_raw = row.get("Publicatiedatum")
        pub_date = parse_date(pub_raw)

        # bedrag uit kolom "Waarde - bedrag"
        bedrag_raw = row.get("bedrag")
        bedrag = parse_amount(bedrag_raw)

        unique_key = (company, kvk, omschrijving[:100] if omschrijving else "")

        all_matches[unique_key].append(
            {
                "publicatiedatum": pub_raw,
                "pub_date_obj": pub_date,
                "row": row,
                "company": company,
                "kvk": kvk,
                "omschrijving": omschrijving,
                "bedrag": bedrag,  # extra info per match
            }
        )

    # 3) Tweede pass: pak per key de meest recente publicatie
    results = []

    for unique_key, matches in all_matches.items():
        if len(results) >= max_results:
            break

        # Kies de meest recente o.b.v. pub_date_obj (fallback op string)
        def sort_key(m):
            if m["pub_date_obj"] is not None:
                return m["pub_date_obj"]
            return m["publicatiedatum"] or ""

        most_recent = max(matches, key=sort_key)
        row = most_recent["row"]
        pub_date = most_recent["pub_date_obj"]

        # Begin- en einddatum uit row
        aanvang_raw = (row.get("Aanvang opdracht") or "").strip()
        voltooiing_raw = (row.get("Voltooiing opdracht") or "").strip()

        def to_iso_str(raw):
            if not raw:
                return None
            d = parse_date(raw)
            return d.strftime("%Y-%m-%d") if d else raw

        begindatum = to_iso_str(aanvang_raw)
        einddatum = to_iso_str(voltooiing_raw)

        results.append(
            {
                "publicatiedatum": most_recent["publicatiedatum"],
                "year": str(pub_date.year) if pub_date else "",
                "bedrijf": most_recent["company"],
                "kvk": most_recent["kvk"],
                "omschrijving": most_recent["omschrijving"],
                "begindatum_opdracht": begindatum,
                "einddatum_opdracht": einddatum,
                "aantal_publicaties": len(matches),
                "bedrag": most_recent["bedrag"],  # <-- HIER KOMT HET BEDRAG MEE TERUG
            }
        )

    print(results)
    return results


@app.get("/api/search/company")
def api_search_company(q: str = Query(..., description="Bedrijfsnaam om te zoeken"), years: int = Query(5, ge=1, le=20)):
    """
    API endpoint om op bedrijfsnaam te zoeken in TenderNed_filtered.csv.
    Query params:
      - q: bedrijfsnaam (substring, verplicht)
      - years: hoeveel jaren terug (default 5)
    
    Retourneert gededupliceerde resultaten met begin- en einddatum van opdrachten.

    """
    try:
        results = _search_companies_in_db(q=q, years=years, max_results=1000)
        print(f"Found {len(results)} results for query '{q}' within last {years} years.")
        print(results)
        return {"query": q, "years": years, "total": len(results), "results": results}
    except FileNotFoundError as e:
        raise HTTPException(status_code=500, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Search failed: {str(e)}")



# ========================================
# SROI ANALYSIS ENDPOINTS (NEW)
# ========================================

def get_notices_for_sroi(import_id: str) -> List[Dict]:
    """
    Haal alle notices op voor SROI analyse.
    """
    resp = supabase.table("notices") \
        .select("*") \
        .eq("import_id", import_id) \
        .execute()
    
    return resp.data or []


def save_sroi_results(results: List[Dict]):
    """
    Sla SROI resultaten op in Supabase.
    """
    if not results:
        return
    
    # Map results naar database format
    db_rows = []
    for result in results:
        db_rows.append({
            "import_id": result.get("import_id"),
            "notice_id": result.get("notice_id"),
            "publicatie_id": result.get("publicatie_id"),
            "winner_name": result.get("winner_name"),
            "analyzed_url": result.get("analyzed_url"),
            "url_source": result.get("url_source"),
            "sroi_compliant": result.get("sroi_compliant", False),
            "confidence": result.get("confidence", "none"),
            "score": result.get("score", 0),
            "evidence": result.get("evidence", []),  # Supabase JSONB
            "summary": result.get("summary", ""),
            "pages_checked": result.get("pages_checked", 0),
            "error": result.get("error"),
        })
    
    # Upsert (vervang bestaande resultaten)
    supabase.table("sroi_results").upsert(
        db_rows,
        on_conflict="import_id,notice_id"  # Of alleen import_id als je 1 resultaat per notice wil
    ).execute()


def run_sroi_analysis_background(import_id: str):
    """
    Background task voor SROI analyse.
    """
    try:
        print(f"\n🚀 Starting SROI analysis for import {import_id}")
        
        # Update status
        sroi_analysis_status[import_id] = {
            "status": "running",
            "progress": 0,
            "current": 0,
            "total": 0,
            "started_at": dt.datetime.utcnow().isoformat()
        }
        
        # Haal notices op
        notices = get_notices_for_sroi(import_id)
        
        if not notices:
            sroi_analysis_status[import_id].update({
                "status": "failed",
                "error": "Geen notices gevonden voor deze import"
            })
            print(f"❌ No notices found for import {import_id}")
            return
        
        sroi_analysis_status[import_id]["total"] = len(notices)
        print(f"📊 Found {len(notices)} notices to analyze")
        
        # Progress callback
        def progress_callback(current, total, result):
            sroi_analysis_status[import_id].update({
                "current": current,
                "progress": int((current / total) * 100)
            })
            print(f"Progress: {current}/{total} ({sroi_analysis_status[import_id]['progress']}%)")
        
        # Run analysis
        results = analyze_import_sroi(notices, progress_callback)
        
        # Add import_id to each result
        for result in results:
            result["import_id"] = import_id
        
        # Save to database
        print(f"💾 Saving {len(results)} results to database...")
        save_sroi_results(results)
        
        # Calculate summary
        compliant_count = sum(1 for r in results if r.get("sroi_compliant"))
        avg_score = sum(r.get("score", 0) for r in results) / len(results) if results else 0
        
        sroi_analysis_status[import_id].update({
            "status": "completed",
            "progress": 100,
            "completed_at": dt.datetime.utcnow().isoformat(),
            "results_summary": {
                "total": len(results),
                "compliant": compliant_count,
                "non_compliant": len(results) - compliant_count,
                "compliance_rate": (compliant_count / len(results) * 100) if results else 0,
                "average_score": round(avg_score, 2)
            }
        })
        
        print(f"✅ SROI analysis completed for import {import_id}")
        print(f"   Compliant: {compliant_count}/{len(results)} ({compliant_count/len(results)*100:.1f}%)")
        print(f"   Average score: {avg_score:.1f}\n")
        
    except Exception as e:
        print(f"❌ ERROR in SROI analysis for import {import_id}: {e}")
        sroi_analysis_status[import_id].update({
            "status": "failed",
            "error": str(e)
        })


@app.post("/imports/{import_id}/sroi-analyze")
async def start_sroi_analysis(import_id: str, background_tasks: BackgroundTasks):
    """
    Start SROI analyse voor een import.
    """
    # Check if import exists
    resp = supabase.table("imports") \
        .select("id, name") \
        .eq("id", import_id) \
        .execute()
    
    if not resp.data:
        raise HTTPException(status_code=404, detail="Import niet gevonden")
    
    # Check if analysis already running
    if import_id in sroi_analysis_status:
        status = sroi_analysis_status[import_id]
        if status["status"] == "running":
            raise HTTPException(
                status_code=400, 
                detail="Analyse is al bezig voor deze import"
            )
    
    # Check if results already exist
    existing = supabase.table("sroi_results") \
        .select("id") \
        .eq("import_id", import_id) \
        .limit(1) \
        .execute()
    
    if existing.data:
        raise HTTPException(
            status_code=400,
            detail="Er bestaan al SROI resultaten voor deze import. Verwijder ze eerst om opnieuw te analyseren."
        )
    
    # Start background task
    background_tasks.add_task(run_sroi_analysis_background, import_id)
    
    # Initialize status
    sroi_analysis_status[import_id] = {
        "status": "pending",
        "progress": 0,
        "current": 0,
        "total": 0,
        "started_at": dt.datetime.utcnow().isoformat()
    }
    
    return {
        "message": "SROI analyse gestart",
        "import_id": import_id,
        "status": "pending"
    }


@app.get("/imports/{import_id}/sroi-status")
async def get_sroi_status(import_id: str):
    """
    Haal de status op van een lopende SROI analyse.
    """
    if import_id not in sroi_analysis_status:
        # Check if results exist in database
        resp = supabase.table("sroi_results") \
            .select("id") \
            .eq("import_id", import_id) \
            .limit(1) \
            .execute()
        
        if resp.data:
            return {
                "import_id": import_id,
                "status": "completed",
                "message": "Analyse is al uitgevoerd. Bekijk de resultaten."
            }
        
        return {
            "import_id": import_id,
            "status": "not_started",
            "message": "Nog geen analyse gestart voor deze import"
        }
    
    return {
        "import_id": import_id,
        **sroi_analysis_status[import_id]
    }


@app.get("/imports/{import_id}/sroi-results")
async def get_sroi_results(import_id: str):
    """
    Haal SROI resultaten op voor een import.
    """
    resp = supabase.table("sroi_results") \
        .select("*") \
        .eq("import_id", import_id) \
        .order("score", desc=True) \
        .execute()
    
    results = resp.data or []
    
    # Calculate summary
    if results:
        compliant_count = sum(1 for r in results if r["sroi_compliant"])
        avg_score = sum(r["score"] for r in results) / len(results)
        
        summary = {
            "total": len(results),
            "compliant": compliant_count,
            "non_compliant": len(results) - compliant_count,
            "compliance_rate": round((compliant_count / len(results) * 100), 2),
            "average_score": round(avg_score, 2)
        }
    else:
        summary = None
    
    return {
        "import_id": import_id,
        "results": results,
        "summary": summary
    }


@app.delete("/imports/{import_id}/sroi-results")
async def delete_sroi_results(import_id: str):
    """
    Verwijder SROI resultaten (om opnieuw te analyseren).
    """
    resp = supabase.table("sroi_results") \
        .delete() \
        .eq("import_id", import_id) \
        .execute()
    
    deleted_count = len(resp.data) if resp.data else 0
    
    # Clear status
    if import_id in sroi_analysis_status:
        del sroi_analysis_status[import_id]
    
    return {
        "message": f"{deleted_count} SROI resultaten verwijderd",
        "import_id": import_id
    }


@app.get("/imports/{import_id}/notices/{notice_id}")
def get_notice_detail(import_id: str, notice_id: str):
    """
    Fetch a single notice detail by import_id and notice_id.
    """
    print(f"\n=== FETCH NOTICE DETAIL ===")
    print(f"Import ID: {import_id!r}")
    print(f"Notice ID: {notice_id!r}")
    
    try:
        # Query notices table for the specific record
        # Use .execute() first, then check if data exists
        resp = (
            supabase.table("notices")
            .select("*")
            .eq("import_id", import_id)
            .eq("id", notice_id)
            .execute()
        )
        
        # Check if any data was returned
        if not resp.data or len(resp.data) == 0:
            print(f"❌ Notice not found: import_id={import_id!r}, notice_id={notice_id!r}")
            raise HTTPException(
                status_code=404, 
                detail=f"Notice not found for import_id={import_id} and notice_id={notice_id}"
            )
        
        # Get the first (and should be only) result
        notice = resp.data[0]
        print(f"✅ Found notice: {notice.get('titel', 'No title')}")
        return notice
        
    except HTTPException:
        raise
    except Exception as e:
        print(f"❌ ERROR fetching notice detail: {e}")
        raise HTTPException(
            status_code=500,
            detail=f"Failed to fetch notice detail: {str(e)}"
        )

@app.get("/imports/{import_id}/sroi-download")
def download_sroi_results(
    import_id: str,
    format: str = Query("excel", pattern="^(excel|csv)$")
):
    """
    Download SROI resultaten als Excel of CSV.
    """
    resp = supabase.table("sroi_results") \
        .select("*") \
        .eq("import_id", import_id) \
        .order("score", desc=True) \
        .execute()
    
    rows = resp.data or []
    if not rows:
        raise HTTPException(404, "Geen SROI resultaten voor deze import")
    
    # Flatten evidence array voor export
    for row in rows:
        if isinstance(row.get("evidence"), list):
            row["evidence"] = ", ".join(row["evidence"])
    
    if format == "csv":
        return _make_csv_response(rows, filename=f"sroi_{import_id}.csv")
    else:
        return _make_excel_response(rows, filename=f"sroi_{import_id}.xlsx")


@app.get("/regions")
def list_regions(include_cities: bool = Query(False, description="Include city lists per province")):
    """
    Return available provinces (regio's). Set include_cities=true to also return example cities per province.
    """
    if include_cities:
        return {"regions": PROVINCE_TO_CITIES}
    return {"regions": list(PROVINCE_TO_CITIES.keys())}


# ---------------------------
# Simple CRM / Rapportage API
# ---------------------------
# Note: This implementation expects two tables in Supabase/postgres:
# 1) crm_companies
# 2) crm_followups
# If these tables don't exist yet, call GET /crm/init to retrieve the SQL needed
# to create them in your Supabase SQL editor.

CRM_COMPANIES_CREATE_SQL = """
CREATE TABLE IF NOT EXISTS crm_companies (
  id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
  name TEXT NOT NULL,
  website TEXT,
  kvk TEXT,
  contact_name TEXT,
  contact_email TEXT,
  contact_phone TEXT,
  source_notice_id TEXT,
  lead_status TEXT DEFAULT 'new', -- e.g. new, contacted, interested, not_interested
  last_contacted TIMESTAMPTZ,
  notes TEXT,
  extra JSONB,
  created_at TIMESTAMPTZ DEFAULT NOW(),
  updated_at TIMESTAMPTZ DEFAULT NOW()
);
CREATE INDEX IF NOT EXISTS idx_crm_companies_name ON crm_companies (lower(name));
"""

CRM_FOLLOWUPS_CREATE_SQL = """
CREATE TABLE IF NOT EXISTS crm_followups (
  id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
  company_id BIGINT REFERENCES crm_companies(id) ON DELETE CASCADE,
  scheduled_at TIMESTAMPTZ,
  completed BOOLEAN DEFAULT FALSE,
  emailed BOOLEAN DEFAULT FALSE,
  action TEXT,
  note TEXT,
  created_by TEXT,
  created_at TIMESTAMPTZ DEFAULT NOW(),
  updated_at TIMESTAMPTZ DEFAULT NOW()
);
CREATE INDEX IF NOT EXISTS idx_crm_followups_company ON crm_followups (company_id);
"""


@app.get("/crm/init")
def crm_init():
    """Return SQL to create CRM tables. Run these statements in Supabase SQL editor if tables don't exist."""
    return {
        "message": "If your Supabase database doesn't have the CRM tables, run the provided SQL in the Supabase SQL editor.",
        "crm_companies_sql": CRM_COMPANIES_CREATE_SQL,
        "crm_followups_sql": CRM_FOLLOWUPS_CREATE_SQL,
    }


def _ensure_crm_tables_ok():
    """Quick check whether crm_companies exists; return (ok, error_message)
    We try a harmless select. If it fails, return False and an advisory message.
    """
    try:
        resp = supabase.table("crm_companies").select("id").limit(1).execute()
        # If the table doesn't exist, supabase client may return an error on resp.error
        if getattr(resp, "error", None):
            return False, str(resp.error)
        return True, None
    except Exception as e:
        return False, str(e)


@app.get("/crm/companies")
def crm_list_companies(q: Optional[str] = Query(None, description="Search by name substring"), status: Optional[str] = Query(None)):
    """List companies (leads). Optional search by name and filter by lead_status."""
    ok, err = _ensure_crm_tables_ok()
    if not ok:
        raise HTTPException(status_code=500, detail={"error": "CRM tables not found", "advice": "Call /crm/init and run SQL in Supabase" , "raw": err})

    query = supabase.table("crm_companies").select("*")
    if q:
        # simple ilike search
        query = query.ilike("name", f"%{q}%")
    if status:
        query = query.eq("lead_status", status)

    resp = query.order("updated_at", desc=True).limit(100).execute()
    return resp.data or []


@app.post("/crm/companies")
def crm_create_company(payload: dict):
    """Create a new company lead. Expected JSON payload keys: name (required), website, kvk, contact_name, contact_email, source_notice_id, notes, lead_status"""
    ok, err = _ensure_crm_tables_ok()
    if not ok:
        raise HTTPException(status_code=500, detail={"error": "CRM tables not found", "advice": "Call /crm/init and run SQL in Supabase" , "raw": err})

    if not payload.get("name"):
        raise HTTPException(status_code=400, detail="Field 'name' is required")

    payload.setdefault("created_at", dt.datetime.utcnow().isoformat())
    payload.setdefault("updated_at", dt.datetime.utcnow().isoformat())

    resp = supabase.table("crm_companies").insert(payload).execute()
    if getattr(resp, "error", None):
        raise HTTPException(status_code=500, detail=str(resp.error))
    return resp.data[0]


@app.get("/crm/companies/{company_id}")
def crm_get_company(company_id: int):
    ok, err = _ensure_crm_tables_ok()
    if not ok:
        raise HTTPException(status_code=500, detail={"error": "CRM tables not found", "advice": "Call /crm/init and run SQL in Supabase" , "raw": err})

    resp = supabase.table("crm_companies").select("*").eq("id", company_id).limit(1).execute()
    if not resp.data:
        raise HTTPException(status_code=404, detail="Company not found")
    company = resp.data[0]

    # fetch followups
    fresp = supabase.table("crm_followups").select("*").eq("company_id", company_id).order("scheduled_at", desc=False).execute()
    followups = fresp.data or []
    company["followups"] = followups
    return company


@app.patch("/crm/companies/{company_id}")
def crm_update_company(company_id: int, payload: dict):
    ok, err = _ensure_crm_tables_ok()
    if not ok:
        raise HTTPException(status_code=500, detail={"error": "CRM tables not found", "advice": "Call /crm/init and run SQL in Supabase" , "raw": err})

    payload["updated_at"] = dt.datetime.utcnow().isoformat()
    resp = supabase.table("crm_companies").update(payload).eq("id", company_id).execute()
    if getattr(resp, "error", None):
        raise HTTPException(status_code=500, detail=str(resp.error))
    if not resp.data:
        raise HTTPException(status_code=404, detail="Company not found or not updated")
    return resp.data[0]


@app.post("/crm/companies/{company_id}/followups")
def crm_add_followup(company_id: int, payload: dict):
    """Add a follow-up action/note for a company. payload keys: scheduled_at (ISO), action, note, emailed (bool), completed (bool), created_by"""
    ok, err = _ensure_crm_tables_ok()
    if not ok:
        raise HTTPException(status_code=500, detail={"error": "CRM tables not found", "advice": "Call /crm/init and run SQL in Supabase" , "raw": err})

    # validate company exists
    cresp = supabase.table("crm_companies").select("id").eq("id", company_id).limit(1).execute()
    if not cresp.data:
        raise HTTPException(status_code=404, detail="Company not found")

    payload["company_id"] = company_id
    payload.setdefault("created_at", dt.datetime.utcnow().isoformat())
    payload.setdefault("updated_at", dt.datetime.utcnow().isoformat())

    resp = supabase.table("crm_followups").insert(payload).execute()
    if getattr(resp, "error", None):
        raise HTTPException(status_code=500, detail=str(resp.error))
    return resp.data[0]


@app.get("/crm/companies/{company_id}/followups")
def crm_list_followups(company_id: int):
    ok, err = _ensure_crm_tables_ok()
    if not ok:
        raise HTTPException(status_code=500, detail={"error": "CRM tables not found", "advice": "Call /crm/init and run SQL in Supabase" , "raw": err})

    resp = supabase.table("crm_followups").select("*").eq("company_id", company_id).order("scheduled_at", desc=False).execute()
    return resp.data or []


@app.patch("/crm/followups/{followup_id}")
def crm_update_followup(followup_id: int, payload: dict):
    ok, err = _ensure_crm_tables_ok()
    if not ok:
        raise HTTPException(status_code=500, detail={"error": "CRM tables not found", "advice": "Call /crm/init and run SQL in Supabase" , "raw": err})

    payload["updated_at"] = dt.datetime.utcnow().isoformat()
    resp = supabase.table("crm_followups").update(payload).eq("id", followup_id).execute()
    if getattr(resp, "error", None):
        raise HTTPException(status_code=500, detail=str(resp.error))
    if not resp.data:
        raise HTTPException(status_code=404, detail="Followup not found or not updated")
    return resp.data[0]


# Runnen:
# uvicorn serve:app --reload --port 8000