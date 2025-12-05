import os
from datetime import date, datetime, timedelta
from typing import Any, Dict, List, Optional

from supabase import create_client, Client
from final_tenderned import run_import

# --------------------------
# Supabase config
# --------------------------
SUPABASE_URL = os.getenv("SUPABASE_URL")
SUPABASE_KEY = os.getenv("SUPABASE_KEY")

if not SUPABASE_URL or not SUPABASE_KEY:
    raise RuntimeError("SUPABASE_URL and SUPABASE_KEY must be set")

supabase: Client = create_client(SUPABASE_URL, SUPABASE_KEY)

TABLE_NAME = "tenderned_raw_cpv_cached"  # New table for all CPV codes

# --------------------------
# CPV Codes to query
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


# --------------------------
# Mapping: import record -> tenderned_raw_cpv_cached
# --------------------------
def map_import_to_cache_schema(import_row: dict, cpv_code: str, cpv_label: str) -> dict:
    """Map import record schema naar tenderned_raw_cpv_cached schema"""
    # Haal publicatie_datum op en formatteer correct
    pub_datum = import_row.get("contract_issue_date") or import_row.get("publicatie_datum")
    if pub_datum and isinstance(pub_datum, str):
        # Zorg dat het een date string is (YYYY-MM-DD)
        pub_datum = pub_datum[:10] if len(pub_datum) >= 10 else pub_datum
    
    # Map province based on win_plaats
    win_plaats = import_row.get("win_plaats")
    province = map_city_to_province(win_plaats)
    
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
        "cpv_code": cpv_code,  # Store the CPV code used for the query
        "cpv_label": cpv_label,  # Store the human-readable label
        "Officiële benaming": import_row.get("win_bedrijf_naam"),
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
    }


# --------------------------
# Batch upsert helper (with conflict handling)
# --------------------------
def upsert_rows_in_batches(rows: List[Dict[str, Any]], batch_size: int = 300):
    """Upsert rows in batches to avoid duplicates"""
    # First, deduplicate the entire list by notice_id (keep last occurrence)
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
    print(f"  ⚙️ Upserting {total} unique rows into {TABLE_NAME} in batches of {batch_size}...")

    for i in range(0, total, batch_size):
        batch = deduped_rows[i : i + batch_size]
        
        try:
            resp = supabase.table(TABLE_NAME).upsert(
                batch, 
                on_conflict="notice_id"  # Prevent duplicates
            ).execute()

            if hasattr(resp, 'error') and resp.error:
                print(f"    ❌ Upsert error: {resp.error}")
                break
            else:
                print(f"    ✅ Batch {i // batch_size + 1}/{(total + batch_size - 1) // batch_size} saved")

        except Exception as e:
            print(f"    ❌ Exception during upsert: {e}")
            break

    print(f"  ✅ Done upserting batch")


# --------------------------
# Process single CPV code for a date range
# --------------------------
def process_cpv_code(
    cpv_code: str,
    cpv_label: str,
    date_from: str,
    date_to: str,
    publicatie_type: str,
    max_pages: int,
    cpv_num: int,
    total_cpv: int
):
    """Process a single CPV code for a date range"""
    print(f"\n{'='*80}")
    print(f"📊 CPV {cpv_num}/{total_cpv}: {cpv_code} - {cpv_label[:50]}...")
    print(f"📅 Date range: {date_from} → {date_to}")
    print(f"{'='*80}")
    
    # Fetch records from TenderNed API for this specific CPV code
    print(f"🔍 Fetching records for CPV {cpv_code}...")
    
    try:
        records = run_import(
            date_from=date_from,
            date_to=date_to,
            publicatie_type=publicatie_type,
            cpv_codes=[cpv_code],  # Query this specific CPV code
            max_pages=max_pages,
        )
    except Exception as e:
        print(f"❌ Error fetching data: {e}")
        return 0

    print(f"✅ Fetched {len(records)} records for CPV {cpv_code}")
    
    if not records:
        print("ℹ️ No records to insert")
        return 0

    # Map to cache schema with CPV code
    print(f"🔄 Mapping records to cache schema...")
    cache_rows = [map_import_to_cache_schema(r, cpv_code, cpv_label) for r in records]

    # Filter out rows without notice_id
    cache_rows = [r for r in cache_rows if r.get("notice_id")]
    print(f"📝 {len(cache_rows)} records have valid notice_id")

    if not cache_rows:
        return 0

    # Upsert to database
    print(f"💾 Saving to {TABLE_NAME}...")
    upsert_rows_in_batches(cache_rows, batch_size=300)
    
    return len(cache_rows)


# --------------------------
# Main: Populate cache by iterating through all CPV codes
# --------------------------
def main():
    # Configuration - ONE YEAR
    date_from = os.getenv("TN_DATE_FROM", "2024-01-01")
    date_to = os.getenv("TN_DATE_TO", "2024-12-31")
    
    publicatie_type = os.getenv("TN_PUBLICATIE_TYPE", "AGO")
    
    max_pages_env = os.getenv("TN_MAX_PAGES")
    max_pages = int(max_pages_env) if max_pages_env else None

    print("=" * 80)
    print("🚀 POPULATING TENDERNED_RAW_CPV_CACHED - BY CPV CODE")
    print("=" * 80)
    print(f"📅 Date range: {date_from} → {date_to}")
    print(f"📋 Publicatie type: {publicatie_type}")
    print(f"🔢 Total CPV codes to process: {len(CPV_CODES)}")
    print(f"📄 Max pages per CPV: {max_pages if max_pages else 'No limit'}")
    print("=" * 80)

    # Check current cache status
    print("\n📊 Checking current cache status...")
    try:
        count_resp = supabase.table(TABLE_NAME).select("notice_id", count="exact").execute()
        print(f"📦 Current records in cache: {count_resp.count}")
        
        # Count unique CPV codes already cached
        cpv_resp = supabase.table(TABLE_NAME).select("cpv_code").execute()
        if cpv_resp.data:
            unique_cpvs = set(row.get("cpv_code") for row in cpv_resp.data if row.get("cpv_code"))
            print(f"📊 Unique CPV codes in cache: {len(unique_cpvs)}")
    except Exception as e:
        print(f"⚠️ Could not check cache: {e}")

    # Process each CPV code
    total_processed = 0
    successful_cpvs = 0
    failed_cpvs = []
    
    for i, cpv_info in enumerate(CPV_CODES, 1):
        cpv_code = cpv_info["code"]
        cpv_label = cpv_info["label"]
        
        try:
            count = process_cpv_code(
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
    
    # Final summary
    print("\n" + "=" * 80)
    print("🎉 CACHE POPULATION COMPLETE")
    print("=" * 80)
    print(f"✅ Successfully processed CPV codes: {successful_cpvs}/{len(CPV_CODES)}")
    print(f"📝 Total records processed: {total_processed}")
    
    if failed_cpvs:
        print(f"\n❌ Failed CPV codes ({len(failed_cpvs)}):")
        for cpv in failed_cpvs:
            print(f"   - {cpv}")
    
    # Final cache statistics
    print("\n📊 Final cache statistics:")
    try:
        final_count = supabase.table(TABLE_NAME).select("notice_id", count="exact").execute()
        print(f"📦 Total records in cache: {final_count.count}")
        
        # Count unique CPV codes
        cpv_resp = supabase.table(TABLE_NAME).select("cpv_code").execute()
        if cpv_resp.data:
            unique_cpvs = set(row.get("cpv_code") for row in cpv_resp.data if row.get("cpv_code"))
            print(f"📊 Unique CPV codes cached: {len(unique_cpvs)}/{len(CPV_CODES)}")
            
            # Show CPV distribution
            cpv_counts = {}
            for row in cpv_resp.data:
                cpv = row.get("cpv_code")
                if cpv:
                    cpv_counts[cpv] = cpv_counts.get(cpv, 0) + 1
            
            print(f"\n📈 Top 10 CPV codes by record count:")
            sorted_cpvs = sorted(cpv_counts.items(), key=lambda x: x[1], reverse=True)[:10]
            for cpv, count in sorted_cpvs:
                cpv_info = next((c for c in CPV_CODES if c["code"] == cpv), None)
                label = cpv_info["label"][:40] if cpv_info else "Unknown"
                print(f"   {cpv}: {count:,} records - {label}...")
                
    except Exception as e:
        print(f"⚠️ Could not retrieve final statistics: {e}")
    
    print("\n" + "=" * 80)


if __name__ == "__main__":
    main()