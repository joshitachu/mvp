import pandas as pd
from datetime import datetime

EXCEL_PATH = 'Dataset_TenderNed_2016_2024_herzien.xlsx'
SHEET_NAME = 'Dataset 2016-2024'

# --------------------------
# 1. Load Excel
# --------------------------
try:
    df = pd.read_excel(EXCEL_PATH, sheet_name=SHEET_NAME, engine='openpyxl')
except FileNotFoundError:
    print(f"Error: Excel file '{EXCEL_PATH}' not found.")
    raise

print(f"Loaded {len(df)} total rows.")
print("Available columns:", list(df.columns))

# --------------------------
# 2. Required columns
# --------------------------
required_cols = [
    'Publicatiedatum',
    'Omschrijving aanbesteding',
    'Officiële benaming',
    'Kvknummer',
    'Internetadres',
    'Aanvang opdracht',
    'Voltooiing opdracht',
    
]

# Check columns exist
for col in required_cols:
    if col not in df.columns:
        raise KeyError(f"Column '{col}' not found in Excel. Check your header names.")

# Keep only required columns
df = df[required_cols].copy()

# --------------------------
# 3. Ask user for a date
# --------------------------
user_input = input("Voer een datum in (YYYY-MM-DD): ")

try:
    user_date = pd.to_datetime(user_input, format="%Y-%m-%d")
except ValueError:
    raise ValueError("Invalid date format. Use YYYY-MM-DD.")

# --------------------------
# 4. Convert Publicatiedatum to datetime
# --------------------------
df['Publicatiedatum'] = pd.to_datetime(df['Publicatiedatum'], errors='coerce')

# Remove rows with invalid/missing dates
df = df.dropna(subset=['Publicatiedatum'])

# --------------------------
# 5. Filter rows >= user input
# --------------------------
filtered_df = df[df['Publicatiedatum'] >= user_date]

print(f"\nAantal rijen vanaf {user_date.date()}: {len(filtered_df)}")
print(filtered_df.head())

# --------------------------
# 6. Save results
# --------------------------
OUT_PATH = 'TenderNed_filtered.csv'
filtered_df.to_csv(OUT_PATH, index=False, encoding='utf-8')

print(f"\nResultaten opgeslagen in '{OUT_PATH}'")
