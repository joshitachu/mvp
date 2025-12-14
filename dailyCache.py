import os
from datetime import date, datetime, timedelta
from typing import Any, Dict, List, Optional
from collections import defaultdict

from sqlalchemy.orm import Session
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy import and_
from final_tenderned import run_import
from database import get_db, engine
from models import TendernedRaw, TendernedRawCached, TendernedRawCPVCached
import dotenv

dotenv.load_dotenv()

# --------------------------
# CPV Codes
# --------------------------
CPV_CODES = [
    {"code": "03000000-1", "label": "Landbouw- en veeteelt-, kwekerij-, visserij-, bosbouw- en aanverwante producten"},
    {"code": "09000000-3", "label": "Aardolieproducten, brandstof, elektriciteit en andere energiebronnen"},
    {"code": "14000000-1", "label": "Mijnbouw, basismetalen en aanverwante producten"},
    {"code": "15000000-8", "label": "Voeding, dranken, tabak en aanverwante producten"},
    {"code": "16000000-5", "label": "Landbouwmachines"},
    {"code": "18000000-9", "label": "Kleding, schoeisel, bagageartikelen en accessoires"},
    {"code": "19000000-6", "label": "Leder, textielweefsels, kunststof en rubber materialen"},
    {"code": "22000000-0", "label": "Drukwerk en aanverwante producten"},
    {"code": "24000000-4", "label": "Chemische producten"},
    {"code": "30000000-9", "label": "Kantoormachines en gegevensverwerkende apparatuur, kantooruitrusting en -benodigdheden, uitgez. meubilair en softwarepakketten"},
    {"code": "31000000-6", "label": "Elektrische machines, apparaten, uitrusting en verbruiksartikelen; verlichting"},
    {"code": "32000000-3", "label": "Radio-, televisie-, communicatie-, telecommunicatietoestellen en aanverwante apparatuur"},
    {"code": "33000000-0", "label": "Medische apparatuur, farmaceutische artikelen en artikelen voor lichaamsverzorging"},
    {"code": "34000000-7", "label": "Vervoersmaterieel en bijbehorende producten"},
    {"code": "35000000-4", "label": "Uitrusting voor veiligheid, brandweer, politie en leger"},
    {"code": "37000000-8", "label": "Muziekinstrumenten, sportartikelen, spelletjes, speelgoed, handwerk, kunstartikelen en toebehoren"},
    {"code": "38000000-5", "label": "Laboratoriuminstrumenten, optische en precisie-instrumenten (uitgezonderd brillen)"},
    {"code": "39000000-2", "label": "Meubelen (m.i.v. kantoormeubelen), inrichtingsartikelen, huishoudelijke apparaten (uitgez. verlichting) en schoonmaakproducten"},
    {"code": "41000000-9", "label": "Verzameld en gezuiverd water"},
    {"code": "42000000-6", "label": "Bedrijfsmachines"},
    {"code": "43000000-3", "label": "Machines voor de mijnbouw, steengroeven en voor de bouw"},
    {"code": "44000000-0", "label": "Structuren en materialen voor de bouw; ondersteunende producten voor de bouw (uitgezonderd elektrische apparatuur)"},
    {"code": "45000000-7", "label": "Bouwwerkzaamheden"},
    {"code": "48000000-8", "label": "Software en informatiesystemen"},
    {"code": "50000000-5", "label": "Reparatie- en onderhoudsdiensten"},
    {"code": "51000000-9", "label": "Installatiediensten (uitgezonderd software)"},
    {"code": "55000000-0", "label": "Diensten voor hotel, restaurant en detailhandel"},
    {"code": "60000000-8", "label": "Vervoersdiensten (uitg. vervoer van afval)"},
    {"code": "63000000-9", "label": "Ondersteunende en aanvullende vervoersdiensten; reisbureaudiensten"},
    {"code": "64000000-6", "label": "Post- en telecommunicatiediensten"},
    {"code": "65000000-3", "label": "Openbare voorzieningen"},
    {"code": "66000000-0", "label": "Financiële en verzekeringsdiensten"},
    {"code": "70000000-1", "label": "Makelaarsdiensten"},
    {"code": "71000000-8", "label": "Dienstverlening op het gebied van architectuur, bouwkunde, civiele techniek en inspectie"},
    {"code": "72000000-5", "label": "IT-diensten: adviezen, softwareontwikkeling, internet en ondersteuning"},
    {"code": "73000000-2", "label": "Onderzoek en ontwikkeling, en aanverwante adviezen"},
    {"code": "75000000-6", "label": "Diensten voor openbaar bestuur, defensie en sociale verzekering"},
    {"code": "76000000-3", "label": "Diensten in verband met de olie- en gasindustrie"},
    {"code": "77000000-0", "label": "Diensten voor land-, bos- en tuinbouw, aquicultuur en imkerij"},
    {"code": "79000000-4", "label": "Zakelijke dienstverlening: juridisch, marketing, consulting, drukkerij en beveiliging"},
    {"code": "80000000-4", "label": "Diensten voor onderwijs en opleiding"},
    {"code": "85000000-9", "label": "Gezondheidszorg en maatschappelijk werk"},
    {"code": "90000000-7", "label": "Diensten inzake afvalwater, afval, reiniging en milieu"},
    {"code": "92000000-1", "label": "Cultuur-, sport- en recreatiediensten"},
    {"code": "98000000-3", "label": "Overige gemeenschaps-, sociale en persoonlijke diensten"},
]

# --------------------------
# Province mapping
# --------------------------
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

CITY_TO_PROVINCE = {}
for prov, cities in PROVINCE_TO_CITIES.items():
    for c in cities:
        CITY_TO_PROVINCE[c.lower()] = prov


def map_city_to_province(city: Optional[str]) -> Optional[str]:
    """Return province name for a given city string (case-insensitive)"""
    if not city:
        return None
    city_norm = city.strip().lower()
    
    if city_norm in CITY_TO_PROVINCE:
        return CITY_TO_PROVINCE[city_norm]
    
    for known_city, prov in CITY_TO_PROVINCE.items():
        if known_city in city_norm:
            return prov
    
    return None


# --------------------------
# Mapping functions
# --------------------------
def map_import_to_raw_schema(import_row: dict) -> dict:
    """Map import record to tenderned_raw schema"""
    pub_datum = import_row.get("contract_issue_date") or import_row.get("publicatie_datum")
    if pub_datum and isinstance(pub_datum, str):
        pub_datum = pub_datum[:10] if len(pub_datum) >= 10 else pub_datum
    
    return {
        "notice_id": import_row.get("notice_id"),
        "publicatie_id": import_row.get("publicatieId") or import_row.get("publicatie_id"),
        "Publicatiedatum": pub_datum,
        "publicatie_datum": pub_datum,
        "Naam_aanbesteding": import_row.get("titel"),
        "titel": import_row.get("titel"),
        "Omschrijving_aanbesteding": import_row.get("omschrijving"),
        "omschrijving": import_row.get("omschrijving"),
        "URL_TenderNed": import_row.get("URL") or import_row.get("url"),
        "url": import_row.get("URL") or import_row.get("url"),
        "Officiele_benaming": import_row.get("win_bedrijf_naam"),
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
        "Naam_Aanbestedende_dienst": import_row.get("buyer_bedrijf_naam"),
        "buyer_bedrijf_naam": import_row.get("buyer_bedrijf_naam"),
        "Nationaal_identificatienummer": import_row.get("buyer_kvk"),
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
        "Waarde_valuta": import_row.get("valuta"),
        "valuta": import_row.get("valuta"),
        "owner_code": import_row.get("owner_code"),
    }


def map_import_to_cpv_cached_schema(import_row: dict, cpv_code: str, cpv_label: str) -> dict:
    """Map import record to tenderned_raw_cpv_cached schema"""
    pub_datum = import_row.get("contract_issue_date") or import_row.get("publicatie_datum")
    if pub_datum and isinstance(pub_datum, str):
        pub_datum = pub_datum[:10] if len(pub_datum) >= 10 else pub_datum
    
    win_plaats = import_row.get("win_plaats")
    province = map_city_to_province(win_plaats)
    
    return {
        "notice_id": import_row.get("notice_id"),
        "publicatie_id": import_row.get("publicatieId") or import_row.get("publicatie_id"),
        "Publicatiedatum": pub_datum,
        "publicatie_datum": pub_datum,
        "Naam_aanbesteding": import_row.get("titel"),
        "titel": import_row.get("titel"),
        "Omschrijving_aanbesteding": import_row.get("omschrijving"),
        "omschrijving": import_row.get("omschrijving"),
        "URL_TenderNed": import_row.get("URL") or import_row.get("url"),
        "url": import_row.get("URL") or import_row.get("url"),
        "cpv_code": cpv_code,
        "cpv_label": cpv_label,
        "Officiele_benaming": import_row.get("win_bedrijf_naam"),
        "win_bedrijf_naam": import_row.get("win_bedrijf_naam"),
        "Kvknummer": import_row.get("win_kvk"),
        "win_kvk": import_row.get("win_kvk"),
        "Postadres": import_row.get("win_straat"),
        "win_straat": import_row.get("win_straat"),
        "Postcode": import_row.get("win_postcode"),
        "win_postcode": import_row.get("win_postcode"),
        "Plaats": import_row.get("win_plaats"),
        "win_plaats": win_plaats,
        "province": province,
        "Land": import_row.get("win_land"),
        "win_land": import_row.get("win_land"),
        "win_contact_naam": import_row.get("win_contact_naam"),
        "win_contact_email": import_row.get("win_contact_email"),
        "win_contact_tel": import_row.get("win_contact_tel"),
        "Internetadres": import_row.get("win_website"),
        "win_website": import_row.get("win_website"),
        "Naam_Aanbestedende_dienst": import_row.get("buyer_bedrijf_naam"),
        "buyer_bedrijf_naam": import_row.get("buyer_bedrijf_naam"),
        "Nationaal_identificatienummer": import_row.get("buyer_kvk"),
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
        "Waarde_valuta": import_row.get("valuta"),
        "valuta": import_row.get("valuta"),
        "owner_code": import_row.get("owner_code"),
    }


# --------------------------
# Batch upsert helper (PostgreSQL)
# --------------------------
def upsert_rows_in_batches(db: Session, model_class, rows: List[Dict[str, Any]], batch_size: int = 300):
    """Upsert rows in batches using PostgreSQL ON CONFLICT"""
    seen = {}
    for row in rows:
        notice_id = row.get("notice_id")
        if notice_id:
            seen[notice_id] = row
    
    deduped_rows = list(seen.values())
    original_count = len(rows)
    deduped_count = len(deduped_rows)
    
    if original_count != deduped_count:
        print(f"  ⚠️ Removed {original_count - deduped_count} duplicate notice_ids from batch")
    
    total = deduped_count
    print(f"  ⚙️ Upserting {total} unique rows into {model_class.__tablename__} in batches of {batch_size}...")

    for i in range(0, total, batch_size):
        batch = deduped_rows[i : i + batch_size]
        
        try:
            for row in batch:
                # Remove None values to avoid overwriting existing data with NULL
                row_clean = {k: v for k, v in row.items() if v is not None}
                
                stmt = insert(model_class).values(**row_clean)
                stmt = stmt.on_conflict_do_update(
                    index_elements=['notice_id'],
                    set_=row_clean
                )
                db.execute(stmt)
            
            db.commit()
            print(f"    ✅ Batch {i // batch_size + 1}/{(total + batch_size - 1) // batch_size} saved")

        except Exception as e:
            print(f"    ❌ Exception during upsert: {e}")
            db.rollback()
            break

    print(f"  ✅ Done upserting to {model_class.__tablename__}")


# --------------------------
# Process single CPV code
# --------------------------
def process_cpv_code(
    db: Session,
    cpv_code: str,
    cpv_label: str,
    date_from: str,
    date_to: str,
    publicatie_type: str,
    max_pages: int,
    cpv_num: int,
    total_cpv: int
):
    """Process a single CPV code and populate both tables"""
    print(f"\n{'='*80}")
    print(f"📊 CPV {cpv_num}/{total_cpv}: {cpv_code} - {cpv_label[:50]}...")
    print(f"📅 Date range: {date_from} → {date_to}")
    print(f"{'='*80}")
    
    print(f"🔍 Fetching records for CPV {cpv_code}...")
    
    try:
        records = run_import(
            date_from=date_from,
            date_to=date_to,
            publicatie_type=publicatie_type,
            cpv_codes=[cpv_code],
            max_pages=max_pages,
        )
    except Exception as e:
        print(f"❌ Error fetching data: {e}")
        return 0

    print(f"✅ Fetched {len(records)} records for CPV {cpv_code}")
    
    if not records:
        print("ℹ️ No records to insert")
        return 0

    # Map to both schemas
    print(f"🔄 Mapping records to both table schemas...")
    raw_rows = [map_import_to_raw_schema(r) for r in records]
    cpv_cached_rows = [map_import_to_cpv_cached_schema(r, cpv_code, cpv_label) for r in records]

    # Filter out rows without notice_id
    raw_rows = [r for r in raw_rows if r.get("notice_id")]
    cpv_cached_rows = [r for r in cpv_cached_rows if r.get("notice_id")]
    
    print(f"📝 {len(raw_rows)} records for tenderned_raw_cached")
    print(f"📝 {len(cpv_cached_rows)} records for tenderned_raw_cpv_cached")

    # Upsert to both cached tables (public schema)
    if raw_rows:
        print(f"💾 Saving to tenderned_raw_cached (public.tenderned_raw_cached)...")
        upsert_rows_in_batches(db, TendernedRawCached, raw_rows, batch_size=300)
    
    if cpv_cached_rows:
        print(f"💾 Saving to tenderned_raw_cpv_cached (public.tenderned_raw_cpv_cached)...")
        upsert_rows_in_batches(db, TendernedRawCPVCached, cpv_cached_rows, batch_size=300)
    
    return len(records)


# --------------------------
# Update eerdere aanbestedingen
# --------------------------
def parse_date(raw):
    """Parse een datum string naar datetime object"""
    if not raw:
        return None
    
    from datetime import date
    if isinstance(raw, (datetime, date)):
        if isinstance(raw, date) and not isinstance(raw, datetime):
            return datetime.combine(raw, datetime.min.time())
        return raw
    
    if isinstance(raw, str):
        try:
            return datetime.fromisoformat(raw)
        except ValueError:
            try:
                return datetime.strptime(raw, "%d-%m-%Y")
            except ValueError:
                try:
                    return datetime.strptime(raw, "%Y-%m-%d")
                except ValueError:
                    return None
    
    return None


def parse_amount(raw):
    """Parse een bedrag naar float"""
    if raw is None:
        return None
    if isinstance(raw, (int, float)):
        return float(raw)
    if isinstance(raw, str):
        txt = raw.replace(".", "").replace(",", ".") if "," in raw else raw
        try:
            return float(txt)
        except ValueError:
            return None
    return None


def update_eerdere_aanbestedingen(batch_size: int = 500, use_cpv_table: bool = False):
    """Update cached table met informatie over eerdere aanbestedingen"""
    
    print(f"\n{'='*80}")
    print(f"🔄 Updating eerdere aanbestedingen for {'CPV cached' if use_cpv_table else 'regular cached'} table")
    print(f"{'='*80}")
    
    db: Session = next(get_db())
    
    try:
        print("Fetching historical data from tenderned_raw...")
        
        raw_data = db.query(
            TendernedRaw.Officiele_benaming,
            TendernedRaw.Publicatiedatum,
            TendernedRaw.bedrag
        ).filter(
            TendernedRaw.Officiele_benaming.isnot(None),
            TendernedRaw.Officiele_benaming != ''
        ).order_by(
            TendernedRaw.Publicatiedatum.asc()
        ).all()
        
        print(f"Loaded {len(raw_data)} records from tenderned_raw")
        
        historical_wins = defaultdict(list)
        
        for row in raw_data:
            bedrijf = (row.Officiele_benaming or "").strip()
            if not bedrijf:
                continue
            
            datum = parse_date(row.Publicatiedatum)
            bedrag = parse_amount(row.bedrag)
            
            historical_wins[bedrijf].append({
                "datum": datum,
                "bedrag": bedrag or 0
            })
        
        print(f"Organized data for {len(historical_wins)} unique companies")
        
        CacheModel = TendernedRawCPVCached if use_cpv_table else TendernedRawCached
        table_name = "tenderned_raw_cpv_cached" if use_cpv_table else "tenderned_raw_cached"
        print(f"Using cache table: {table_name}")
        
        offset = 0
        total_updated = 0
        
        while True:
            cached_rows = db.query(
                CacheModel.id,
                CacheModel.Officiele_benaming,
                CacheModel.Publicatiedatum
            ).filter(
                CacheModel.Officiele_benaming.isnot(None),
                CacheModel.Officiele_benaming != ''
            ).order_by(
                CacheModel.id.asc()
            ).limit(batch_size).offset(offset).all()
            
            if not cached_rows:
                break
            
            print(f"Processing batch: records {offset + 1} to {offset + len(cached_rows)}")
            
            updates_performed = 0
            
            for row in cached_rows:
                row_id = row.id
                bedrijf = (row.Officiele_benaming or "").strip()
                pub_datum = parse_date(row.Publicatiedatum)
                
                if not bedrijf or not row_id:
                    continue
                
                aantal_eerder = 0
                totaal_bedrag_eerder = 0
                
                if bedrijf in historical_wins:
                    for win in historical_wins[bedrijf]:
                        if win["datum"] and pub_datum and win["datum"] < pub_datum:
                            aantal_eerder += 1
                            totaal_bedrag_eerder += win["bedrag"]
                
                try:
                    db.query(CacheModel).filter(
                        CacheModel.id == row_id
                    ).update({
                        "aantal_eerdere_aanbestedingen": aantal_eerder,
                        "heeft_eerdere_aanbestedingen": aantal_eerder > 0,
                        "totaal_bedrag_eerdere_aanbestedingen": totaal_bedrag_eerder
                    }, synchronize_session=False)
                    
                    updates_performed += 1
                    
                except Exception as e:
                    print(f"❌ Error updating id {row_id}: {e}")
                    db.rollback()
                    continue
            
            db.commit()
            
            total_updated += updates_performed
            print(f"Updated {updates_performed} records. Total so far: {total_updated}")
            
            offset += batch_size
            
            if len(cached_rows) < batch_size:
                break
        
        print(f"✅ Complete! Updated {total_updated} records in total")
        
    except Exception as e:
        print(f"❌ Error during update process: {e}")
        db.rollback()
        raise
    finally:
        db.close()


# --------------------------
# Main function
# --------------------------
def main():
    """Main nightly update function"""
    print("\n" + "=" * 80)
    print("🌙 NIGHTLY TENDERNED UPDATE STARTED")
    print(f"⏰ Start time: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print("=" * 80)
    
    # Calculate yesterday's date for incremental updates
    yesterday = (datetime.now() - timedelta(days=1)).strftime("%Y-%m-%d")
    today = datetime.now().strftime("%Y-%m-%d")
    
    date_from = os.getenv("TN_DATE_FROM", yesterday)
    date_to = os.getenv("TN_DATE_TO", today)
    
    publicatie_type = os.getenv("TN_PUBLICATIE_TYPE", "AGO")
    
    max_pages_env = os.getenv("TN_MAX_PAGES")
    max_pages = int(max_pages_env) if max_pages_env else None

    print(f"📅 Date range: {date_from} → {date_to}")
    print(f"📋 Publicatie type: {publicatie_type}")
    print(f"🔢 Total CPV codes: {len(CPV_CODES)}")
    print(f"📄 Max pages per CPV: {max_pages if max_pages else 'No limit'}")
    print("=" * 80)

    # Create database session
    db: Session = next(get_db())
    
    try:
        # STEP 1: Process all CPV codes and populate both tables
        print("\n" + "=" * 80)
        print("📥 STEP 1: FETCHING AND POPULATING DATA")
        print("=" * 80)
        
        total_processed = 0
        successful_cpvs = 0
        failed_cpvs = []
        
        for i, cpv_info in enumerate(CPV_CODES, 1):
            cpv_code = cpv_info["code"]
            cpv_label = cpv_info["label"]
            
            try:
                count = process_cpv_code(
                    db=db,
                    cpv_code=cpv_code,
                    cpv_label=cpv_label,
                    date_from=date_from,
                    date_to=date_to,
                    publicatie_type=publicatie_type,
                    max_pages=max_pages,
                    cpv_num=i,
                    total_cpv=len(CPV_CODES)
                )
                total_processed += count
                successful_cpvs += 1
                
                print(f"✅ CPV {i}/{len(CPV_CODES)} complete: {count} records")
                
            except Exception as e:
                print(f"❌ CPV {i}/{len(CPV_CODES)} failed: {e}")
                failed_cpvs.append(cpv_code)
        
        print("\n" + "=" * 80)
        print("✅ DATA POPULATION COMPLETE")
        print("=" * 80)
        print(f"✅ Successfully processed CPV codes: {successful_cpvs}/{len(CPV_CODES)}")
        print(f"📝 Total records processed: {total_processed}")
        
        if failed_cpvs:
            print(f"\n❌ Failed CPV codes ({len(failed_cpvs)}):")
            for cpv in failed_cpvs:
                print(f"   - {cpv}")
        
    finally:
        db.close()
    
    # STEP 2: Update eerdere aanbestedingen for both cached tables
    print("\n" + "=" * 80)
    print("🔄 STEP 2: UPDATING EERDERE AANBESTEDINGEN")
    print("=" * 80)
    
    try:
        print("\n📊 Updating tenderned_raw_cached...")
        update_eerdere_aanbestedingen(batch_size=500, use_cpv_table=False)
    except Exception as e:
        print(f"❌ Error updating tenderned_raw_cached: {e}")
    
    try:
        print("\n📊 Updating tenderned_raw_cpv_cached...")
        update_eerdere_aanbestedingen(batch_size=500, use_cpv_table=True)
    except Exception as e:
        print(f"❌ Error updating tenderned_raw_cpv_cached: {e}")
    
    # Final summary
    print("\n" + "=" * 80)
    print("🎉 NIGHTLY UPDATE COMPLETE")
    print(f"⏰ End time: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print("=" * 80)


if __name__ == "__main__":
    main()