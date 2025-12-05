import os
from datetime import date
from typing import Any, Dict, List

from supabase import create_client, Client
# ⬇️ adjust this import path to where your run_import lives
from final_tenderned import run_import   # e.g. from app.scraper import run_import


# --------------------------
# Supabase config
# --------------------------
SUPABASE_URL = os.getenv("SUPABASE_URL")
SUPABASE_KEY = os.getenv("SUPABASE_KEY")

if not SUPABASE_URL or not SUPABASE_KEY:
    raise RuntimeError("SUPABASE_URL and SUPABASE_KEY must be set")

supabase: Client = create_client(SUPABASE_URL, SUPABASE_KEY)

TABLE_NAME = "tenderned_cached"


# --------------------------
# Mapping: run_import record -> tenderned_raw row
# --------------------------
def map_record_to_tenderned_raw(rec: Dict[str, Any]) -> Dict[str, Any]:
    """
    Neem één record uit run_import (parse_publicatie_xml + meta)
    en mapt het naar de kolommen van public.tenderned_raw.
    Alles wat we niet hebben laten we gewoon op None.
    """

    # Publicatie-id & URLs
    publicatie_id = rec.get("publicatieId") or rec.get("publicatie_id")
    notice_id = rec.get("notice_id") or str(publicatie_id)  # desnoods gelijk aan publicatie_id
    url = rec.get("URL") or rec.get("url")

    # Titel / omschrijving / publicatiedatum
    titel = rec.get("titel") or rec.get("Naam aanbesteding")
    omschrijving = rec.get("omschrijving") or rec.get("Omschrijving aanbesteding")

    publicatie_datum = (
        rec.get("publicatie_datum")
        or rec.get("Publicatiedatum")
        or rec.get("publicatiedatum")
    )

    # Aanvang / voltooiing / gunning
    aanvang_opdracht = rec.get("Aanvang opdracht") or rec.get("aanvang_opdracht")
    voltooiing_opdracht = rec.get("Voltooiing opdracht") or rec.get("voltooiing_opdracht")
    datum_gunning = rec.get("Datum gunning") or rec.get("datum_gunning")
    datum_besluit_gunning = rec.get("Datum besluit gunning") or rec.get("datum_besluit_gunning")

    # Winnaar (winnend bedrijf)
    win_bedrijf_naam = rec.get("win_bedrijf_naam") or rec.get("Officiële benaming")
    win_kvk = rec.get("win_kvk") or rec.get("Kvknummer")
    win_straat = rec.get("win_straat") or rec.get("Postadres")
    win_postcode = rec.get("win_postcode") or rec.get("Postcode")
    win_plaats = rec.get("win_plaats") or rec.get("Plaats")
    win_land = rec.get("win_land") or rec.get("Land")
    win_contact_naam = rec.get("win_contact_naam")
    win_contact_email = rec.get("win_contact_email")
    win_contact_tel = rec.get("win_contact_tel")
    win_website = rec.get("win_website") or rec.get("Internetadres")

    # Aanbestedende dienst (buyer)
    buyer_bedrijf_naam = (
        rec.get("buyer_bedrijf_naam")
        or rec.get("Naam Aanbestedende dienst")
        or rec.get("Officiële naam Aanbestedende dienst")
    )
    buyer_kvk = rec.get("buyer_kvk")
    buyer_straat = rec.get("buyer_straat") or rec.get("AD postadres")
    buyer_postcode = rec.get("buyer_postcode") or rec.get("AD postcode")
    buyer_plaats = rec.get("buyer_plaats") or rec.get("AD plaats")
    buyer_land = rec.get("buyer_land") or rec.get("AD land")
    buyer_contact_naam = rec.get("buyer_contact_naam")
    buyer_contact_email = rec.get("buyer_contact_email")
    buyer_contact_tel = rec.get("buyer_contact_tel")
    buyer_website = rec.get("buyer_website") or rec.get("Internetadres aanbestedende dienst")

    # Bedragen / valuta
    bedrag = (
        rec.get("bedrag")
        or rec.get("Waarde - bedrag")
        or rec.get("Oorspronkelijk geraamde waarde - bedrag")
    )
    valuta = (
        rec.get("valuta")
        or rec.get("Waarde - valuta")
        or rec.get("Oorspronkelijk geraamde waarde - valuta")
    )

    termijn_voltooiing = rec.get("Termijn voltooiing opdracht")
    tijdseenheid_voltooiing = rec.get("Tijdseenheid periode voltooiing opdracht")

    region = rec.get("region")
    province = rec.get("province")
    owner_code = rec.get("owner_code")
    heeft_eerdere = rec.get("heeft_eerdere_aanbestedingen")
    aantal_eerdere = rec.get("aantal_eerdere_aanbestedingen")

    row = {
        # Originele Excel-achtige kolommen
        "Id publicatie": str(publicatie_id) if publicatie_id is not None else None,
        "Tenderned kenmerk": rec.get("Tenderned kenmerk"),
        "Publicatiedatum": publicatie_datum,
        "Naam Aanbestedende dienst": buyer_bedrijf_naam,
        "Officiële naam Aanbestedende dienst": buyer_bedrijf_naam,
        "Nationaal identificatienummer": rec.get("Nationaal identificatienummer"),
        "Naam aanbesteding": titel,
        "URL TenderNed": url,
        "Omschrijving aanbesteding": omschrijving,
        "Aanvang opdracht": aanvang_opdracht,
        "Voltooiing opdracht": voltooiing_opdracht,
        "Datum gunning": datum_gunning,
        "Datum besluit gunning": datum_besluit_gunning,
        "Officiële benaming": win_bedrijf_naam,
        "Kvknummer": win_kvk,
        "Postadres": win_straat,
        "Plaats": win_plaats,
        "Postcode": win_postcode,
        "Land": win_land,
        "Internetadres": win_website,
        "Waarde - valuta": valuta,
        "Termijn voltooiing opdracht": termijn_voltooiing,
        "Tijdseenheid periode voltooiing opdracht": tijdseenheid_voltooiing,

        # Nieuwe normalized velden
        "bedrag": bedrag,
        "notice_id": notice_id,
        "publicatie_id": publicatie_id,
        "url": url,
        "titel": titel,
        "omschrijving": omschrijving,

        "win_bedrijf_naam": win_bedrijf_naam,
        "win_kvk": win_kvk,
        "win_straat": win_straat,
        "win_postcode": win_postcode,
        "win_plaats": win_plaats,
        "win_land": win_land,
        "win_contact_naam": win_contact_naam,
        "win_contact_email": win_contact_email,
        "win_contact_tel": win_contact_tel,
        "win_website": win_website,

        "buyer_bedrijf_naam": buyer_bedrijf_naam,
        "buyer_kvk": buyer_kvk,
        "buyer_straat": buyer_straat,
        "buyer_postcode": buyer_postcode,
        "buyer_plaats": buyer_plaats,
        "buyer_land": buyer_land,
        "buyer_contact_naam": buyer_contact_naam,
        "buyer_contact_email": buyer_contact_email,
        "buyer_contact_tel": buyer_contact_tel,
        "buyer_website": buyer_website,

        "valuta": valuta,
        "region": region,
        "province": province,
        "heeft_eerdere_aanbestedingen": heeft_eerdere,
        "aantal_eerdere_aanbestedingen": aantal_eerdere,
        "owner_code": owner_code,
        "publicatie_datum": publicatie_datum,
    }

    return row


# --------------------------
# Batch insert helper
# --------------------------
def insert_rows_in_batches(rows: List[Dict[str, Any]], batch_size: int = 300):
    total = len(rows)
    print(f"⚙️ Insert {total} rows into {TABLE_NAME} in batches of {batch_size}...")

    for i in range(0, total, batch_size):
        batch = rows[i : i + batch_size]
        print(f"  → inserting batch {i}..{i + len(batch) - 1}")

        resp = supabase.table(TABLE_NAME).insert(batch).execute()

        # supabase-py v2: check resp.get("error") if needed; older: resp.error
        if getattr(resp, "error", None):
            print("Insert error:", resp.error)
            break

    print("✅ Done inserting into tenderned_raw")


# --------------------------
# Main: use TenderNed API instead of Excel
# --------------------------
def main():
    # Range: 2023-01-01 → today (can be overridden by env vars)
    date_from = os.getenv("TN_DATE_FROM", "2023-01-01")
    date_to = os.getenv("TN_DATE_TO", date.today().isoformat())

    publicatie_type = os.getenv("TN_PUBLICATIE_TYPE", "AGO")
    cpv_codes_env = os.getenv("TN_CPV_CODES")
    cpv_codes = cpv_codes_env.split(",") if cpv_codes_env else None

    max_pages_env = os.getenv("TN_MAX_PAGES")
    max_pages = int(max_pages_env) if max_pages_env else None

    print(f"🚀 run_import via TenderNed API: {date_from} → {date_to} (type={publicatie_type})")

    records = run_import(
        date_from=date_from,
        date_to=date_to,
        publicatie_type=publicatie_type,
        cpv_codes=cpv_codes,
        max_pages=max_pages,
        save_xml=False,
    )

    print(f"✅ run_import returned {len(records)} records")

    if not records:
        print("ℹ️ No records to insert into tenderned_raw")
        return

    rows = [map_record_to_tenderned_raw(r) for r in records]

    insert_rows_in_batches(rows, batch_size=300)


if __name__ == "__main__":
    main()
