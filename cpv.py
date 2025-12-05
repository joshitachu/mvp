from collections import defaultdict
from datetime import datetime
from supabase import create_client
import os
import dotenv

dotenv.load_dotenv()


# --------------------------

# Supabase config
# --------------------------
SUPABASE_URL = os.getenv("SUPABASE_URL")
SUPABASE_KEY = os.getenv("SUPABASE_KEY")

print(SUPABASE_URL)



# Initialiseer je supabase client
supabase = create_client(SUPABASE_URL, SUPABASE_KEY)

def update_eerdere_aanbestedingen(batch_size: int = 500):
    """
    Update tenderned_raw_cached met informatie over eerdere aanbestedingen
    van dezelfde winnaar uit tenderned_raw.
    
    Voor elke winnaar in tenderned_raw_cached:
    - Zoek in tenderned_raw hoeveel keer ze eerder hebben gewonnen
    - Tel het aantal eerdere aanbestedingen
    - Bereken totaal bedrag van eerdere aanbestedingen
    """
    
    print("Starting update process...")
    
    # 1) Haal ALLE data op uit tenderned_raw (de historische data)
    print("Fetching historical data from tenderned_raw...")
    resp_raw = (
        supabase.table("tenderned_raw")
        .select('"Officiële benaming", Publicatiedatum, bedrag')
        .not_.is_('"Officiële benaming"', 'null')
        .order("Publicatiedatum", desc=False)
        .execute()
    )
    
    if getattr(resp_raw, "error", None):
        print(f"Error fetching tenderned_raw: {resp_raw.error}")
        raise RuntimeError(resp_raw.error)
    
    raw_data = resp_raw.data or []
    print(f"Loaded {len(raw_data)} records from tenderned_raw")
    
    # 2) Organiseer de historische data per bedrijfsnaam
    # Format: { "bedrijfsnaam": [(datum, bedrag), (datum, bedrag), ...] }
    historical_wins = defaultdict(list)
    
    for row in raw_data:
        bedrijf = (row.get("Officiële benaming") or "").strip()
        if not bedrijf:
            continue
            
        datum_raw = row.get("Publicatiedatum")
        bedrag_raw = row.get("bedrag")
        
        # Parse datum
        datum = parse_date(datum_raw)
        # Parse bedrag
        bedrag = parse_amount(bedrag_raw)
        
        historical_wins[bedrijf].append({
            "datum": datum,
            "bedrag": bedrag or 0
        })
    
    print(f"Organized data for {len(historical_wins)} unique companies")
    
    # 3) Haal data op uit tenderned_raw_cached (de nieuwe data die we willen updaten)
    print("Fetching data from tenderned_raw_cached...")
    offset = 0
    total_updated = 0
    
    while True:
        resp_cached = (
            supabase.table("tenderned_raw_cpv_cached")
            .select('id, "Officiële benaming", Publicatiedatum')
            .not_.is_('"Officiële benaming"', 'null')
            .order("id")
            .range(offset, offset + batch_size - 1)
            .execute()
        )
        
        if getattr(resp_cached, "error", None):
            print(f"Error fetching tenderned_raw_cached: {resp_cached.error}")
            raise RuntimeError(resp_cached.error)
        
        cached_rows = resp_cached.data or []
        if not cached_rows:
            break
        
        print(f"Processing batch: records {offset + 1} to {offset + len(cached_rows)}")
        
        # 4) Bereken voor elke cached row het aantal eerdere aanbestedingen
        updates = []
        
        for row in cached_rows:
            row_id = row.get("id")
            bedrijf = (row.get("Officiële benaming") or "").strip()
            pub_datum_raw = row.get("Publicatiedatum")
            
            if not bedrijf or not row_id:
                continue
            
            pub_datum = parse_date(pub_datum_raw)
            
            # Tel eerdere aanbestedingen van dit bedrijf
            aantal_eerder = 0
            totaal_bedrag_eerder = 0
            
            if bedrijf in historical_wins:
                for win in historical_wins[bedrijf]:
                    # Check of deze win eerder was dan de huidige publicatie
                    if win["datum"] and pub_datum and win["datum"] < pub_datum:
                        aantal_eerder += 1
                        totaal_bedrag_eerder += win["bedrag"]
            
            updates.append({
                "id": row_id,
                "aantal_eerdere_aanbestedingen": aantal_eerder,
                "heeft_eerdere_aanbestedingen": aantal_eerder > 0
            })
        
        # 5) Bulk update naar database
        if updates:
            for update in updates:
                try:
                    supabase.table("tenderned_raw_cached").update({
                        "aantal_eerdere_aanbestedingen": update["aantal_eerdere_aanbestedingen"],
                        "heeft_eerdere_aanbestedingen": update["heeft_eerdere_aanbestedingen"]
                    }).eq("id", update["id"]).execute()
                except Exception as e:
                    print(f"Error updating id {update['id']}: {e}")
            
            total_updated += len(updates)
            print(f"Updated {len(updates)} records. Total so far: {total_updated}")
        
        offset += batch_size
        
        # Stop als we minder rows krijgen dan batch_size
        if len(cached_rows) < batch_size:
            break
    
    print(f"✅ Complete! Updated {total_updated} records in total")


def parse_date(raw):
    """Parse een datum string naar datetime object"""
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


if __name__ == "__main__":
    # Run de update functie
    update_eerdere_aanbestedingen(batch_size=500)