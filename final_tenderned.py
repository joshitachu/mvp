import os
import csv
import requests
from requests.auth import HTTPBasicAuth
import xml.etree.ElementTree as ET

from dotenv import load_dotenv

# ---------- CONFIG ----------
load_dotenv()

TNS_BASE_URL = os.getenv("TNS_BASE_URL")
API_BASE_URL = os.getenv("API_BASE_URL")
API_USERNAME = os.getenv("API_USERNAME")
API_PASSWORD = os.getenv("API_PASSWORD")



DATE_FROM = "2025-02-03"
DATE_TO = "2025-02-05"
PUBLICATIE_TYPE = "AGO"
CPV_CODES = None
MAX_PAGES = None

SAVE_XML = True
XML_OUTPUT_DIR = "xml_gegund"


# ---------- NAMESPACES ----------

NS_EFORMS = {
    "cac": "urn:oasis:names:specification:ubl:schema:xsd:CommonAggregateComponents-2",
    "cbc": "urn:oasis:names:specification:ubl:schema:xsd:CommonBasicComponents-2",
    "efac": "http://data.europa.eu/p27/eforms-ubl-extension-aggregate-components/1",
    "efbc": "http://data.europa.eu/p27/eforms-ubl-extension-basic-components/1",
}


# ---------- HELPER FUNCTIONS ----------

def get_text(elem, path, namespaces=None):
    """Veilige helper: geeft .text of None terug."""
    if elem is None:
        return None
    found = elem.find(path, namespaces) if namespaces else elem.find(path)
    return found.text.strip() if found is not None and found.text else None


def find_element_ns_agnostic(parent, tag_name):
    """Vindt element met of zonder namespace."""
    if parent is None:
        return None
    
    # Probeer met TED namespace
    elem = parent.find(f"{{http://publications.europa.eu/resource/schema/ted/R2.0.9/reception}}{tag_name}")
    if elem is not None:
        return elem
    
    # Probeer zonder namespace
    return parent.find(tag_name)


def get_text_ns_agnostic(parent, tag_name):
    """Haalt text op van element, namespace-agnostisch."""
    elem = find_element_ns_agnostic(parent, tag_name)
    if elem is not None and elem.text:
        return elem.text.strip()
    return None


# ---------- XML FORMAT DETECTION ----------

def detect_xml_format(root):
    """Detecteert of het een oude TED XML is of een nieuwe eForms XML."""
    root_tag = root.tag.split('}')[-1] if '}' in root.tag else root.tag
    
    if root_tag == "TED_ESENDERS":
        return "TED"
    elif root_tag in ["ContractAwardNotice", "ContractNotice"]:
        return "EFORMS"
    
    # Fallback: kijk naar child elements
    for elem in root.iter():
        tag = elem.tag.split('}')[-1] if '}' in elem.tag else elem.tag
        if tag.startswith("F0") and "_2014" in tag:
            return "TED"
    
    return "EFORMS"


# ---------- TED FORMAT PARSERS ----------

def parse_ted_contractor(contractor_elem):
    """Parseert contractor info uit oude TED XML."""
    if contractor_elem is None:
        return {k: None for k in ["bedrijf_naam", "kvk", "straat", "postcode", "plaats", "land", "contact_naam", "contact_email", "contact_tel", "website"]}
    
    addr = find_element_ns_agnostic(contractor_elem, "ADDRESS_CONTRACTOR") or contractor_elem
    
    country_elem = find_element_ns_agnostic(addr, "COUNTRY")
    
    return {
        "bedrijf_naam": get_text_ns_agnostic(addr, "OFFICIALNAME"),
        "kvk": get_text_ns_agnostic(addr, "NATIONALID"),
        "straat": get_text_ns_agnostic(addr, "ADDRESS"),
        "postcode": get_text_ns_agnostic(addr, "POSTAL_CODE"),
        "plaats": get_text_ns_agnostic(addr, "TOWN"),
        "land": country_elem.get("VALUE") if country_elem is not None else None,
        "contact_naam": get_text_ns_agnostic(addr, "CONTACT_POINT"),
        "contact_email": get_text_ns_agnostic(addr, "E_MAIL"),
        "contact_tel": get_text_ns_agnostic(addr, "PHONE"),
        "website": get_text_ns_agnostic(addr, "URL") or get_text_ns_agnostic(addr, "URL_GENERAL"),
    }


def parse_ted_contracting_body(form_elem):
    """Parseert aanbestedende dienst uit oude TED XML."""
    cb = find_element_ns_agnostic(form_elem, "CONTRACTING_BODY")
    if cb is None:
        return {k: None for k in ["bedrijf_naam", "kvk", "straat", "postcode", "plaats", "land", "contact_naam", "contact_email", "contact_tel", "website"]}
    
    addr = find_element_ns_agnostic(cb, "ADDRESS_CONTRACTING_BODY") or cb
    country_elem = find_element_ns_agnostic(addr, "COUNTRY")
    
    return {
        "bedrijf_naam": get_text_ns_agnostic(addr, "OFFICIALNAME"),
        "kvk": get_text_ns_agnostic(addr, "NATIONALID"),
        "straat": get_text_ns_agnostic(addr, "ADDRESS"),
        "postcode": get_text_ns_agnostic(addr, "POSTAL_CODE"),
        "plaats": get_text_ns_agnostic(addr, "TOWN"),
        "land": country_elem.get("VALUE") if country_elem is not None else None,
        "contact_naam": get_text_ns_agnostic(addr, "CONTACT_POINT"),
        "contact_email": get_text_ns_agnostic(addr, "E_MAIL"),
        "contact_tel": get_text_ns_agnostic(addr, "PHONE"),
        "website": get_text_ns_agnostic(addr, "URL") or get_text_ns_agnostic(addr, "URL_GENERAL"),
    }


def parse_ted_xml(root):
    """Parseert oude TED XML format."""
    
    # Vind het form element
    form_elem = None
    possible_forms = ["F03_2014", "F02_2014", "F06_2014", "F15_2014", "F01_2014"]
    
    # Zoek zonder en met namespace
    for form_name in possible_forms:
        for elem in root.iter():
            tag = elem.tag.split('}')[-1] if '}' in elem.tag else elem.tag
            if tag == form_name:
                form_elem = elem
                break
        if form_elem is not None:
            break
    
    if form_elem is None:
        print(f"⚠️ Geen bekend TED form gevonden")
        return None
    
    # Basic info
    obj_contract = find_element_ns_agnostic(form_elem, "OBJECT_CONTRACT")
    
    titel = None
    if obj_contract is not None:
        title_elem = find_element_ns_agnostic(obj_contract, "TITLE")
        if title_elem is not None:
            p_elem = find_element_ns_agnostic(title_elem, "P")
            titel = p_elem.text.strip() if p_elem is not None and p_elem.text else None
    
    omschrijving = None
    if obj_contract is not None:
        descr_elem = find_element_ns_agnostic(obj_contract, "SHORT_DESCR")
        if descr_elem is not None:
            p_texts = []
            for elem in descr_elem:
                tag = elem.tag.split('}')[-1] if '}' in elem.tag else elem.tag
                if tag == "P" and elem.text:
                    p_texts.append(elem.text.strip())
            omschrijving = " ".join(p_texts) if p_texts else None
    
    ref_number = get_text_ns_agnostic(obj_contract, "REFERENCE_NUMBER") if obj_contract is not None else None
    
    # Aanbestedende dienst
    buyer_info = parse_ted_contracting_body(form_elem)
    
    # Award contract info
    award = find_element_ns_agnostic(form_elem, "AWARD_CONTRACT")
    
    winner_info = {k: None for k in ["bedrijf_naam", "kvk", "straat", "postcode", "plaats", "land", "contact_naam", "contact_email", "contact_tel", "website"]}
    
    if award is not None:
        awarded = find_element_ns_agnostic(award, "AWARDED_CONTRACT")
        if awarded is not None:
            contractors = find_element_ns_agnostic(awarded, "CONTRACTORS")
            if contractors is not None:
                contractor = find_element_ns_agnostic(contractors, "CONTRACTOR")
                if contractor is not None:
                    winner_info = parse_ted_contractor(contractor)
    
    # Bedrag
    bedrag = None
    valuta = None
    if award is not None:
        awarded = find_element_ns_agnostic(award, "AWARDED_CONTRACT")
        if awarded is not None:
            values = find_element_ns_agnostic(awarded, "VALUES")
            if values is not None:
                val_total = find_element_ns_agnostic(values, "VAL_TOTAL")
                if val_total is not None:
                    valuta = val_total.get("CURRENCY")
                    if val_total.text:
                        try:
                            bedrag = float(val_total.text.strip())
                        except ValueError:
                            pass
    
    # Datum gunning
    datum_gunning = None
    if award is not None:
        awarded = find_element_ns_agnostic(award, "AWARDED_CONTRACT")
        if awarded is not None:
            datum_gunning = get_text_ns_agnostic(awarded, "DATE_CONCLUSION_CONTRACT")
    
    # Dispatch date
    compl_info = find_element_ns_agnostic(form_elem, "COMPLEMENTARY_INFO")
    dispatch_date = get_text_ns_agnostic(compl_info, "DATE_DISPATCH_NOTICE") if compl_info is not None else None

    final_issue_date = dispatch_date or datum_gunning
    print(f"  📅 final_issue_date determined as: {final_issue_date}")

    return {
        "notice_id": ref_number,
        "titel": titel,
        "omschrijving": omschrijving,
        "win_bedrijf_naam": winner_info["bedrijf_naam"],
        "win_kvk": winner_info["kvk"],
        "win_straat": winner_info["straat"],
        "win_postcode": winner_info["postcode"],
        "win_plaats": winner_info["plaats"],
        "win_land": winner_info["land"],
        "win_contact_naam": winner_info["contact_naam"],
        "win_contact_email": winner_info["contact_email"],
        "win_contact_tel": winner_info["contact_tel"],
        "win_website": winner_info["website"],
        "buyer_bedrijf_naam": buyer_info["bedrijf_naam"],
        "buyer_kvk": buyer_info["kvk"],
        "buyer_straat": buyer_info["straat"],
        "buyer_postcode": buyer_info["postcode"],
        "buyer_plaats": buyer_info["plaats"],
        "buyer_land": buyer_info["land"],
        "buyer_contact_naam": buyer_info["contact_naam"],
        "buyer_contact_email": buyer_info["contact_email"],
        "buyer_contact_tel": buyer_info["contact_tel"],
        "buyer_website": buyer_info["website"],
        "bedrag": bedrag,
        "valuta": valuta,
        "datum_gunning": datum_gunning,
        "contract_issue_date": final_issue_date,  # ✅ Always has a value now
        "contract_startdatum": None,
        "contract_einddatum": None,
        "contract_duur_waarde": None,
        "contract_duur_eenheid": None,
    }

# ---------- EFORMS FORMAT PARSERS ----------

def build_org_index(root):
    """Maak een dict: org_id -> <efac:Organization>-element."""
    orgs = {}
    for org in root.findall(".//efac:Organizations/efac:Organization", NS_EFORMS):
        org_id_el = org.find(".//cac:PartyIdentification/cbc:ID", NS_EFORMS)
        if org_id_el is not None and org_id_el.text:
            orgs[org_id_el.text.strip()] = org
    return orgs


def extract_company_info(org):
    """Haalt basisgegevens uit een <efac:Organization>."""
    if org is None:
        return {k: None for k in ["bedrijf_naam", "kvk", "straat", "postcode", "plaats", "land", "contact_naam", "contact_email", "contact_tel", "website"]}

    company = org.find(".//efac:Company", NS_EFORMS) or org

    naam = get_text(company, ".//cac:PartyName/cbc:Name", NS_EFORMS)
    kvk = get_text(company, ".//cac:PartyLegalEntity/cbc:CompanyID", NS_EFORMS)

    addr = company.find(".//cac:PostalAddress", NS_EFORMS)
    straat = get_text(addr, "./cbc:StreetName", NS_EFORMS)
    postcode = get_text(addr, "./cbc:PostalZone", NS_EFORMS)
    plaats = get_text(addr, "./cbc:CityName", NS_EFORMS)
    land = get_text(addr, "./cac:Country/cbc:IdentificationCode", NS_EFORMS)

    contact = company.find(".//cac:Contact", NS_EFORMS)
    contact_naam = get_text(contact, "./cbc:Name", NS_EFORMS)
    contact_email = get_text(contact, "./cbc:ElectronicMail", NS_EFORMS)
    contact_tel = get_text(contact, "./cbc:Telephone", NS_EFORMS)

    website = get_text(company, "./cbc:WebsiteURI", NS_EFORMS)

    return {
        "bedrijf_naam": naam,
        "kvk": kvk,
        "straat": straat,
        "postcode": postcode,
        "plaats": plaats,
        "land": land,
        "contact_naam": contact_naam,
        "contact_email": contact_email,
        "contact_tel": contact_tel,
        "website": website,
    }


def extract_amount(root):
    """Haal bedrag + valuta op."""
    paths = [
        ".//efac:LotResult/efac:FrameworkAgreementValues/efbc:ReestimatedValueAmount",
        ".//efac:LotTender/cac:LegalMonetaryTotal/cbc:PayableAmount",
        ".//efac:NoticeResult/cbc:TotalAmount",
        ".//efac:NoticeResult/efbc:OverallApproximateFrameworkContractsAmount",
        ".//cac:ProcurementProject/cac:RequestedTenderTotal/cbc:EstimatedOverallContractAmount",
    ]
    
    for path in paths:
        el = root.find(path, NS_EFORMS)
        if el is not None and el.text:
            try:
                amount = float(el.text.strip().replace(",", "."))
                currency = el.attrib.get("currencyID")
                return amount, currency
            except ValueError:
                pass
    
    return None, None


def extract_contract_info(root):
    """Haalt basis contractinformatie op, inclusief IssueDate en datum gunning."""
    # ✅ CRITICAL: IssueDate is at ROOT level of the notice, NOT in SettledContract
    contract_issue_date = get_text(root, "./cbc:IssueDate", NS_EFORMS)
    
    # Haal datum gunning op uit meerdere mogelijke locaties
    datum_gunning = (
        get_text(root, ".//efac:SettledContract/cbc:AwardDate", NS_EFORMS) or
        get_text(root, ".//cac:TenderResult/cbc:AwardDate", NS_EFORMS)
    )

    planned_period = root.find(".//cac:ProcurementProjectLot/cac:ProcurementProject/cac:PlannedPeriod", NS_EFORMS)
    contract_startdatum = get_text(planned_period, "./cbc:StartDate", NS_EFORMS) if planned_period is not None else None
    contract_einddatum = get_text(planned_period, "./cbc:EndDate", NS_EFORMS) if planned_period is not None else None

    contract_duur_waarde = None
    contract_duur_eenheid = None
    if planned_period is not None:
        dur_el = planned_period.find("./cbc:DurationMeasure", NS_EFORMS)
        if dur_el is not None and dur_el.text:
            contract_duur_waarde = dur_el.text.strip()
            contract_duur_eenheid = dur_el.attrib.get("unitCode")

    # ✅ Ensure we ALWAYS have a publication date - fallback chain
    final_issue_date = contract_issue_date
    if not final_issue_date:
        print(f"⚠️ WARNING: No root IssueDate found, falling back to AwardDate")
        final_issue_date = datum_gunning

    print(f"  📅 final_issue_date determined as: {final_issue_date}")

    return {
        "datum_gunning": datum_gunning,
        "contract_issue_date": final_issue_date,
        "contract_startdatum": contract_startdatum,
        "contract_einddatum": contract_einddatum,
        "contract_duur_waarde": contract_duur_waarde,
        "contract_duur_eenheid": contract_duur_eenheid,
    }


def parse_eforms_xml(root):
    """Parseert eForms XML."""
    notice_id = get_text(root, "./cbc:ID", NS_EFORMS)
    titel = get_text(root, ".//cac:ProcurementProject/cbc:Name", NS_EFORMS)
    omschrijving = get_text(root, ".//cac:ProcurementProject/cbc:Description", NS_EFORMS)

    org_index = build_org_index(root)

    buyer_id = get_text(root, ".//cac:ContractingParty/cac:Party/cac:PartyIdentification/cbc:ID", NS_EFORMS)
    buyer_info = extract_company_info(org_index.get(buyer_id))

    winner_org_id = get_text(root, ".//efac:NoticeResult/efac:TenderingParty/efac:Tenderer/cbc:ID", NS_EFORMS)
    winner_info = extract_company_info(org_index.get(winner_org_id))

    bedrag, valuta = extract_amount(root)
    contract_info = extract_contract_info(root)

    return {
        "notice_id": notice_id,
        "titel": titel,
        "omschrijving": omschrijving,
        "win_bedrijf_naam": winner_info["bedrijf_naam"],
        "win_kvk": winner_info["kvk"],
        "win_straat": winner_info["straat"],
        "win_postcode": winner_info["postcode"],
        "win_plaats": winner_info["plaats"],
        "win_land": winner_info["land"],
        "win_contact_naam": winner_info["contact_naam"],
        "win_contact_email": winner_info["contact_email"],
        "win_contact_tel": winner_info["contact_tel"],
        "win_website": winner_info["website"],
        "buyer_bedrijf_naam": buyer_info["bedrijf_naam"],
        "buyer_kvk": buyer_info["kvk"],
        "buyer_straat": buyer_info["straat"],
        "buyer_postcode": buyer_info["postcode"],
        "buyer_plaats": buyer_info["plaats"],
        "buyer_land": buyer_info["land"],
        "buyer_contact_naam": buyer_info["contact_naam"],
        "buyer_contact_email": buyer_info["contact_email"],
        "buyer_contact_tel": buyer_info["contact_tel"],
        "buyer_website": buyer_info["website"],
        "bedrag": bedrag,
        "valuta": valuta,
        "datum_gunning": contract_info["datum_gunning"],
        "contract_issue_date": contract_info["contract_issue_date"],
        "contract_startdatum": contract_info["contract_startdatum"],
        "contract_einddatum": contract_info["contract_einddatum"],
        "contract_duur_waarde": contract_info["contract_duur_waarde"],
        "contract_duur_eenheid": contract_info["contract_duur_eenheid"],
    }




# ---------- UNIFIED PARSER ----------

def parse_publicatie_xml(xml_bytes):
    """Parseert XML en detecteert automatisch het formaat."""
    root = ET.fromstring(xml_bytes)
    xml_format = detect_xml_format(root)
    print(f"  📄 Detected format: {xml_format}")
    
    if xml_format == "TED":
        return parse_ted_xml(root)
    else:
        return parse_eforms_xml(root)


# ---------- API FUNCTIONS ----------

def iter_publicaties(publicatie_type=PUBLICATIE_TYPE, date_from=DATE_FROM, date_to=DATE_TO, cpv_codes=CPV_CODES, page_size=100, max_pages=MAX_PAGES):
    """Haalt publicaties op via de publieke JSON-webservice."""
    page = 0

    while True:
        params = {"page": page, "size": page_size}

        if publicatie_type:
            params["publicatieType"] = publicatie_type
        if date_from:
            params["publicatieDatumVanaf"] = date_from
        if date_to:
            params["publicatieDatumTot"] = date_to
        if date_from or date_to:
            params["publicatieDatumPreset"] = "AGP"
        if cpv_codes:
            params["cpvCodes"] = cpv_codes

        resp = requests.get(TNS_BASE_URL, params=params, timeout=30)
        resp.raise_for_status()
        data = resp.json()

        contents = data.get("contents") or data.get("content", [])
        if not contents:
            break

        for item in contents:
            publicatie_id = item.get("publicatieId") or item.get("id") or item.get("publicationId")
            if publicatie_id:
                yield int(publicatie_id), item

        if data.get("last"):
            break

        page += 1
        if max_pages is not None and page >= max_pages:
            break


def download_xml_bytes(publicatie_id: int):
    """Download XML uit de beveiligde TenderNed XML API."""
    url = f"{API_BASE_URL}/publicaties/{publicatie_id}/public-xml"
    resp = requests.get(url, auth=HTTPBasicAuth(API_USERNAME, API_PASSWORD), timeout=30)
    if resp.status_code == 200:
        return resp.content
    print(f"Fout {resp.status_code} bij {publicatie_id}")
    return None


# ---------- MAIN ----------
def run_import(
    date_from: str,
    date_to: str,
    publicatie_type: str = "AGO",
    cpv_codes=None,
    max_pages=None,
    save_xml: bool = False,
    xml_output_dir: str = "xml_gegund",
):
    """
    Draait de volledige import en geeft een lijst dicts (records) terug.
    Schrijft NIET naar CSV.
    """
    print("🚀 Start TenderNed scraper run_import")

    records = []
    row_id = 1

    if save_xml:
        os.makedirs(xml_output_dir, exist_ok=True)

    for publicatie_id, meta in iter_publicaties(
        publicatie_type=publicatie_type,
        date_from=date_from,
        date_to=date_to,
        cpv_codes=cpv_codes,
        max_pages=max_pages,
    ):
        print(f"Verwerk publicatie {publicatie_id}...")

        xml_bytes = download_xml_bytes(publicatie_id)
        if not xml_bytes:
            continue

        if save_xml:
            xml_path = os.path.join(xml_output_dir, f"{publicatie_id}.xml")
            with open(xml_path, "wb") as f:
                f.write(xml_bytes)

        try:
            rec = parse_publicatie_xml(xml_bytes)
            if rec is None:
                print(f"⚠️ Kon publicatie {publicatie_id} niet parsen")
                continue
        except Exception as e:
            print(f"⚠️ Fout bij parsen XML {publicatie_id}: {e}")
            continue

        # ✅ Gebruik dispatch date / contract_issue_date als publicatie_datum
        # TED: DATE_DISPATCH_NOTICE → contract_issue_date
        # eForms: IssueDate → contract_issue_date
        pub_raw = rec.get("contract_issue_date") or rec.get("datum_gunning")

        pub_iso = None
        if isinstance(pub_raw, str):
            # als er 'YYYY-MM-DDThh:mm:ss' in zit → alleen datumdeel pakken
            pub_iso = pub_raw.split("T")[0]
        else:
            pub_iso = pub_raw

        rec["publicatie_datum"] = pub_iso
        rec["Publicatiedatum"] = pub_iso  # voor je "Publicatiedatum" kolom in tenderned_raw

        # Eventueel debug
        print(f"[DEBUG] publicatie_id={publicatie_id}, dispatch/publicatie_datum={pub_iso!r}")

        # Bestaande velden
        rec["id"] = row_id
        rec["publicatieId"] = publicatie_id
        rec["URL"] = meta.get("link")

        row_id += 1
        records.append(rec)

    print(f"\n✅ Klaar. Totaal records: {len(records)}")
    return records



def main():
    print("🚀 Start TenderNed scraper")

    if SAVE_XML:
        os.makedirs(XML_OUTPUT_DIR, exist_ok=True)

    records = []
    row_id = 1

    for publicatie_id, meta in iter_publicaties():
        print(f"Verwerk publicatie {publicatie_id}...")

        xml_bytes = download_xml_bytes(publicatie_id)
        if not xml_bytes:
            continue

        if SAVE_XML:
            xml_path = os.path.join(XML_OUTPUT_DIR, f"{publicatie_id}.xml")
            with open(xml_path, "wb") as f:
                f.write(xml_bytes)

        try:
            rec = parse_publicatie_xml(xml_bytes)
            if rec is None:
                print(f"⚠️ Kon publicatie {publicatie_id} niet parsen")
                continue
        except Exception as e:
            print(f"⚠️ Fout bij parsen XML {publicatie_id}: {e}")
            continue

        rec["id"] = row_id
        rec["publicatieId"] = publicatie_id
        rec["URL"] = meta.get("link")

        row_id += 1
        records.append(rec)
        

    print(f"\nKlaar. Totaal records: {len(records)}")

    if records:
        csv_path = "output.csv"
        fieldnames = [
            "id", "publicatieId", "URL", "notice_id", "titel", "omschrijving",
            "win_bedrijf_naam", "win_kvk", "win_straat", "win_postcode", "win_plaats", "win_land",
            "win_contact_naam", "win_contact_email", "win_contact_tel", "win_website",
            "buyer_bedrijf_naam", "buyer_kvk", "buyer_straat", "buyer_postcode", "buyer_plaats", "buyer_land",
            "buyer_contact_naam", "buyer_contact_email", "buyer_contact_tel", "buyer_website",
            "bedrag", "valuta", "datum_gunning", "contract_issue_date", "contract_startdatum",
            "contract_einddatum", "contract_duur_waarde", "contract_duur_eenheid",
        ]

        with open(csv_path, "w", newline="", encoding="utf-8") as f:
            writer = csv.DictWriter(f, fieldnames=fieldnames)
            writer.writeheader()
            writer.writerows(records)

        print(f"CSV opgeslagen als: {csv_path}")


if __name__ == "__main__":
    main()