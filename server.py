# serve.py
import os
import io
import json
import datetime as dt
from typing import Optional, List, Dict
from fastapi import FastAPI, HTTPException, Query, BackgroundTasks, Depends, Header, Request
from fastapi.responses import StreamingResponse
from pydantic import BaseModel
from supabase import create_client, Client
from datetime import datetime, timedelta
from collections import defaultdict
import csv

from dotenv import load_dotenv
from sroi_scanner import analyze_notice_sroi




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


# ----------------------
# Simple header-based auth
# Expects header `X-User-Code: 123456789012` (12 digits)
# ----------------------
def validate_user_code(x_user_code: str = Header(..., alias="X-User-Code")) -> str:
    """Validate that the provided header is a 12-digit numeric code.
    Returns the code when valid, otherwise raises HTTPException(401).
    """
    if not x_user_code:
        raise HTTPException(status_code=401, detail="X-User-Code header missing")
    code = str(x_user_code).strip()
    if len(code) != 12 or not code.isdigit():
        raise HTTPException(status_code=401, detail="Invalid user code. Must be 12 digits.")
    # Server-side validation: ensure the code exists in a whitelist table (e.g. `auth_codes`)
    try:
        resp = supabase.table("auth_codes").select("code").eq("code", code).limit(1).execute()
        # If Supabase returns an error (e.g. table doesn't exist), surface a server error
        if getattr(resp, "error", None):
            # If the table doesn't exist, treat as server misconfiguration
            raise HTTPException(status_code=500, detail=f"Auth validation error: {resp.error}")
        if not resp.data:
            # No matching code found
            raise HTTPException(status_code=403, detail="Unknown user code; please register your code or contact admin.")
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to validate user code: {e}")

    return code


def _import_belongs_to_user(import_id: str, user_code: str) -> bool:
    try:
        resp = supabase.table("imports").select("id").eq("id", import_id).eq("owner_code", user_code).limit(1).execute()
        return bool(resp.data)
    except Exception:
        return False



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
def list_imports(user_code: str = Depends(validate_user_code)):
    """
    Lijst eerdere imports (voor UI-overzicht).
    """
    resp = supabase.table("imports") \
        .select("*") \
        .eq("owner_code", user_code) \
        .order("created_at", desc=True) \
        .limit(50) \
        .execute()

    return resp.data or []

    
def map_cache_to_import_schema(cache_row: dict) -> dict:
    """Map tenderned_raw schema naar import record schema"""
    return {
        "notice_id": cache_row.get("notice_id"),
        "publicatieId": cache_row.get("publicatie_id"),
        "publicatie_id": cache_row.get("publicatie_id"),
        "URL": cache_row.get("url") or cache_row.get("URL TenderNed"),
        "url": cache_row.get("url") or cache_row.get("URL TenderNed"),
        "titel": cache_row.get("titel") or cache_row.get("Naam aanbesteding"),
        "omschrijving": cache_row.get("omschrijving") or cache_row.get("Omschrijving aanbesteding"),
        "win_bedrijf_naam": cache_row.get("win_bedrijf_naam") or cache_row.get("Officiële benaming"),
        "win_kvk": cache_row.get("win_kvk") or cache_row.get("Kvknummer"),
        "win_straat": cache_row.get("win_straat") or cache_row.get("Postadres"),
        "win_postcode": cache_row.get("win_postcode") or cache_row.get("Postcode"),
        "win_plaats": cache_row.get("win_plaats") or cache_row.get("Plaats"),
        "win_land": cache_row.get("win_land") or cache_row.get("Land"),
        "win_contact_naam": cache_row.get("win_contact_naam"),
        "win_contact_email": cache_row.get("win_contact_email"),
        "win_contact_tel": cache_row.get("win_contact_tel"),
        "win_website": cache_row.get("win_website") or cache_row.get("Internetadres"),
        "buyer_bedrijf_naam": cache_row.get("buyer_bedrijf_naam") or cache_row.get("Naam Aanbestedende dienst"),
        "buyer_kvk": cache_row.get("buyer_kvk") or cache_row.get("Nationaal identificatienummer"),
        "buyer_straat": cache_row.get("buyer_straat"),
        "buyer_postcode": cache_row.get("buyer_postcode"),
        "buyer_plaats": cache_row.get("buyer_plaats"),
        "buyer_land": cache_row.get("buyer_land"),
        "buyer_contact_naam": cache_row.get("buyer_contact_naam"),
        "buyer_contact_email": cache_row.get("buyer_contact_email"),
        "buyer_contact_tel": cache_row.get("buyer_contact_tel"),
        "buyer_website": cache_row.get("buyer_website"),
        "bedrag": cache_row.get("bedrag"),
        "valuta": cache_row.get("valuta") or cache_row.get("Waarde - valuta"),
        "contract_issue_date": cache_row.get("publicatie_datum") or cache_row.get("Publicatiedatum"),
        "publicatie_datum": cache_row.get("publicatie_datum") or cache_row.get("Publicatiedatum"),

        "heeft_eerdere_aanbestedingen": cache_row.get("heeft_eerdere_aanbestedingen", False),
        "aantal_eerdere_aanbestedingen": cache_row.get("aantal_eerdere_aanbestedingen", 0),
        "totaal_bedrag_eerdere_aanbestedingen": cache_row.get("totaal_bedrag_eerdere_aanbestedingen"),
    }


def map_import_to_cache_schema(import_row: dict) -> dict:
    """Map import record schema naar tenderned_raw schema"""
    # Haal publicatie_datum op en formatteer correct
    pub_datum = import_row.get("contract_issue_date") or import_row.get("publicatie_datum")
    if pub_datum and isinstance(pub_datum, str):
        # Zorg dat het een date string is (YYYY-MM-DD)
        pub_datum = pub_datum[:10] if len(pub_datum) >= 10 else pub_datum
    
    return {
        "notice_id": import_row.get("notice_id"),
        "publicatie_id": import_row.get("publicatieId") or import_row.get("publicatie_id"),
        "Publicatiedatum": pub_datum,
        "publicatie_datum": pub_datum,
        "Naam aanbesteding": import_row.get("titel"),
        "titel": import_row.get("titel"),
        "Omschrijving aanbesteding": import_row.get("omschrijving"),
        "omschrijving": import_row.get("omschrijving"),
        "URL TenderNed": import_row.get("URL") or import_row.get("url"),
        "url": import_row.get("URL") or import_row.get("url"),
        "Officiële benaming": import_row.get("win_bedrijf_naam"),
        "win_bedrijf_naam": import_row.get("win_bedrijf_naam"),
        "Kvknummer": import_row.get("win_kvk"),
        "win_kvk": import_row.get("win_kvk"),
        "Postadres": import_row.get("win_straat"),
        "win_straat": import_row.get("win_straat"),
        "Postcode": import_row.get("win_postcode"),
        "win_postcode": import_row.get("win_postcode"),
        "Plaats": import_row.get("win_plaats"),
        "win_plaats": import_row.get("win_plaats"),
        "Land": import_row.get("win_land"),
        "win_land": import_row.get("win_land"),
        "win_contact_naam": import_row.get("win_contact_naam"),
        "win_contact_email": import_row.get("win_contact_email"),
        "win_contact_tel": import_row.get("win_contact_tel"),
        "Internetadres": import_row.get("win_website"),
        "win_website": import_row.get("win_website"),
        "Naam Aanbestedende dienst": import_row.get("buyer_bedrijf_naam"),
        "buyer_bedrijf_naam": import_row.get("buyer_bedrijf_naam"),
        "Nationaal identificatienummer": import_row.get("buyer_kvk"),
        "buyer_kvk": import_row.get("buyer_kvk"),
        "buyer_straat": import_row.get("buyer_straat"),
        "buyer_postcode": import_row.get("buyer_postcode"),
        "buyer_plaats": import_row.get("buyer_plaats"),
        "buyer_land": import_row.get("buyer_land"),
        "buyer_contact_naam": import_row.get("buyer_contact_naam"),
        "buyer_contact_email": import_row.get("buyer_contact_email"),
        "buyer_contact_tel": import_row.get("buyer_contact_tel"),
        "buyer_website": import_row.get("buyer_website"),
        "bedrag": import_row.get("bedrag"),
        "Waarde - valuta": import_row.get("valuta"),
        "valuta": import_row.get("valuta"),
        "owner_code": import_row.get("owner_code"),
        "heeft_eerdere_aanbestedingen": import_row.get("heeft_eerdere_aanbestedingen", False),
        "aantal_eerdere_aanbestedingen": import_row.get("aantal_eerdere_aanbestedingen", 0),
        "totaal_bedrag_eerdere_aanbestedingen": import_row.get("totaal_bedrag_eerdere_aanbestedingen"),
    
    }
    
from datetime import datetime, timedelta

BATCH_SIZE = 1000  # or whatever your PostgREST max-rows is

def fetch_cached_in_batches(
    date_from: str, 
    date_to: str, 
    cache_table: str = "tenderned_raw_cached",
    cpv_codes: list[str] = None
) -> list[dict]:
    """
    Haal alle cached rows op voor een Publicatiedatum-range, in batches van BATCH_SIZE.
    Returned een platte list van rows (dus GEEN .data).
    
    Args:
        date_from: Start datum voor de range (inclusive)
        date_to: Eind datum voor de range (exclusive, zoals SQL <)
        cache_table: Naam van de cache table (default: "tenderned_raw_cached")
        cpv_codes: Optionele lijst van CPV codes om op te filteren
    
    Returns:
        List van alle rows binnen de datum range (en optioneel gefilterd op CPV)
    """
    offset = 0
    all_rows: list[dict] = []
    
    while True:
        query = (
            supabase
            .table(cache_table)
            .select("*")
            .gte("Publicatiedatum", date_from)
            .lt("Publicatiedatum", date_to)  # Changed from lte to lt to match SQL behavior
        )
        
        # Als we CPV codes hebben, filter dan IN de database query
        if cpv_codes and cache_table == "tenderned_raw_cpv_cached":
            # Bouw OR filter voor alle CPV codes
            # Dit zorgt ervoor dat we direct in de database filteren
            cpv_filters = []
            for cpv in cpv_codes:
                cpv_filters.append(f"cpv_code.eq.{cpv},cpv_codes.ilike.%{cpv}%")
            
            # Gebruik or_ filter voor meerdere CPV codes
            if len(cpv_codes) == 1:
                query = query.or_(f"cpv_code.eq.{cpv_codes[0]},cpv_codes.ilike.%{cpv_codes[0]}%")
            else:
                or_condition = ",".join([f"cpv_code.eq.{cpv}" for cpv in cpv_codes] + 
                                       [f"cpv_codes.ilike.%{cpv}%" for cpv in cpv_codes])
                query = query.or_(or_condition)
        
        resp = query.range(offset, offset + BATCH_SIZE - 1).execute()
        
        rows = resp.data or []
        
        # Check of we nog rows hebben gekregen
        if not rows:
            break
        
        all_rows.extend(rows)
        
        # Als we minder rows krijgen dan BATCH_SIZE, zijn we klaar
        if len(rows) < BATCH_SIZE:
            break
            
        offset += BATCH_SIZE
    
    return all_rows

@app.post("/imports", response_model=ImportResponse)
def start_import(payload: ImportRequest, user_code: str = Depends(validate_user_code)):
    """
    Start een nieuwe import-run met volledige caching via tenderned_raw.
    Implementeert alle scenario's uit het importeer-document.
    Ondersteunt nu ook CPV-specifieke caching.
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
        "owner_code": user_code,
    }).execute()

    if not insert_resp.data:
        raise HTTPException(500, "Kon import-record niet aanmaken")

    import_row = insert_resp.data[0]
    import_id = import_row["id"]

    # 2) Bepaal data-bron(nen): cache (met of zonder CPV) + evt run_import
    date_from = payload.date_from
    date_to = payload.date_to

    # Normaliseer naar strings voor vergelijking
    df_str = str(date_from) if date_from is not None else None
    dt_str = str(date_to) if date_to is not None else None

    records: list[dict] = []
    records_from_api: list[dict] = []  # Track welke records van API komen

    # Bepaal welke cache table te gebruiken
    cache_table = "tenderned_raw_cpv_cached" if payload.cpv_codes else "tenderned_raw_cached"
    print(f"🗄️  Gebruikte cache table: {cache_table}")

    # Haal cache range op
    range_resp = supabase.table(cache_table) \
        .select("Publicatiedatum") \
        .not_.is_("Publicatiedatum", "null") \
        .order("Publicatiedatum", desc=False) \
        .limit(1) \
        .execute()

    earliest_publicatie = None
    if range_resp.data:
        earliest_publicatie = range_resp.data[0]["Publicatiedatum"]

    latest_raw_resp = supabase.table(cache_table) \
        .select("Publicatiedatum") \
        .not_.is_("Publicatiedatum", "null") \
        .order("Publicatiedatum", desc=True) \
        .limit(1) \
        .execute()

    latest_publicatie = None
    if latest_raw_resp.data:
        latest_publicatie = latest_raw_resp.data[0]["Publicatiedatum"]

    ep_str = str(earliest_publicatie) if earliest_publicatie is not None else None
    lp_str = str(latest_publicatie) if latest_publicatie is not None else None

    print(f"📊 Cache range: {ep_str} tot {lp_str}")
    print(f"🎯 Gevraagde range: {df_str} tot {dt_str}")

    # SCENARIO 1: Geen cache OF startdatum > meest recente datum in cache
    if not lp_str or (df_str is not None and df_str > lp_str):
        print(f"📡 SCENARIO 1: Startdatum ({df_str}) > laatste cache ({lp_str})")
        print(f"   → Ophalen via TenderNed API: {df_str} tot {dt_str}")
        
        new_records = run_import(
            date_from=payload.date_from,
            date_to=payload.date_to,
            publicatie_type=payload.publicatie_type,
            cpv_codes=payload.cpv_codes,
            max_pages=payload.max_pages,
        )
        
        if new_records:
            records.extend(new_records)
            records_from_api.extend(new_records)  # Deze komen van API
            
            # Voeg toe aan cache
            cache_records = [map_import_to_cache_schema(r) for r in new_records]
            print(f"💾 Opslaan {len(cache_records)} records in {cache_table}")
            supabase.table(cache_table) \
                .upsert(cache_records, on_conflict="notice_id") \
                .execute()

    # SCENARIO 5: Startdatum < kleinste datum in cache
    elif ep_str and df_str is not None and df_str < ep_str:
        print(f"📡 SCENARIO 5: Startdatum ({df_str}) < oudste cache ({ep_str})")
        
        # Bepaal waar cache begint te overlappen
        cache_overlap_start = ep_str
        cache_overlap_end = dt_str if (dt_str and dt_str <= lp_str) else lp_str
        
        # Haal historische data op VIA API (ouder dan cache)
        api_end = ep_str
        print(f"   → API ophalen (historisch): {df_str} tot {api_end}")
        
        historical_records = run_import(
            date_from=payload.date_from,
            date_to=earliest_publicatie,
            publicatie_type=payload.publicatie_type,
            cpv_codes=payload.cpv_codes,
            max_pages=payload.max_pages,
        )
        
        if historical_records:
            records.extend(historical_records)
            records_from_api.extend(historical_records)  # Deze komen van API
            
            # Voeg historische data toe aan cache
            cache_records = [map_import_to_cache_schema(r) for r in historical_records]
            print(f"💾 Opslaan {len(cache_records)} historische records in {cache_table}")
            supabase.table(cache_table) \
                .upsert(cache_records, on_conflict="notice_id") \
                .execute()
        
        # Haal cached data op (als einddatum binnen cache valt)
        if dt_str and dt_str >= cache_overlap_start:
            print(f"   → Cache gebruiken: {cache_overlap_start} tot {cache_overlap_end}")
            
            cached_rows = fetch_cached_in_batches(
                cache_overlap_start, 
                cache_overlap_end,
                cache_table=cache_table,
                cpv_codes=payload.cpv_codes
            )

            if cached_rows:
                print(f"✅ {len(cached_rows)} records uit cache (batched)")
                for cache_row in cached_rows:
                    records.append(map_cache_to_import_schema(cache_row))
                # NIET toevoegen aan records_from_api
        
        # Als einddatum > laatste cache datum, haal resterende data op
        if dt_str and lp_str and dt_str > lp_str:
            print(f"   → API ophalen (recent): {lp_str} tot {dt_str}")
            
            recent_records = run_import(
                date_from=latest_publicatie,
                date_to=payload.date_to,
                publicatie_type=payload.publicatie_type,
                cpv_codes=payload.cpv_codes,
                max_pages=payload.max_pages,
            )
            
            if recent_records:
                records.extend(recent_records)
                records_from_api.extend(recent_records)  # Deze komen van API
                cache_records = [map_import_to_cache_schema(r) for r in recent_records]
                print(f"💾 Opslaan {len(cache_records)} recente records in {cache_table}")
                supabase.table(cache_table) \
                    .upsert(cache_records, on_conflict="notice_id") \
                    .execute()

    # SCENARIO 2 & 3: Startdatum <= meest recente datum in cache
    else:
        print(f"📦 SCENARIO 2/3: Startdatum ({df_str}) binnen cache range")
        
        # Bepaal upper bound voor cached data
        upper_bound_str = dt_str if (dt_str is not None and dt_str <= lp_str) else lp_str
        
        # Haal cached data op IN BATCHES
        print(f"   → Cache gebruiken: {df_str} tot {upper_bound_str}")
        cached_rows = fetch_cached_in_batches(
            df_str, 
            upper_bound_str,
            cache_table=cache_table,
            cpv_codes=payload.cpv_codes
        )

        if cached_rows:
            print(f"✅ {len(cached_rows)} records uit cache (batched)")
            for cache_row in cached_rows:
                records.append(map_cache_to_import_schema(cache_row))
            # Deze komen NIET van API, dus niet toevoegen aan records_from_api

        # Als einddatum > laatste cache datum, vul aan met API
        if dt_str is not None and lp_str and dt_str > lp_str:
            print(f"   → API aanvullen: {lp_str} tot {dt_str}")
            
            new_records = run_import(
                date_from=latest_publicatie,
                date_to=payload.date_to,
                publicatie_type=payload.publicatie_type,
                cpv_codes=payload.cpv_codes,
                max_pages=payload.max_pages,
            )

            if new_records:
                print(f"✅ {len(new_records)} nieuwe records via API")
                records.extend(new_records)
                records_from_api.extend(new_records)  # Deze komen van API

                # Voeg toe aan cache
                cache_records = [map_import_to_cache_schema(r) for r in new_records]
                print(f"💾 Opslaan {len(cache_records)} nieuwe records in {cache_table}")
                supabase.table(cache_table) \
                    .upsert(cache_records, on_conflict="notice_id") \
                    .execute()

    print(f"📊 Totaal records verzameld: {len(records)}")
    print(f"📡 Waarvan van API: {len(records_from_api)}")

    # Maak een set van notice_ids die van API komen voor snelle lookup
    api_notice_ids = {r.get("notice_id") for r in records_from_api if r.get("notice_id")}

    # 3) Map records & voeg import_id toe
    # Check historische aanbestedingen ALLEEN voor records die van API komen
    notice_rows = []
    for r in records:
        # Bereid province EERST
        province = map_city_to_province(r.get("win_plaats"))
        
        # Skip dit record als region filter actief is EN province niet matcht
        if payload.region:
            if not province:
                continue
            if province.strip().lower() != payload.region.strip().lower():
                continue

        notice_id = r.get("notice_id")
        
        # Check historische aanbestedingen ALLEEN als dit record van API komt
        heeft_eerdere_aanbestedingen = False
        aantal_eerdere_aanbestedingen = 0
        
        if notice_id in api_notice_ids:
            bedrijf_naam = (r.get("win_bedrijf_naam") or "").strip()
            
            if bedrijf_naam:
                try:
                    historische_records = _search_companies_in_db(
                        q=bedrijf_naam,
                        years=5,
                        max_results=100
                    )
                    
                    if historische_records:
                        heeft_eerdere_aanbestedingen = True
                        aantal_eerdere_aanbestedingen = len(historische_records)
                except Exception as e:
                    print(f"Fout bij zoeken historische data voor {bedrijf_naam}: {e}")
        else:
            # Voor cached records: haal de waarden op uit de cache
            heeft_eerdere_aanbestedingen = r.get("heeft_eerdere_aanbestedingen", False)
            aantal_eerdere_aanbestedingen = r.get("aantal_eerdere_aanbestedingen", 0)

        # Haal publicatie_datum op
        pub_datum = r.get("contract_issue_date") or r.get("publicatie_datum")
        if pub_datum and isinstance(pub_datum, str) and len(pub_datum) >= 10:
            pub_datum = pub_datum[:10]
        
        notice_rows.append({
            "import_id": import_id,
            "notice_id": notice_id,
            "publicatie_id": r.get("publicatieId") or r.get("publicatie_id"),
            "url": r.get("URL") or r.get("url"),
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
            "publicatie_datum": pub_datum,
            "heeft_eerdere_aanbestedingen": heeft_eerdere_aanbestedingen,
            "aantal_eerdere_aanbestedingen": aantal_eerdere_aanbestedingen,
            "owner_code": user_code,
        })

    total_records = len(notice_rows)
    print(f"✅ {total_records} records na filtering")

    # 4) Upsert naar Supabase
    unique_rows = {}
    for row in notice_rows:
        nid = row.get("notice_id")
        if not nid:
            continue
        unique_rows[nid] = row

    deduped_notice_rows = list(unique_rows.values())

    # Filter alleen records die van API komen
    api_records_to_save = [
        row for row in deduped_notice_rows 
        if row.get("notice_id") in api_notice_ids
    ]

    print(f"💾 Opslaan {len(api_records_to_save)} unieke notices (alleen van API)")
    print(f"⏭️  Overgeslagen: {len(deduped_notice_rows) - len(api_records_to_save)} notices (al in cache)")

    UPSERT_BATCH_SIZE = 500

    if api_records_to_save:
        for r in api_records_to_save:
            r.setdefault("owner_code", user_code)
        
        # Upsert in batches
        for i in range(0, len(api_records_to_save), UPSERT_BATCH_SIZE):
            batch = api_records_to_save[i:i + UPSERT_BATCH_SIZE]
            print(f"💾 Upserting batch {i//UPSERT_BATCH_SIZE + 1}/{(len(api_records_to_save)-1)//UPSERT_BATCH_SIZE + 1} ({len(batch)} records)")
            supabase.table("notices") \
                .upsert(batch, on_conflict="notice_id") \
                .execute()


    # 5) Update total_records
    supabase.table("imports") \
        .update({"total_records": total_records}) \
        .eq("id", import_id) \
        .eq("owner_code", user_code) \
        .execute()

    print(f"✅ Import {name} voltooid: {total_records} records")

    return ImportResponse(
        import_id=import_id,
        name=name,
        total_records=total_records,
        created_at=import_row["created_at"],
    )


@app.delete("/imports/{import_id}")
def delete_import(import_id: str, user_code: str = Depends(validate_user_code)):
    """
    Verwijder een import en alle gekoppelde data uit Supabase.
    - notices (import_id = import_id)
    - optioneel: SROI resultaten
    - imports record zelf
    """

    # 1) Bestaat de import? + eigenaarschap check
    imp_resp = (
        supabase.table("imports")
        .select("id, owner_code")
        .eq("id", import_id)
        .execute()
    )

    if not imp_resp.data:
        raise HTTPException(status_code=404, detail="Import niet gevonden")

    found = imp_resp.data[0]
    owner_code = found.get("owner_code")

    if owner_code and owner_code != user_code:
        raise HTTPException(
            status_code=403,
            detail="Je hebt geen toestemming om deze import te verwijderen"
        )

    # 2) Verwijder gekoppelde notices
    try:
        notices_resp = (
            supabase.table("notices")
            .delete()
            .eq("import_id", import_id)
            .eq("owner_code", user_code)  # <- ensures user can delete only own notices
            .execute()
        )
    except Exception as e:
        print("Error deleting notices for import", import_id, e)
        raise HTTPException(
            status_code=500,
            detail="Fout bij verwijderen van notices"
        )

    # 3) Verwijder gekoppelde SROI resultaten
    try:
        supabase.table("sroi_results") \
            .delete() \
            .eq("import_id", import_id) \
            .eq("owner_code", user_code) \
            .execute()
    except Exception as e:
        print("Optional: error deleting sroi_results for import", import_id, e)

    # 4) Verwijder de import zelf
    try:
        delete_resp = (
            supabase.table("imports")
            .delete()
            .eq("id", import_id)
            .eq("owner_code", user_code)
            .execute()
        )
    except Exception as e:
        print("Error deleting import", import_id, e)
        raise HTTPException(
            status_code=500,
            detail="Fout bij verwijderen van import"
        )

    if not delete_resp.data:
        raise HTTPException(
            status_code=404,
            detail="Import niet gevonden (bij verwijderen)"
        )

    return {
        "detail": "Import en gekoppelde data verwijderd",
        "import_id": import_id,
        "deleted_notices": len(notices_resp.data or []),
    }



@app.get("/imports/{import_id}/notices")
def get_import_notices(import_id: str, region: Optional[str] = Query(None, description="Filter op provincie/regio"), user_code: str = Depends(validate_user_code)):
    """
    Fetch all notices for a specific import to display in the UI.
    """
    print("\n=== FETCH NOTICES START ===")
    print(f"Import ID received: {import_id!r}")

    try:
        # Only fetch notices that belong to this user
        resp = (
            supabase.table("notices")
            .select("*")
            .eq("import_id", import_id)
            .eq("owner_code", user_code)
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
    region: Optional[str] = Query(None, description="Filter op provincie/regio voor download"),
    user_code: str = Depends(validate_user_code),
):
    """
    Genereer Excel of CSV op basis van Supabase-data.
    Geen DB details in de UI, alleen een download.
    """
    resp = supabase.table("notices") \
        .select("*") \
        .eq("import_id", import_id) \
        .eq("owner_code", user_code) \
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

    return results


@app.post("/validate-code")
def validate_code_endpoint(payload: dict):
    """Validate a code server-side without needing a full authenticated request.
    Expects JSON: { code: "123456789012" }
    Returns 200 ok if code exists in `auth_codes` table; 400 for bad input; 403 if unknown.
    """
    code = (payload.get("code") if isinstance(payload, dict) else None) or ""
    code = str(code).strip()
    if not code or not code.isdigit() or len(code) != 12:
        raise HTTPException(status_code=400, detail="Invalid code format")

    try:
        resp = supabase.table("auth_codes").select("code").eq("code", code).limit(1).execute()
        if getattr(resp, "error", None):
            raise HTTPException(status_code=500, detail=f"Auth validation error: {resp.error}")
        if not resp.data:
            raise HTTPException(status_code=403, detail="Unknown code")
        return {"ok": True}
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/auth/request-code")
def request_code_endpoint():
    """Generate a unique 12-digit numeric code, store it in `auth_codes` and return it.
    This endpoint is intentionally simple: it returns the generated code in the response body.
    Ensure your Supabase DB has an `auth_codes(code TEXT PRIMARY KEY, created_at TIMESTAMPTZ)` table.
    """
    import random

    def _gen():
        return "%012d" % random.randint(0, 10**12 - 1)

    # Try a few times to avoid collisions on insert
    attempts = 0
    max_attempts = 8
    while attempts < max_attempts:
        attempts += 1
        code = _gen()
        try:
            resp = supabase.table("auth_codes").insert({"code": code, "created_at": dt.datetime.utcnow().isoformat()}).execute()
            # If insert succeeded, return the code
            if getattr(resp, "error", None):
                # If duplicate key error or other, retry a few times
                # Supabase client exposes resp.error; if it's a duplicate we try again
                # For other errors, surface
                err_text = str(resp.error)
                # crude duplicate check
                if "duplicate" in err_text.lower() or "unique" in err_text.lower():
                    continue
                raise HTTPException(status_code=500, detail=f"Failed to create auth code: {resp.error}")
            if resp.data:
                return {"code": code}
        except Exception as e:
            # If it's a DB-level duplicate, try again; otherwise surface after last attempt
            if attempts >= max_attempts:
                raise HTTPException(status_code=500, detail=f"Error generating code: {e}")
            continue

    raise HTTPException(status_code=500, detail="Could not generate unique code, try again later")


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

def get_notices_for_sroi(import_id: str, owner_code: str) -> List[Dict]:
    """
    Haal alle notices op voor SROI analyse.
    """
    resp = supabase.table("notices") \
        .select("*") \
        .eq("import_id", import_id) \
        .eq("owner_code", owner_code) \
        .execute()
    
    return resp.data or []


def save_sroi_results(results: List[Dict], owner_code: Optional[str] = None):
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
            "owner_code": owner_code,
        })
    
    # Upsert (vervang bestaande resultaten)
    supabase.table("sroi_results").upsert(
        db_rows,
        on_conflict="import_id,notice_id"  # Of alleen import_id als je 1 resultaat per notice wil
    ).execute()


def run_sroi_analysis_background(import_id: str, owner_code: Optional[str] = None):
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

        # Haal notices op (eigenaar filter)
        notices = get_notices_for_sroi(import_id, owner_code)

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
        save_sroi_results(results, owner_code=owner_code)

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
async def start_sroi_analysis(import_id: str, background_tasks: BackgroundTasks, user_code: str = Depends(validate_user_code)):
    """
    Start SROI analyse voor een import.
    """
    # Check if import exists and belongs to caller
    resp = supabase.table("imports") \
        .select("id, name, owner_code") \
        .eq("id", import_id) \
        .execute()
    
    if not resp.data:
        raise HTTPException(status_code=404, detail="Import niet gevonden")
    if resp.data[0].get("owner_code") != user_code:
        raise HTTPException(status_code=403, detail="Je hebt geen toestemming voor deze import")
    
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
    
    # Start background task (pass owner_code so saved results are scoped)
    background_tasks.add_task(run_sroi_analysis_background, import_id, user_code)
    
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


def save_notice_sroi_result(result: Dict, owner_code: str):
    """
    Sla één SROI resultaat op voor een specifieke notice (winner of buyer).
    
    Args:
        result: Dictionary met SROI analyse resultaat
        owner_code: User code van de eigenaar
    """
    if not result:
        return
    
    # Map result naar database format
    db_row = {
        "notice_id": result.get("notice_id"),
        "target": result.get("target", "winner"),  # winner or buyer
        "company_name": result.get("winner_name") or result.get("company_name"),
        "analyzed_url": result.get("analyzed_url"),
        "url_source": result.get("url_source"),
        "sroi_compliant": result.get("sroi_compliant", False),
        "confidence": result.get("confidence", "none"),
        "score": result.get("score", 0),
        "evidence": result.get("evidence", []),  # Supabase JSONB
        "summary": result.get("summary", ""),
        "pages_checked": result.get("pages_checked", 0),
        "error": result.get("error"),
        "owner_code": owner_code,
    }
    
    # Upsert (vervang bestaand resultaat voor deze notice + target combinatie)
    supabase.table("notice_sroi_results").upsert(
        db_row,
        on_conflict="notice_id,target"
    ).execute()

@app.get("/imports/{import_id}/sroi-status")
async def get_sroi_status(import_id: str, user_code: str = Depends(validate_user_code)):
    """
    Haal de status op van een lopende SROI analyse.
    """
    # ensure import belongs to user
    imp = supabase.table("imports").select("id, owner_code").eq("id", import_id).limit(1).execute()
    if not imp.data:
        raise HTTPException(status_code=404, detail="Import niet gevonden")
    if imp.data[0].get("owner_code") != user_code:
        raise HTTPException(status_code=403, detail="Je hebt geen toegang tot de status van deze import")

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
async def get_sroi_results(import_id: str, user_code: str = Depends(validate_user_code)):
    """
    Haal SROI resultaten op voor een import.
    """
    # Only fetch results for this owner's import
    resp = supabase.table("sroi_results") \
        .select("*") \
        .eq("import_id", import_id) \
        .eq("owner_code", user_code) \
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


@app.get("/imports/{import_id}/notices/{notice_id}/sroi-results")
async def get_notice_sroi_results(
    import_id: str, 
    notice_id: str, 
    user_code: str = Depends(validate_user_code)
):
    """
    Haal SROI resultaat op voor een specifieke notice.
    """
    # Verify import ownership
    imp = supabase.table("imports").select("id, owner_code").eq("id", import_id).limit(1).execute()
    if not imp.data:
        raise HTTPException(status_code=404, detail="Import niet gevonden")
    if imp.data[0].get("owner_code") != user_code:
        raise HTTPException(status_code=403, detail="Je hebt geen toegang tot deze import")
    
    # Fetch result for this notice
    resp = (
        supabase.table("notice_sroi_results")
        .select("*")
        .eq("notice_id", notice_id)
        .eq("owner_code", user_code)
        .limit(1)
        .execute()
    )
    
    if not resp.data:
        return {
            "notice_id": notice_id,
            "result": None,
            "message": "Nog geen analyse beschikbaar voor deze notice"
        }
    
    result = resp.data[0]
    
    
    return {
        "notice_id": notice_id,
        "result": result
    }


@app.delete("/imports/{import_id}/sroi-results")
async def delete_sroi_results(import_id: str, user_code: str = Depends(validate_user_code)):
    """
    Verwijder SROI resultaten (om opnieuw te analyseren).
    """
    # ensure import belongs to user
    imp = supabase.table("imports").select("id, owner_code").eq("id", import_id).limit(1).execute()
    if not imp.data:
        raise HTTPException(status_code=404, detail="Import niet gevonden")
    if imp.data[0].get("owner_code") != user_code:
        raise HTTPException(status_code=403, detail="Je hebt geen toegang tot deze import")

    resp = supabase.table("sroi_results") \
        .delete() \
        .eq("import_id", import_id) \
        .eq("owner_code", user_code) \
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
def get_notice_detail(import_id: str, notice_id: str, user_code: str = Depends(validate_user_code)):
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
            .eq("owner_code", user_code)
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

@app.post("/imports/{import_id}/notices/{notice_id}/sroi-analyze")
async def analyze_single_notice(import_id: str, notice_id: str, request: Request, user_code: str = Depends(validate_user_code)):
    """
    Analyseer één specifieke notice / bedrijf (winnaar of inkoper) en sla resultaat direct op.
    Body (optioneel): { "target": "winner" | "buyer" }
    """
    try:
        if not notice_id:
            raise HTTPException(status_code=400, detail="Notice ID is missing or invalid")

        try:
            body = await request.json()
        except Exception:
            body = {}

        target = (body or {}).get("target", "winner") if isinstance(body, dict) else "winner"

        # Verify import exists and ownership
        imp = supabase.table("imports").select("id, owner_code").eq("id", import_id).execute()
        if not imp.data:
            raise HTTPException(status_code=404, detail="Import niet gevonden")
        if imp.data[0].get("owner_code") != user_code:
            raise HTTPException(status_code=403, detail="Je hebt geen toegang tot deze import")

        # Fetch the notice record
        resp = (
            supabase.table("notices")
            .select("*")
            .eq("import_id", import_id)
            .eq("id", notice_id)
            .eq("owner_code", user_code)
            .execute()
        )

        if not resp.data:
            raise HTTPException(status_code=404, detail="Notice niet gevonden")

        notice = resp.data[0]

        # If caller requested the buyer specifically, coerce fields so analyze_notice_sroi targets buyer
        notice_for_analysis = dict(notice)
        if target == "buyer":
            notice_for_analysis["win_bedrijf_naam"] = notice.get("buyer_bedrijf_naam")
            notice_for_analysis["win_website"] = notice.get("buyer_website")

        # Run analysis
        try:
            result = analyze_notice_sroi(notice_for_analysis)
        except Exception as e:
            raise HTTPException(status_code=500, detail=f"Analyse mislukt: {e}")

        # Attach metadata
        result["notice_id"] = notice_id
        result["target"] = target
        
        # Save using new function
        save_notice_sroi_result(result, owner_code=user_code)

        return result

    except HTTPException:
        raise
    except Exception as e:
        print("ERROR in analyze_single_notice:", e)
        raise HTTPException(status_code=500, detail=str(e))


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
    owner_code TEXT,
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
CREATE INDEX IF NOT EXISTS idx_crm_companies_owner ON crm_companies (owner_code);
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
def crm_list_companies(q: Optional[str] = Query(None, description="Search by name substring"), status: Optional[str] = Query(None), user_code: str = Depends(validate_user_code)):
    """List companies (leads). Optional search by name and filter by lead_status."""
    ok, err = _ensure_crm_tables_ok()
    if not ok:
        raise HTTPException(status_code=500, detail={"error": "CRM tables not found", "advice": "Call /crm/init and run SQL in Supabase" , "raw": err})

    query = supabase.table("crm_companies").select("*").eq("owner_code", user_code)
    if q:
        # simple ilike search
        query = query.ilike("name", f"%{q}%")
    if status:
        query = query.eq("lead_status", status)

    resp = query.order("updated_at", desc=True).limit(100).execute()
    return resp.data or []


@app.post("/crm/companies")
def crm_create_company(payload: dict, user_code: str = Depends(validate_user_code)):
    """Create a new company lead. Expected JSON payload keys: name (required), website, kvk, contact_name, contact_email, source_notice_id, notes, lead_status"""
    ok, err = _ensure_crm_tables_ok()
    if not ok:
        raise HTTPException(status_code=500, detail={"error": "CRM tables not found", "advice": "Call /crm/init and run SQL in Supabase" , "raw": err})

    if not payload.get("name"):
        raise HTTPException(status_code=400, detail="Field 'name' is required")

    payload.setdefault("created_at", dt.datetime.utcnow().isoformat())
    payload.setdefault("updated_at", dt.datetime.utcnow().isoformat())
    # attach owner
    payload["owner_code"] = user_code

    resp = supabase.table("crm_companies").insert(payload).execute()
    if getattr(resp, "error", None):
        raise HTTPException(status_code=500, detail=str(resp.error))
    return resp.data[0]


@app.get("/crm/companies/{company_id}")
def crm_get_company(company_id: int, user_code: str = Depends(validate_user_code)):
    ok, err = _ensure_crm_tables_ok()
    if not ok:
        raise HTTPException(status_code=500, detail={"error": "CRM tables not found", "advice": "Call /crm/init and run SQL in Supabase" , "raw": err})

    resp = supabase.table("crm_companies").select("*").eq("id", company_id).limit(1).execute()
    if not resp.data:
        raise HTTPException(status_code=404, detail="Company not found")
    company = resp.data[0]
    if company.get("owner_code") != user_code:
        raise HTTPException(status_code=403, detail="Je hebt geen toegang tot dit bedrijf")

    # fetch followups
    fresp = supabase.table("crm_followups").select("*").eq("company_id", company_id).order("scheduled_at", desc=False).execute()
    followups = fresp.data or []
    company["followups"] = followups
    return company


@app.patch("/crm/companies/{company_id}")
def crm_update_company(company_id: int, payload: dict, user_code: str = Depends(validate_user_code)):
    ok, err = _ensure_crm_tables_ok()
    if not ok:
        raise HTTPException(status_code=500, detail={"error": "CRM tables not found", "advice": "Call /crm/init and run SQL in Supabase" , "raw": err})

    payload["updated_at"] = dt.datetime.utcnow().isoformat()
    # ensure company belongs to user
    check = supabase.table("crm_companies").select("owner_code").eq("id", company_id).limit(1).execute()
    if not check.data:
        raise HTTPException(status_code=404, detail="Company not found")
    if check.data[0].get("owner_code") != user_code:
        raise HTTPException(status_code=403, detail="Je hebt geen toestemming om dit bedrijf te bewerken")

    payload["owner_code"] = user_code
    resp = supabase.table("crm_companies").update(payload).eq("id", company_id).execute()
    if getattr(resp, "error", None):
        raise HTTPException(status_code=500, detail=str(resp.error))
    if not resp.data:
        raise HTTPException(status_code=404, detail="Company not found or not updated")
    return resp.data[0]


@app.post("/crm/companies/{company_id}/followups")
def crm_add_followup(company_id: int, payload: dict, user_code: str = Depends(validate_user_code)):
    """Add a follow-up action/note for a company. payload keys: scheduled_at (ISO), action, note, emailed (bool), completed (bool), created_by"""
    ok, err = _ensure_crm_tables_ok()
    if not ok:
        raise HTTPException(status_code=500, detail={"error": "CRM tables not found", "advice": "Call /crm/init and run SQL in Supabase" , "raw": err})

    # validate company exists and belongs to user
    cresp = supabase.table("crm_companies").select("id, owner_code").eq("id", company_id).limit(1).execute()
    if not cresp.data:
        raise HTTPException(status_code=404, detail="Company not found")
    if cresp.data[0].get("owner_code") != user_code:
        raise HTTPException(status_code=403, detail="Je hebt geen toestemming om followups voor dit bedrijf toe te voegen")

    payload["company_id"] = company_id
    payload.setdefault("created_at", dt.datetime.utcnow().isoformat())
    payload.setdefault("updated_at", dt.datetime.utcnow().isoformat())

    resp = supabase.table("crm_followups").insert(payload).execute()
    if getattr(resp, "error", None):
        raise HTTPException(status_code=500, detail=str(resp.error))
    return resp.data[0]


@app.get("/crm/companies/{company_id}/followups")
def crm_list_followups(company_id: int, user_code: str = Depends(validate_user_code)):
    ok, err = _ensure_crm_tables_ok()
    if not ok:
        raise HTTPException(status_code=500, detail={"error": "CRM tables not found", "advice": "Call /crm/init and run SQL in Supabase" , "raw": err})

    # ensure company belongs to user
    cresp = supabase.table("crm_companies").select("owner_code").eq("id", company_id).limit(1).execute()
    if not cresp.data:
        raise HTTPException(status_code=404, detail="Company not found")
    if cresp.data[0].get("owner_code") != user_code:
        raise HTTPException(status_code=403, detail="Je hebt geen toegang tot de followups van dit bedrijf")

    resp = supabase.table("crm_followups").select("*").eq("company_id", company_id).order("scheduled_at", desc=False).execute()
    return resp.data or []


@app.patch("/crm/followups/{followup_id}")
def crm_update_followup(followup_id: int, payload: dict, user_code: str = Depends(validate_user_code)):
    ok, err = _ensure_crm_tables_ok()
    if not ok:
        raise HTTPException(status_code=500, detail={"error": "CRM tables not found", "advice": "Call /crm/init and run SQL in Supabase" , "raw": err})

    # ensure followup belongs to a company owned by user
    fcheck = supabase.table("crm_followups").select("company_id").eq("id", followup_id).limit(1).execute()
    if not fcheck.data:
        raise HTTPException(status_code=404, detail="Followup not found")
    company_id = fcheck.data[0].get("company_id")
    cresp = supabase.table("crm_companies").select("owner_code").eq("id", company_id).limit(1).execute()
    if not cresp.data or cresp.data[0].get("owner_code") != user_code:
        raise HTTPException(status_code=403, detail="Je hebt geen toestemming om deze followup te bewerken")

    payload["updated_at"] = dt.datetime.utcnow().isoformat()
    resp = supabase.table("crm_followups").update(payload).eq("id", followup_id).execute()
    if getattr(resp, "error", None):
        raise HTTPException(status_code=500, detail=str(resp.error))
    if not resp.data:
        raise HTTPException(status_code=404, detail="Followup not found or not updated")
    return resp.data[0]


# Runnen:
# uvicorn serve:app --reload --port 8000