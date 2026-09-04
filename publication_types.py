"""TenderNed publication type reference data.

Everything here was verified against the live API on 2026-09-04, not taken from
documentation. TenderNed exposes TWO independent classifications per publication
and they do not mean the same thing:

  typePublicatie.code   TenderNed's own coarse bucket -- this is where "AGO" lives
  publicatiecode.code   the actual form: EF01..EF40 / EFE1..EFE4 (eForms era),
                        or SF01..SF25 (legacy standard forms, pre Oct-2023)

The app previously filtered on typePublicatie == "AGO" and treated the result as
"awards". Measured over 300 live AGO records that is wrong in both directions:

  EF29  231 (77.0%)  award notice          <- wanted
  EF25   18 ( 6.0%)  VEAT, intent to award <- NOT an award
  EF30   15 ( 5.0%)  award notice          <- wanted
  EF33   14 ( 4.7%)  award, light regime   <- wanted
  EFE4   11 ( 3.7%)  voluntary award       <- wanted
  EF31    8 ( 2.7%)  award notice          <- wanted
  EF32/26/28  3      mixed
  --> 6.7% of "awards" are VEAT: announcements of an INTENTION to award
      directly, with no winner yet.

And cancellations (vroegtijdige beëindiging) are excluded entirely, because they
live under typePublicatie VBE -- while carrying award form codes.
"""

# Authoritative enum, obtained by sending an invalid value and reading the API's
# own validation message:
#   GET /v2/publicaties?publicatieType=ZZZ
#   -> "One of the following is required: [VAK, AAO, AGO, REC, MAC, VBE, AAW]"
TYPE_PUBLICATIE = {
    "VAK": "Vooraankondiging",
    "AAO": "Aankondiging opdracht",
    "AGO": "Aankondiging gegunde opdracht",
    "REC": "Rectificatie",
    "MAC": "Marktconsultatie",
    "VBE": "Vroegtijdige beëindiging",
    "AAW": "Aankondiging van een wijziging",
}

# WARNING: publicatieType=VBE is BROKEN server-side. Verified 2026-09-04:
#   AGO -> 62,878   AAO -> 48,572   MAC -> 5,999   VBE -> 145,300 (= whole corpus)
# It returns everything, unfiltered. Detect early termination via the
# isVroegtijdigeBeeindiging / isVroegtijdigBeeindigd booleans on each record.
BROKEN_TYPE_FILTERS = {"VBE"}


# ---- publicatiecode families (the reliable classification) ----

# Genuine award notices ("this contract was awarded to X").
AWARD_CODES = frozenset({
    "EF29", "EF30", "EF31", "EF32",   # standard regime, dir. 24/25/81/23
    "EF33", "EF34", "EF35",           # light regime (social & other specific services)
    "EF36", "EF37",                   # design contest results
    "EFE4",                           # national voluntary award notice
    # legacy standard forms
    "SF03", "SF06", "SF18", "SF21", "SF25",
})

# Vrijwillige transparantie vooraf. An announcement of INTENT to award without
# competition, published to start a 20-day standstill (art. 2.127 / 4.16 Aw).
# There is no winner yet. Valuable as its own signal -- "contract about to be
# handed out without competition" -- but it is NOT an award.
VEAT_CODES = frozenset({"EF25", "EF26", "EF27", "EF28", "SF15"})

# Open tenders you can still bid on. This is the bid-intelligence feed.
CONTRACT_NOTICE_CODES = frozenset({
    "EF16", "EF17", "EF18", "EF19",   # standard regime + concessions
    "EF20", "EF21",                   # light regime
    "EF23", "EF24",                   # design contests
    "EFE3",                           # national below-threshold contract notice
    "SF02", "SF05", "SF17", "SF20",
})

# Early-warning: buyer signalling a future procurement.
PRIOR_INFORMATION_CODES = frozenset({
    "EF04", "EF05", "EF06", "EF07", "EF08", "EF09",
    "EF10", "EF11", "EF12", "EF13", "EF14",
    "EFE1",                           # voluntary market consultation
    "EFE2",                           # voluntary prior information
    "SF01", "SF04",
})

MODIFICATION_CODES = frozenset({"EF38", "EF39", "EF40", "SF20"})

# Convenience groupings for the import API.
CODE_FAMILIES = {
    "awards": AWARD_CODES,
    "veat": VEAT_CODES,
    "open_tenders": CONTRACT_NOTICE_CODES,
    "prior_information": PRIOR_INFORMATION_CODES,
    "modifications": MODIFICATION_CODES,
}


def classify(record: dict) -> str:
    """Classify a TenderNed list record by its publicatiecode.

    Returns one of: awards | veat | open_tenders | prior_information |
    modifications | cancelled | unknown

    Prefer this over typePublicatie. Cancellations are detected via the boolean
    flags, because the VBE type filter is broken server-side.
    """
    if record.get("isVroegtijdigeBeeindiging") or record.get("isVroegtijdigBeeindigd"):
        return "cancelled"

    code = record.get("publicatiecode")
    if isinstance(code, dict):
        code = code.get("code")
    if not code:
        return "unknown"

    for family, codes in CODE_FAMILIES.items():
        if code in codes:
            return family
    return "unknown"


def is_real_award(record: dict) -> bool:
    """True only for genuine award notices -- excludes VEAT and cancellations."""
    return classify(record) == "awards"
