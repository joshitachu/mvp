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
    
    # Nieuwe kolommen voor username/password (optioneel)
    username = Column(String, unique=True, nullable=True, index=True)
    password = Column(String, nullable=True)  # hashed password

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
    
    # Relationships
    notices = relationship("Notice", back_populates="import_record", cascade="all, delete-orphan")
    sroi_results = relationship("SROIResult", back_populates="import_record", cascade="all, delete-orphan")


class Notice(Base):
    __tablename__ = "notices"
    
    id = Column(BigInteger, primary_key=True, autoincrement=True)
    import_id = Column(UUID(as_uuid=True), ForeignKey("imports.id", ondelete="CASCADE"), nullable=False)
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


from pydantic import BaseModel, EmailStr
from typing import Optional
from datetime import date
class CompanyCreate(BaseModel):
    name: str  # -> Company field
    contact_name: Optional[str] = None  # -> LastName
    contact_email: Optional[EmailStr] = None  # -> Email
    contact_phone: Optional[str] = None  # -> Phone
    website: Optional[str] = None  # -> Website
    title: Optional[str] = None  # -> Title
    industry: Optional[str] = None  # -> Industry
    notes: Optional[str] = None  # -> Description
    lead_status: Optional[str] = "Open - Not Contacted"  # -> Status
    lead_source: Optional[str] = "Web Scraper"  # -> LeadSource
    annual_revenue: Optional[float] = None  # -> AnnualRevenue
    num_employees: Optional[int] = None  # -> NumberOfEmployees
    
    # Additional fields from frontend
    street: Optional[str] = None  # -> Street
    city: Optional[str] = None  # -> City
    postal_code: Optional[str] = None  # -> PostalCode
    state_province: Optional[str] = None  # -> State
    country: Optional[str] = None  # -> Country

class CompanyUpdate(BaseModel):
    lead_status: Optional[str] = None
    contact_name: Optional[str] = None
    contact_email: Optional[EmailStr] = None
    contact_phone: Optional[str] = None
    website: Optional[str] = None
    title: Optional[str] = None
    industry: Optional[str] = None
    notes: Optional[str] = None
    annual_revenue: Optional[float] = None
    num_employees: Optional[int] = None

class FollowupCreate(BaseModel):
    subject: str
    due_date: date
    notes: Optional[str] = None
    priority: Optional[str] = "Normal"

class CompanyResponse(BaseModel):
    id: str
    name: str
    contact_name: Optional[str]
    contact_email: Optional[str]
    contact_phone: Optional[str]
    website: Optional[str]
    title: Optional[str]
    industry: Optional[str]
    lead_status: str
    lead_source: Optional[str]
    notes: Optional[str]
    annual_revenue: Optional[float]
    num_employees: Optional[int]
    created_date: Optional[str]