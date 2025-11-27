import xml.etree.ElementTree as ET

# Test de TED parser met je XML bestand
XML_FILE = "xml_gegund/284771.xml"

# Helper functies
def find_element_ns_agnostic(parent, tag_name):
    """Vindt element met of zonder namespace."""
    if parent is None:
        return None
    
    # Probeer met TED namespace EERST
    elem = parent.find(f"{{http://publications.europa.eu/resource/schema/ted/R2.0.9/reception}}{tag_name}")
    if elem is not None:
        return elem
    
    # Probeer zonder namespace als fallback
    elem = parent.find(tag_name)
    return elem


def get_text_ns_agnostic(parent, tag_name):
    """Haalt text op van element, namespace-agnostisch."""
    elem = find_element_ns_agnostic(parent, tag_name)
    if elem is not None and elem.text:
        return elem.text.strip()
    return None


# Lees XML
with open(XML_FILE, "rb") as f:
    xml_bytes = f.read()

root = ET.fromstring(xml_bytes)
print(f"Root tag: {root.tag}")

# Vind F03_2014
print("\nTrying different search methods:")

# Method 1: Direct path
form_elem = root.find(".//{{http://publications.europa.eu/resource/schema/ted/R2.0.9/reception}}F03_2014")
print(f"Method 1 (.//) found: {form_elem is not None}")

# Method 2: Via FORM_SECTION
form_section = root.find("{{http://publications.europa.eu/resource/schema/ted/R2.0.9/reception}}FORM_SECTION")
print(f"FORM_SECTION found: {form_section is not None}")

if form_section is not None:
    form_elem = form_section.find("{{http://publications.europa.eu/resource/schema/ted/R2.0.9/reception}}F03_2014")
    print(f"F03_2014 in FORM_SECTION found: {form_elem is not None}")

# Method 3: Iterate and look for F03_2014
for elem in root.iter():
    tag = elem.tag.split('}')[-1] if '}' in elem.tag else elem.tag
    if tag == "F03_2014":
        form_elem = elem
        print(f"Method 3 (iterate) found: True")
        break

print(f"\nFinal: F03_2014 found: {form_elem is not None}")

if form_elem is not None:
    # Test OBJECT_CONTRACT
    obj_contract = find_element_ns_agnostic(form_elem, "OBJECT_CONTRACT")
    print(f"OBJECT_CONTRACT found: {obj_contract is not None}")
    
    if obj_contract is not None:
        # Test TITLE
        title_elem = find_element_ns_agnostic(obj_contract, "TITLE")
        print(f"TITLE found: {title_elem is not None}")
        
        if title_elem is not None:
            p_elem = find_element_ns_agnostic(title_elem, "P")
            print(f"TITLE/P found: {p_elem is not None}")
            if p_elem is not None and p_elem.text:
                print(f"Titel: {p_elem.text.strip()}")
    
    # Test CONTRACTING_BODY
    cb = find_element_ns_agnostic(form_elem, "CONTRACTING_BODY")
    print(f"\nCONTRACTING_BODY found: {cb is not None}")
    
    if cb is not None:
        addr = find_element_ns_agnostic(cb, "ADDRESS_CONTRACTING_BODY")
        print(f"ADDRESS_CONTRACTING_BODY found: {addr is not None}")
        
        if addr is not None:
            naam = get_text_ns_agnostic(addr, "OFFICIALNAME")
            print(f"Buyer naam: {naam}")
            plaats = get_text_ns_agnostic(addr, "TOWN")
            print(f"Buyer plaats: {plaats}")
    
    # Test AWARD_CONTRACT
    award = find_element_ns_agnostic(form_elem, "AWARD_CONTRACT")
    print(f"\nAWARD_CONTRACT found: {award is not None}")
    
    if award is not None:
        awarded = find_element_ns_agnostic(award, "AWARDED_CONTRACT")
        print(f"AWARDED_CONTRACT found: {awarded is not None}")
        
        if awarded is not None:
            contractors = find_element_ns_agnostic(awarded, "CONTRACTORS")
            print(f"CONTRACTORS found: {contractors is not None}")
            
            if contractors is not None:
                contractor = find_element_ns_agnostic(contractors, "CONTRACTOR")
                print(f"CONTRACTOR found: {contractor is not None}")
                
                if contractor is not None:
                    addr = find_element_ns_agnostic(contractor, "ADDRESS_CONTRACTOR")
                    print(f"ADDRESS_CONTRACTOR found: {addr is not None}")
                    
                    if addr is not None:
                        naam = get_text_ns_agnostic(addr, "OFFICIALNAME")
                        print(f"Winner naam: {naam}")
            
            # Test bedrag
            values = find_element_ns_agnostic(awarded, "VALUES")
            print(f"\nVALUES found: {values is not None}")
            
            if values is not None:
                val_total = find_element_ns_agnostic(values, "VAL_TOTAL")
                print(f"VAL_TOTAL found: {val_total is not None}")
                
                if val_total is not None:
                    print(f"Bedrag: {val_total.text} {val_total.get('CURRENCY')}")
            
            # Test datum
            datum = get_text_ns_agnostic(awarded, "DATE_CONCLUSION_CONTRACT")
            print(f"Datum gunning: {datum}")

print("\n✅ Test voltooid!")