from collections import defaultdict
from datetime import datetime
from sqlalchemy.orm import Session
from sqlalchemy import and_
from database import get_db, engine
from models import TendernedRaw, TendernedRawCached, TendernedRawCPVCached
import os
import dotenv

dotenv.load_dotenv()


def update_eerdere_aanbestedingen(batch_size: int = 500, use_cpv_table: bool = False):
    """
    Update tenderned_raw_cached (of tenderned_raw_cpv_cached) met informatie 
    over eerdere aanbestedingen van dezelfde winnaar uit tenderned_raw.
    
    Voor elke winnaar in de cache table:
    - Zoek in tenderned_raw hoeveel keer ze eerder hebben gewonnen
    - Tel het aantal eerdere aanbestedingen
    - Bereken totaal bedrag van eerdere aanbestedingen
    
    Args:
        batch_size: Aantal records per batch
        use_cpv_table: True voor tenderned_raw_cpv_cached, False voor tenderned_raw_cached
    """
    
    print("Starting update process...")
    
    # Create database session
    db: Session = next(get_db())
    
    try:
        # 1) Haal ALLE data op uit tenderned_raw (de historische data)
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
        
        # 2) Organiseer de historische data per bedrijfsnaam
        # Format: { "bedrijfsnaam": [(datum, bedrag), (datum, bedrag), ...] }
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
        
        # 3) Bepaal welke cache table te gebruiken
        CacheModel = TendernedRawCPVCached if use_cpv_table else TendernedRawCached
        table_name = "tenderned_raw_cpv_cached"
        print(f"Using cache table: {table_name}")
        
        # 4) Haal data op uit cache table in batches
        print("Fetching data from cache table...")
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
            
            # 5) Bereken voor elke cached row het aantal eerdere aanbestedingen
            updates_performed = 0
            
            for row in cached_rows:
                row_id = row.id
                bedrijf = (row.Officiele_benaming or "").strip()
                pub_datum = parse_date(row.Publicatiedatum)
                
                if not bedrijf or not row_id:
                    continue
                
                # Tel eerdere aanbestedingen van dit bedrijf
                aantal_eerder = 0
                totaal_bedrag_eerder = 0
                
                if bedrijf in historical_wins:
                    for win in historical_wins[bedrijf]:
                        # Check of deze win eerder was dan de huidige publicatie
                        if win["datum"] and pub_datum and win["datum"] < pub_datum:
                            aantal_eerder += 1
                            totaal_bedrag_eerder += win["bedrag"]
                
                # 6) Update het record
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
                    print(f"Error updating id {row_id}: {e}")
                    db.rollback()
                    continue
            
            # Commit na elke batch
            db.commit()
            
            total_updated += updates_performed
            print(f"Updated {updates_performed} records. Total so far: {total_updated}")
            
            offset += batch_size
            
            # Stop als we minder rows krijgen dan batch_size
            if len(cached_rows) < batch_size:
                break
        
        print(f"✅ Complete! Updated {total_updated} records in total")
        
    except Exception as e:
        print(f"❌ Error during update process: {e}")
        db.rollback()
        raise
    finally:
        db.close()


def parse_date(raw):
    """Parse een datum string naar datetime object"""
    if not raw:
        return None
    
    # If it's already a datetime/date object
    if isinstance(raw, (datetime, )):
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


if __name__ == "__main__":
    # Update beide tables
    print("\n" + "="*50)
    print("Updating tenderned_raw_cached...")
    print("="*50 + "\n")
    update_eerdere_aanbestedingen(batch_size=500, use_cpv_table=False)
    
    print("\n" + "="*50)
    print("Updating tenderned_raw_cpv_cached...")
    print("="*50 + "\n")
    update_eerdere_aanbestedingen(batch_size=500, use_cpv_table=True)