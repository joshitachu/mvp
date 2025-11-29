import os
from datetime import datetime

import pandas as pd
from supabase import create_client, Client
import numpy as np


# --------------------------
# Supabase config
# --------------------------
SUPABASE_URL = os.getenv("SUPABASE_URL" )
SUPABASE_KEY = os.getenv("SUPABASE_KEY")


supabase: Client = create_client(SUPABASE_URL, SUPABASE_KEY)

# --------------------------
# Excel config
# --------------------------
EXCEL_PATH = "Dataset_TenderNed_2016_2024_herzien.xlsx"
SHEET_NAME = "Dataset 2016-2024"

# --------------------------
# Columns you want to keep EXACTLY
# --------------------------
COLUMNS = [
    "Id publicatie",
    "Tenderned kenmerk",
    "Publicatiedatum",
    "Naam Aanbestedende dienst",
    "Officiële naam Aanbestedende dienst",
    "Nationaal identificatienummer",
    "Naam aanbesteding",
    "URL TenderNed",
    "Omschrijving aanbesteding",
    "Aanvang opdracht",
    "Voltooiing opdracht",
    "Datum gunning",
    "Datum besluit gunning",
    "Officiële benaming",
    "Kvknummer",
    "Postadres",
    "Plaats",
    "Postcode",
    "Land",
    "Internetadres",
    "Waarde - bedrag",
    "Waarde - valuta",
    "Termijn voltooiing opdracht",
    "Tijdseenheid periode voltooiing opdracht",
]

TABLE_NAME = "tenderned_raw"   # change if needed


def main():
    # --------------------------
    # 1) Load Excel
    # --------------------------
    df = pd.read_excel(EXCEL_PATH, sheet_name=SHEET_NAME, engine="openpyxl")
    print(f"Loaded {len(df)} rows from Excel.")

    # --------------------------
    # 2) Keep only the desired columns
    # --------------------------
    missing = [c for c in COLUMNS if c not in df.columns]
    if missing:
        raise KeyError(f"Missing columns in Excel: {missing}")

    df = df[COLUMNS].copy()

    # --------------------------
    # 3) Convert date columns to ISO (YYYY-MM-DD)
    # --------------------------
    # 3) Convert date columns to ISO (YYYY-MM-DD) **as strings**
# --------------------------
    DATE_COLS = [
        "Publicatiedatum",
        "Aanvang opdracht",
        "Voltooiing opdracht",
        "Datum gunning",
        "Datum besluit gunning",
    ]

    for col in DATE_COLS:
        # parse with dayfirst=True, then format as string
        parsed = pd.to_datetime(df[col], errors="coerce", dayfirst=True)
        df[col] = parsed.dt.strftime("%Y-%m-%d")


    # --------------------------
    # 4) Convert NaN -> None for Supabase
    # --------------------------
# 4) Convert NaN / NaT -> None for all columns
    df = df.replace({np.nan: None})
    df = df.where(pd.notnull(df), None)

    # --------------------------
    # 5) Convert to list of dicts
    # --------------------------
    records = df.to_dict(orient="records")
    import math

    def clean_record(rec: dict) -> dict:
        for k, v in rec.items():
            # Catch leftover float('nan')
            if isinstance(v, float) and math.isnan(v):
                rec[k] = None
        return rec

    records = [clean_record(r) for r in records]

    print(f"Prepared {len(records)} records to upload.")

    if not records:
        print("No rows to upload.")
        return

    # --------------------------
    # 6) Insert in batches
    # --------------------------
    BATCH_SIZE = 300
    inserted = 0

    for i in range(0, len(records), BATCH_SIZE):
        batch = records[i : i + BATCH_SIZE]

        resp = (
            supabase.table(TABLE_NAME)
            .insert(batch)
            .execute()
        )

        if hasattr(resp, "error") and resp.error:
            print("Insert error:", resp.error)
            break

        inserted += len(batch)
        print(f"Inserted {inserted}/{len(records)} rows")

    print("Done.")


if __name__ == "__main__":
    main()
