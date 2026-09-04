"""
SQLAlchemy ORM Models for TenderNed Database
Generated from PostgreSQL table schemas
"""
from sqlalchemy import (
    Column, String, Integer, BigInteger, Boolean, Date, DateTime, 
    Text, CHAR, Numeric, ForeignKey, UniqueConstraint, Index
)
from sqlalchemy.dialects.postgresql import UUID, JSONB
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func
from database import Base
import uuid


class AuthCode(Base):
    __tablename__ = "auth_codes"
    
    code = Column(CHAR(12), primary_key=True)
    created_at = Column(DateTime, default=func.now())
    used = Column(Boolean, default=False)


class Import(Base):
    __tablename__ = "imports"
    
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    name = Column(Text, unique=True, nullable=False)
    date_from = Column(Date)
    date_to = Column(Date)
    publicatie_type = Column(Text)
    cpv_codes = Column(Text)
    total_records = Column(Integer, default=0)
    created_at = Column(DateTime(timezone=True), default=func.now())
    region = Column(Text)
    province = Column(Text)
    owner_code = Column(Text)

    # Lifecycle: pending -> running -> completed | partial | failed
    # See migrations/003_import_status.sql.
    status = Column(Text, nullable=False, default="pending")
    error_message = Column(Text)
    started_at = Column(DateTime(timezone=True))
    finished_at = Column(DateTime(timezone=True))
    # Per-run fetch counters; partial means listed > fetched.
    listed = Column(Integer, nullable=False, default=0)
    fetched = Column(Integer, nullable=False, default=0)
    http_failed = Column(Integer, nullable=False, default=0)
    parse_failed = Column(Integer, nullable=False, default=0)

    # Relationships
    notices = relationship("Notice", back_populates="import_record", cascade="all, delete-orphan")
    sroi_results = relationship("SROIResult", back_populates="import_record", cascade="all, delete-orphan")


class Notice(Base):
    __tablename__ = "notices"
    
    id = Column(BigInteger, primary_key=True, autoincrement=True)
    import_id = Column(UUID(as_uuid=True), ForeignKey("imports.id", ondelete="CASCADE"), nullable=False)
    # NOT globally unique: the same TenderNed notice may appear in many imports.
    # Uniqueness is (import_id, notice_id) -- see __table_args__ and
    # migrations/001_fix_notice_uniqueness.sql.
    notice_id = Column(Text)
    publicatie_id = Column(BigInteger)
    url = Column(Text)
    titel = Column(Text)
    omschrijving = Column(Text)
    
    # Winner fields
    win_bedrijf_naam = Column(Text)
    win_kvk = Column(Text)
    win_straat = Column(Text)
    win_postcode = Column(Text)
    win_plaats = Column(Text)
    win_land = Column(Text)
    win_contact_naam = Column(Text)
    win_contact_email = Column(Text)
    win_contact_tel = Column(Text)
    win_website = Column(Text)
    
    # Buyer fields
    buyer_bedrijf_naam = Column(Text)
    buyer_kvk = Column(Text)
    buyer_straat = Column(Text)
    buyer_postcode = Column(Text)
    buyer_plaats = Column(Text)
    buyer_land = Column(Text)
    buyer_contact_naam = Column(Text)
    buyer_contact_email = Column(Text)
    buyer_contact_tel = Column(Text)
    buyer_website = Column(Text)
    
    # Additional fields
    bedrag = Column(Numeric)
    valuta = Column(Text)
    created_at = Column(DateTime(timezone=True), default=func.now())
    region = Column(Text)
    province = Column(Text)
    heeft_eerdere_aanbestedingen = Column(Boolean, default=False)
    aantal_eerdere_aanbestedingen = Column(Integer, default=0)
    owner_code = Column(Text)
    publicatie_datum = Column(DateTime(timezone=True))

    # Classification -- see publication_types.py and migration 004.
    # record_type is what you should filter on; 'awards' excludes VEAT
    # (intent-to-award, no winner) and cancelled procedures.
    publicatie_code = Column(Text)
    record_type = Column(Text)
    type_publicatie = Column(Text)
    is_cancelled = Column(Boolean, nullable=False, default=False)

    __table_args__ = (
        UniqueConstraint('import_id', 'notice_id', name='notices_import_id_notice_id_key'),
        # Every hot read filters on (import_id, owner_code); without this it is a seq scan.
        Index('idx_notices_import_owner', 'import_id', 'owner_code'),
        # server.py filters with func.lower(province) == region; needs the expression index.
        Index('idx_notices_province_lower', func.lower(province)),
    )

    # Relationships
    import_record = relationship("Import", back_populates="notices")


class SROIResult(Base):
    __tablename__ = "sroi_results"
    
    id = Column(BigInteger, primary_key=True, autoincrement=True)
    import_id = Column(UUID(as_uuid=True), ForeignKey("imports.id", ondelete="CASCADE"), nullable=False)
    notice_id = Column(Text)
    publicatie_id = Column(Text)
    winner_name = Column(Text)
    analyzed_url = Column(Text)
    url_source = Column(Text)
    sroi_compliant = Column(Boolean, default=False)
    confidence = Column(Text)
    score = Column(Integer, default=0)
    evidence = Column(JSONB)
    summary = Column(Text)
    pages_checked = Column(Integer, default=0)
    error = Column(Text)
    analysis_method = Column(Text)
    verdict = Column(Text)
    created_at = Column(DateTime(timezone=True), default=func.now())
    owner_code = Column(Text)
    
    # Relationships
    import_record = relationship("Import", back_populates="sroi_results")
    
    __table_args__ = (
        Index('idx_sroi_import_id', 'import_id'),
        Index('idx_sroi_compliant', 'sroi_compliant'),
        UniqueConstraint('import_id', 'notice_id', name='idx_sroi_unique_notice'),
    )


class NoticeSROIResult(Base):
    __tablename__ = "notice_sroi_results"
    
    id = Column(BigInteger, primary_key=True, autoincrement=True)
    notice_id = Column(Text, nullable=False)
    target = Column(Text, nullable=False)  # 'winner' or 'buyer'
    company_name = Column(Text)
    analyzed_url = Column(Text)
    url_source = Column(Text)
    sroi_compliant = Column(Boolean, default=False)
    confidence = Column(Text)
    score = Column(Integer, default=0)
    evidence = Column(JSONB)
    summary = Column(Text)
    pages_checked = Column(Integer, default=0)
    error = Column(Text)
    analysis_method = Column(Text)
    verdict = Column(Text)
    created_at = Column(DateTime(timezone=True), default=func.now())
    owner_code = Column(Text)
    
    __table_args__ = (
        Index('idx_notice_sroi_notice_id', 'notice_id'),
        Index('idx_notice_sroi_compliant', 'sroi_compliant'),
        Index('idx_notice_sroi_owner', 'owner_code'),
        UniqueConstraint('notice_id', 'target', name='idx_notice_sroi_unique'),
    )


class CRMCompany(Base):
    __tablename__ = "crm_companies"
    
    id = Column(BigInteger, primary_key=True, autoincrement=True)
    name = Column(Text, nullable=False)
    website = Column(Text)
    kvk = Column(Text)
    contact_name = Column(Text)
    contact_email = Column(Text)
    contact_phone = Column(Text)
    source_notice_id = Column(Text)
    lead_status = Column(Text, default='new')
    last_contacted = Column(DateTime(timezone=True))
    notes = Column(Text)
    extra = Column(JSONB)
    created_at = Column(DateTime(timezone=True), default=func.now())
    updated_at = Column(DateTime(timezone=True), default=func.now(), onupdate=func.now())
    address = Column(Text)
    city = Column(Text)
    country = Column(Text)
    postal_code = Column(Text)
    owner_code = Column(Text)
    
    # Relationships
    followups = relationship("CRMFollowup", back_populates="company", cascade="all, delete-orphan")
    
    __table_args__ = (
        Index('idx_crm_companies_name', func.lower(name)),
    )


class CRMFollowup(Base):
    __tablename__ = "crm_followups"
    
    id = Column(BigInteger, primary_key=True, autoincrement=True)
    company_id = Column(BigInteger, ForeignKey("crm_companies.id", ondelete="CASCADE"))
    scheduled_at = Column(DateTime(timezone=True))
    completed = Column(Boolean, default=False)
    emailed = Column(Boolean, default=False)
    action = Column(Text)
    note = Column(Text)
    created_by = Column(Text)
    created_at = Column(DateTime(timezone=True), default=func.now())
    updated_at = Column(DateTime(timezone=True), default=func.now(), onupdate=func.now())
    
    # Relationships
    company = relationship("CRMCompany", back_populates="followups")
    
    __table_args__ = (
        Index('idx_crm_followups_company', 'company_id'),
    )


# Canonical TenderNed layer -------------------------------------------------
# These tables supersede the legacy tenderned_raw*_cached tables. Source data is
# global/public and immutable; the existing `notices` table remains the
# owner-scoped import projection used by the UI.
class TenderNotice(Base):
    __tablename__ = "tender_notices"

    id = Column(BigInteger, primary_key=True, autoincrement=True)
    notice_id = Column(Text, unique=True, nullable=False)
    publicatie_id = Column(BigInteger, unique=True)
    publicatie_datum = Column(Date)
    publicatie_code = Column(Text)
    type_publicatie = Column(Text)
    record_type = Column(Text)
    is_cancelled = Column(Boolean, nullable=False, default=False)
    title = Column(Text)
    description = Column(Text)
    source_url = Column(Text)
    winner_company_id = Column(BigInteger, ForeignKey("tender_companies.id", ondelete="SET NULL"))
    buyer_company_id = Column(BigInteger, ForeignKey("tender_companies.id", ondelete="SET NULL"))
    # Preserve the API listing object and source XML. Derived records can be
    # rebuilt locally without re-downloading TenderNed.
    listing_payload = Column(JSONB, nullable=False, default=dict)
    source_xml = Column(Text, nullable=False)
    parsed_payload = Column(JSONB, nullable=False, default=dict)
    fetched_at = Column(DateTime(timezone=True), nullable=False, default=func.now())
    updated_at = Column(DateTime(timezone=True), nullable=False, default=func.now(), onupdate=func.now())

    cpvs = relationship("TenderNoticeCPV", back_populates="notice", cascade="all, delete-orphan")
    lots = relationship("TenderNoticeLot", back_populates="notice", cascade="all, delete-orphan")
    winner_company = relationship("TenderCompany", foreign_keys=[winner_company_id])
    buyer_company = relationship("TenderCompany", foreign_keys=[buyer_company_id])

    __table_args__ = (
        Index("idx_tender_notices_date", "publicatie_datum"),
        Index("idx_tender_notices_type_date", "record_type", "publicatie_datum"),
    )


class TenderCompany(Base):
    __tablename__ = "tender_companies"

    id = Column(BigInteger, primary_key=True, autoincrement=True)
    # KVK is the stable identifier where available. canonical_key falls back to
    # a normalized name/location key for notices that do not contain a KVK.
    kvk = Column(Text, unique=True)
    canonical_key = Column(Text, unique=True, nullable=False)
    name = Column(Text, nullable=False)
    street = Column(Text)
    postcode = Column(Text)
    city = Column(Text)
    province = Column(Text)
    country = Column(Text)
    website = Column(Text)
    first_seen_at = Column(DateTime(timezone=True), nullable=False, default=func.now())
    last_seen_at = Column(DateTime(timezone=True), nullable=False, default=func.now())

    __table_args__ = (
        Index("idx_tender_companies_name", "name"),
        Index("idx_tender_companies_province", "province"),
    )


class TenderNoticeCPV(Base):
    __tablename__ = "tender_notice_cpvs"

    id = Column(BigInteger, primary_key=True, autoincrement=True)
    notice_id = Column(BigInteger, ForeignKey("tender_notices.id", ondelete="CASCADE"), nullable=False)
    code = Column(Text, nullable=False)
    label = Column(Text)
    is_main = Column(Boolean, nullable=False, default=False)

    notice = relationship("TenderNotice", back_populates="cpvs")

    __table_args__ = (
        UniqueConstraint("notice_id", "code", name="tender_notice_cpvs_notice_code_key"),
        Index("idx_tender_notice_cpvs_code", "code"),
    )


class TenderNoticeLot(Base):
    __tablename__ = "tender_notice_lots"

    id = Column(BigInteger, primary_key=True, autoincrement=True)
    notice_id = Column(BigInteger, ForeignKey("tender_notices.id", ondelete="CASCADE"), nullable=False)
    external_lot_id = Column(Text, nullable=False)
    title = Column(Text)
    description = Column(Text)
    awarded_company_id = Column(BigInteger, ForeignKey("tender_companies.id", ondelete="SET NULL"))
    award_value = Column(Numeric)
    currency = Column(Text)
    award_date = Column(Date)
    contract_start = Column(Date)
    contract_end = Column(Date)

    notice = relationship("TenderNotice", back_populates="lots")
    awarded_company = relationship("TenderCompany")

    __table_args__ = (
        UniqueConstraint("notice_id", "external_lot_id", name="tender_notice_lots_notice_external_key"),
        Index("idx_tender_notice_lots_company", "awarded_company_id"),
    )


class SavedSearch(Base):
    __tablename__ = "saved_searches"
    id = Column(BigInteger, primary_key=True, autoincrement=True)
    owner_code = Column(Text, nullable=False)
    name = Column(Text, nullable=False)
    filters = Column(JSONB, nullable=False, default=dict)
    is_alert_enabled = Column(Boolean, nullable=False, default=True)
    last_checked_at = Column(DateTime(timezone=True))
    created_at = Column(DateTime(timezone=True), nullable=False, default=func.now())
    updated_at = Column(DateTime(timezone=True), nullable=False, default=func.now(), onupdate=func.now())

    __table_args__ = (UniqueConstraint("owner_code", "name", name="saved_searches_owner_name_key"),)


class SavedSearchAlert(Base):
    __tablename__ = "saved_search_alerts"
    id = Column(BigInteger, primary_key=True, autoincrement=True)
    saved_search_id = Column(BigInteger, ForeignKey("saved_searches.id", ondelete="CASCADE"), nullable=False)
    tender_notice_id = Column(BigInteger, ForeignKey("tender_notices.id", ondelete="CASCADE"), nullable=False)
    created_at = Column(DateTime(timezone=True), nullable=False, default=func.now())
    read_at = Column(DateTime(timezone=True))

    __table_args__ = (UniqueConstraint("saved_search_id", "tender_notice_id", name="saved_search_alerts_search_notice_key"),)


class TendernedRaw(Base):
    __tablename__ = "tenderned_raw"
    
    id = Column(BigInteger, primary_key=True, autoincrement=True)
    
    # Original columns with Dutch names (keep as-is for compatibility)
    Id_publicatie = Column("Id publicatie", Text)
    
    Tenderned_kenmerk = Column("Tenderned kenmerk", Text)
    Publicatiedatum = Column("Publicatiedatum", Date)
    Naam_Aanbestedende_dienst = Column("Naam Aanbestedende dienst", Text)
    Officiele_naam_Aanbestedende_dienst = Column("Officiële naam Aanbestedende dienst", Text)
    Nationaal_identificatienummer = Column("Nationaal identificatienummer", Text)
    Naam_aanbesteding = Column("Naam aanbesteding", Text)
    URL_TenderNed = Column("URL TenderNed", Text)
    Omschrijving_aanbesteding = Column("Omschrijving aanbesteding", Text)
    Aanvang_opdracht = Column("Aanvang opdracht", Date)
    Voltooiing_opdracht = Column("Voltooiing opdracht", Date)
    Datum_gunning = Column("Datum gunning", Date)
    Datum_besluit_gunning = Column("Datum besluit gunning", Date)
    Officiele_benaming = Column("Officiële benaming", Text)
    Kvknummer = Column("Kvknummer", Text)
    Postadres = Column("Postadres", Text)
    Plaats = Column("Plaats", Text)
    Postcode = Column("Postcode", Text)
    Land = Column("Land", Text)
    Internetadres = Column("Internetadres", Text)
    bedrag = Column("bedrag", Numeric)
    Waarde_valuta = Column("Waarde - valuta", Text)
    Termijn_voltooiing_opdracht = Column("Termijn voltooiing opdracht", Text)
    Tijdseenheid_periode_voltooiing_opdracht = Column("Tijdseenheid periode voltooiing opdracht", Text)
    
    # Normalized columns
    notice_id = Column(Text, unique=True)
    publicatie_id = Column(BigInteger)
    url = Column(Text)
    titel = Column(Text)
    omschrijving = Column(Text)
    
    # Winner fields
    win_bedrijf_naam = Column(Text)
    win_kvk = Column(Text)
    win_straat = Column(Text)
    win_postcode = Column(Text)
    win_plaats = Column(Text)
    win_land = Column(Text)
    win_contact_naam = Column(Text)
    win_contact_email = Column(Text)
    win_contact_tel = Column(Text)
    win_website = Column(Text)
    
    # Buyer fields
    buyer_bedrijf_naam = Column(Text)
    buyer_kvk = Column(Text)
    buyer_straat = Column(Text)
    buyer_postcode = Column(Text)
    buyer_plaats = Column(Text)
    buyer_land = Column(Text)
    buyer_contact_naam = Column(Text)
    buyer_contact_email = Column(Text)
    buyer_contact_tel = Column(Text)
    buyer_website = Column(Text)
    
    valuta = Column(Text)
    region = Column(Text)
    province = Column(Text)
    heeft_eerdere_aanbestedingen = Column(Boolean)
    aantal_eerdere_aanbestedingen = Column(Integer)
    owner_code = Column(Text)
    publicatie_datum = Column(DateTime(timezone=True))
    
    __table_args__ = (
        Index('idx_tenderned_raw_publicatiedatum', 'Publicatiedatum'),
        Index('idx_tenderned_raw_notice_id', 'notice_id'),
        Index('idx_tenderned_raw_bedrijfsnaam', 'Officiële benaming'),
        Index('idx_tenderned_raw_owner', 'owner_code'),
        Index('idx_tenderned_raw_bedrijfsnaam_datum', 'Officiële benaming', 'Publicatiedatum'),
    )


class TendernedRawCached(Base):
    __tablename__ = "tenderned_raw_cached"
    
    id = Column(BigInteger, primary_key=True, autoincrement=True)
    notice_id = Column(Text, unique=True)
    publicatie_id = Column(BigInteger)
    Publicatiedatum = Column("Publicatiedatum", Date)
    publicatie_datum = Column(DateTime(timezone=True))
    Naam_aanbesteding = Column("Naam aanbesteding", Text)
    titel = Column(Text)
    Omschrijving_aanbesteding = Column("Omschrijving aanbesteding", Text)
    omschrijving = Column(Text)
    URL_TenderNed = Column("URL TenderNed", Text)
    url = Column(Text)
    
    # Winner fields (both Dutch and normalized names)
    Officiele_benaming = Column("Officiële benaming", Text)
    win_bedrijf_naam = Column(Text)
    Kvknummer = Column("Kvknummer", Text)
    win_kvk = Column(Text)
    Postadres = Column("Postadres", Text)
    win_straat = Column(Text)
    Postcode = Column("Postcode", Text)
    win_postcode = Column(Text)
    Plaats = Column("Plaats", Text)
    win_plaats = Column(Text)
    Land = Column("Land", Text)
    win_land = Column(Text)
    win_contact_naam = Column(Text)
    win_contact_email = Column(Text)
    win_contact_tel = Column(Text)
    Internetadres = Column("Internetadres", Text)
    win_website = Column(Text)
    
    # Buyer fields
    Naam_Aanbestedende_dienst = Column("Naam Aanbestedende dienst", Text)
    buyer_bedrijf_naam = Column(Text)
    Nationaal_identificatienummer = Column("Nationaal identificatienummer", Text)
    buyer_kvk = Column(Text)
    buyer_straat = Column(Text)
    buyer_postcode = Column(Text)
    buyer_plaats = Column(Text)
    buyer_land = Column(Text)
    buyer_contact_naam = Column(Text)
    buyer_contact_email = Column(Text)
    buyer_contact_tel = Column(Text)
    buyer_website = Column(Text)
    
    bedrag = Column(Numeric)
    Waarde_valuta = Column("Waarde - valuta", Text)
    valuta = Column(Text)
    province = Column(Text)
    owner_code = Column(Text)
    heeft_eerdere_aanbestedingen = Column(Boolean, default=False)
    aantal_eerdere_aanbestedingen = Column(Integer, default=0)
    totaal_bedrag_eerdere_aanbestedingen = Column(Numeric)
    
    __table_args__ = (
        Index('idx_tenderned_raw_cached_publicatiedatum', 'Publicatiedatum'),
        Index('idx_tenderned_raw_cached_notice_id', 'notice_id'),
        Index('idx_tenderned_raw_cached_bedrijfsnaam', 'Officiële benaming'),
        Index('idx_tenderned_raw_cached_owner', 'owner_code'),
        Index('idx_tenderned_raw_cached_province', 'province'),
    )


class TendernedRawCPVCached(Base):
    __tablename__ = "tenderned_raw_cpv_cached"
    
    id = Column(BigInteger, primary_key=True, autoincrement=True)
    notice_id = Column(Text, unique=True)
    publicatie_id = Column(BigInteger)
    Publicatiedatum = Column("Publicatiedatum", Date)
    publicatie_datum = Column(DateTime(timezone=True))
    Naam_aanbesteding = Column("Naam aanbesteding", Text)
    titel = Column(Text)
    Omschrijving_aanbesteding = Column("Omschrijving aanbesteding", Text)
    omschrijving = Column(Text)
    URL_TenderNed = Column("URL TenderNed", Text)
    url = Column(Text)
    cpv_codes = Column(Text)
    
    # Winner fields
    Officiele_benaming = Column("Officiële benaming", Text)
    win_bedrijf_naam = Column(Text)
    Kvknummer = Column("Kvknummer", Text)
    win_kvk = Column(Text)
    Postadres = Column("Postadres", Text)
    win_straat = Column(Text)
    Postcode = Column("Postcode", Text)
    win_postcode = Column(Text)
    Plaats = Column("Plaats", Text)
    win_plaats = Column(Text)
    Land = Column("Land", Text)
    win_land = Column(Text)
    win_contact_naam = Column(Text)
    win_contact_email = Column(Text)
    win_contact_tel = Column(Text)
    Internetadres = Column("Internetadres", Text)
    win_website = Column(Text)
    
    # Buyer fields
    Naam_Aanbestedende_dienst = Column("Naam Aanbestedende dienst", Text)
    buyer_bedrijf_naam = Column(Text)
    Nationaal_identificatienummer = Column("Nationaal identificatienummer", Text)
    buyer_kvk = Column(Text)
    buyer_straat = Column(Text)
    buyer_postcode = Column(Text)
    buyer_plaats = Column(Text)
    buyer_land = Column(Text)
    buyer_contact_naam = Column(Text)
    buyer_contact_email = Column(Text)
    buyer_contact_tel = Column(Text)
    buyer_website = Column(Text)
    
    bedrag = Column(Numeric)
    Waarde_valuta = Column("Waarde - valuta", Text)
    valuta = Column(Text)
    province = Column(Text)
    owner_code = Column(Text)
    heeft_eerdere_aanbestedingen = Column(Boolean, default=False)
    aantal_eerdere_aanbestedingen = Column(Integer, default=0)
    totaal_bedrag_eerdere_aanbestedingen = Column(Numeric)
    cpv_code = Column(Text)
    cpv_label = Column(Text)
    
    __table_args__ = (
        Index('idx_tenderned_raw_cpv_cached_publicatiedatum', 'Publicatiedatum'),
        Index('idx_tenderned_raw_cpv_cached_notice_id', 'notice_id'),
        Index('idx_tenderned_raw_cpv_cached_bedrijfsnaam', 'Officiële benaming'),
        Index('idx_tenderned_raw_cpv_cached_owner', 'owner_code'),
        Index('idx_tenderned_raw_cpv_cached_province', 'province'),
        Index('idx_tenderned_raw_cpv_cached_cpv_codes', 'cpv_codes'),
    )
