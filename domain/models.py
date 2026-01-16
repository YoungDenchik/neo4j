from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional, List, Dict, Any

from domain.enums import PropertyType, IncomeCategory


# ============================================================================
# DOMAIN ENTITIES (Neo4j Nodes)
# WHY:
# - These classes map 1:1 to Neo4j nodes (domain layer)
# - Nodes represent stable identities (rnokpp, edrpou, request_id, etc.)
# - They are immutable (frozen=True) to avoid accidental mutation during ingestion
# ============================================================================


@dataclass(frozen=True)
class Person:
    """
    Natural person (taxpayer, director, family member).
    Identity: RNOKPP (Ukrainian taxpayer id).
    """
    rnokpp: str
    last_name: str
    first_name: str
    middle_name: Optional[str] = None
    date_birth: Optional[str] = None  # ISO "YYYY-MM-DD"
    unzr: Optional[str] = None        # demographic registry id (if present)


@dataclass(frozen=True)
class PersonAlias:
    """
    Weak person identity used when RNOKPP is missing in the source data.

    WHY:
    - In court/civil registry records a person may appear only as a text name (PIB)
    - We cannot reliably merge such record into a Person node without a stable id
    - PersonAlias acts as a safe intermediate node that can later be linked to Person
    """
    alias_id: str                # synthetic hash (e.g., normalized full name + extra signals)
    full_name_raw: str           # raw "PIB" from source
    normalized_name: Optional[str] = None
    date_birth: Optional[str] = None


@dataclass(frozen=True)
class Organization:
    """
    Legal entity (company, government agency, tax agent).
    Identity: EDRPOU (company registration code).
    """
    edrpou: str
    name: str

    short_name: Optional[str] = None
    state: Optional[str] = None          # raw state code from source (e.g., "1", "3")
    state_text: Optional[str] = None     # human-readable state text from source

    olf_code: Optional[str] = None       # organizational-legal form code
    olf_name: Optional[str] = None

    authorised_capital: Optional[float] = None
    registration_date: Optional[str] = None  # ISO "YYYY-MM-DD"
    termination_date: Optional[str] = None


@dataclass(frozen=True)
class KvedActivity:
    """
    KVED activity (economic activity code).
    Identity: code.
    """
    code: str
    name: Optional[str] = None


@dataclass(frozen=True)
class Address:
    """
    Normalized address node.

    WHY as node:
    - Addresses can be shared between many persons/organizations/properties
    - Enables address-based traversals and clustering
    """
    address_id: str   # synthetic hash (e.g., normalized full_text)
    full_text: str

    region: Optional[str] = None
    district: Optional[str] = None
    city: Optional[str] = None
    street: Optional[str] = None
    building: Optional[str] = None
    apartment: Optional[str] = None
    postal_code: Optional[str] = None


@dataclass(frozen=True)
class Document:
    """
    Person identification document.
    Identity: doc_id (synthetic).
    """
    doc_id: str
    doc_type: str  # passport / idcard / foreign_passport

    series: Optional[str] = None
    number: Optional[str] = None
    issued_by: Optional[str] = None
    issued_date: Optional[str] = None
    expiry_date: Optional[str] = None


@dataclass(frozen=True)
class Request:
    """
    Investigation request document.
    Identity: request_id (IDrequest from source data).
    """
    request_id: str
    basis_request: Optional[str] = None
    application_number: Optional[str] = None
    application_date: Optional[str] = None

    period_begin_month: Optional[int] = None
    period_begin_year: Optional[int] = None
    period_end_month: Optional[int] = None
    period_end_year: Optional[int] = None


@dataclass(frozen=True)
class Executor:
    """
    Executor/investigator who created requests.
    Identity: executor_rnokpp OR (fallback) synthetic executor_id.
    """
    executor_id: str  # stable id for graph merge

    executor_rnokpp: Optional[str] = None
    executor_edrpou: Optional[str] = None
    full_name: Optional[str] = None

    position: Optional[str] = None
    department: Optional[str] = None


@dataclass(frozen=True)
class IncomeRecord:
    """
    Individual income payment event.
    Identity: synthetic income_id.
    """
    income_id: str

    income_accrued: float
    income_paid: float
    tax_charged: float
    tax_transferred: float

    income_type_code: str
    income_type_description: str

    period_quarter_month: str
    period_year: int
    result_income: int

    income_category: IncomeCategory = IncomeCategory.OTHER
    currency: str = "UAH"

    # provenance (optional but useful during ingestion/debug)
    source_request_id: Optional[str] = None


@dataclass(frozen=True)
class Property:
    """
    Real estate or vehicle asset.
    Identity: synthetic property_id.

    NOTE:
    - Land parcels are modeled separately as LandParcel
    """
    property_id: str
    property_type: PropertyType
    description: str

    # Vehicles
    government_reg_number: Optional[str] = None
    serial_number: Optional[str] = None

    # Real estate
    address_text: Optional[str] = None
    area: Optional[float] = None

    # provenance
    source_request_id: Optional[str] = None


@dataclass(frozen=True)
class LandParcel:
    """
    Land parcel asset.
    Identity: cadastre_number (or synthetic land_id).
    """
    land_id: str
    cadastre_number: str

    area: Optional[float] = None
    purpose: Optional[str] = None
    address_text: Optional[str] = None

    # provenance
    source_request_id: Optional[str] = None


@dataclass(frozen=True)
class NotarialBlank:
    """
    Notarial blank used for PoA registration.
    Identity: blank_id (synthetic serial:number).
    """
    blank_id: str
    serial: Optional[str] = None
    number: Optional[str] = None


@dataclass(frozen=True)
class PowerOfAttorney:
    """
    Legal power of attorney document.
    Identity: synthetic poa_id.
    """
    poa_id: str

    notarial_reg_number: Optional[str] = None
    attested_date: Optional[str] = None
    finished_date: Optional[str] = None

    witness_name: Optional[str] = None
    notary_name: Optional[str] = None

    # provenance
    source_request_id: Optional[str] = None


@dataclass(frozen=True)
class CourtCase:
    """
    Court case / legal record.
    Identity: synthetic case_id.
    """
    case_id: str

    court_name: Optional[str] = None
    case_number: Optional[str] = None
    judge: Optional[str] = None
    decision_date: Optional[str] = None

    category: Optional[str] = None
    document_type: Optional[str] = None
    result: Optional[str] = None

    # provenance
    source_request_id: Optional[str] = None


@dataclass(frozen=True)
class BirthRecord:
    """
    Civil registry birth record.
    Identity: record_id.
    """
    record_id: str
    record_date: Optional[str] = None
    registry_office: Optional[str] = None

    # Note: we do NOT store links here (rnokpp) as fields.
    # These connections are represented as relationships in the graph.
    source_request_id: Optional[str] = None


# ============================================================================
# RELATIONSHIP FACTS (with properties)
# WHY: These are not nodes - they're structured data for relationship creation.
# Services transform these into Neo4j relationships.
# ============================================================================


# @dataclass(frozen=True)
# class DirectorRelation:
#     """Person is director of organization."""
#     person_rnokpp: str
#     organization_edrpou: str
#     role_text: Optional[str] = None  # e.g., "керівник"


# @dataclass(frozen=True)
# class FounderRelation:
#     """Person is founder/shareholder of organization."""
#     person_rnokpp: str
#     organization_edrpou: str
#     capital: Optional[float] = None  # Investment amount
#     role_text: Optional[str] = None  # e.g., "засновник"


# @dataclass(frozen=True)
# class ChildOfRelation:
#     """Person is child of another person."""
#     child_rnokpp: str
#     parent_rnokpp: str


# @dataclass(frozen=True)
# class SpouseOfRelation:
#     """Person is married to another person."""
#     person_rnokpp: str
#     spouse_rnokpp: str
#     marriage_date: Optional[str] = None


# @dataclass(frozen=True)
# class OwnershipRelation:
#     """Person owns property."""
#     person_rnokpp: str
#     property_id: str
#     ownership_type: Optional[str] = None
#     since_date: Optional[str] = None


# ============================================================================
# COMPUTED VIEWS (Aggregated graph data for UI/analysis)
# WHY: These are NOT stored in Neo4j. They're constructed by services
# from graph queries. Represent complex subgraphs for business logic.
# ============================================================================


# @dataclass
# class PersonProfile:
#     """
#     Comprehensive person profile (computed view).
#     WHY: Aggregates data from multiple graph traversals for risk analysis.
#     Not stored - computed on-demand from graph.
#     """
#     person: Person

#     # Corporate connections
#     organizations_director: List[Organization] = field(default_factory=list)
#     organizations_founder: List[Organization] = field(default_factory=list)

#     # Income sources
#     income_records: List[IncomeRecord] = field(default_factory=list)
#     total_income_paid: float = 0.0
#     total_tax_paid: float = 0.0

#     # Properties
#     properties_direct: List[Property] = field(default_factory=list)
#     properties_via_poa: List[Property] = field(default_factory=list)

#     # Family network
#     children: List[Person] = field(default_factory=list)
#     parents: List[Person] = field(default_factory=list)
#     spouse: Optional[Person] = None

#     # Investigation metadata
#     requests: List[Request] = field(default_factory=list)

#     # Metadata for additional context
#     meta: Dict[str, Any] = field(default_factory=dict)


# ============================================================================
# COMPUTED VIEWS (NOT stored in Neo4j)
# WHY:
# - Built on-demand by services
# - Aggregates subgraphs for UI/risk analytics
# ============================================================================

@dataclass
class PersonProfile:
    """
    Computed view for a person.
    Not stored in Neo4j, built from graph traversals.
    """
    person: Person

    # Identity / KYC (from graph)
    documents: List[Document] = field(default_factory=list)
    registration_address: Optional[Address] = None

    # Corporate connections
    organizations_director: List[Organization] = field(default_factory=list)
    organizations_founder: List[Organization] = field(default_factory=list)

    # Income sources
    income_records: List[IncomeRecord] = field(default_factory=list)
    total_income_paid: float = 0.0
    total_tax_paid: float = 0.0
    income_by_year: Dict[int, float] = field(default_factory=dict)

    # Assets
    properties_direct: List[Property] = field(default_factory=list)
    land_parcels: List[LandParcel] = field(default_factory=list)

    # PoA network
    poa_received_by_person: List[PowerOfAttorney] = field(default_factory=list)
    poa_given_to_person: List[PowerOfAttorney] = field(default_factory=list)
    properties_via_poa: List[Property] = field(default_factory=list)

    # Legal / Court
    court_cases: List[CourtCase] = field(default_factory=list)

    # Investigation metadata
    requests: List[Request] = field(default_factory=list)

    # Risk/analytics
    risk_flags: List[str] = field(default_factory=list)
    risk_score: float = 0.0

    meta: Dict[str, Any] = field(default_factory=dict)


@dataclass
class OrganizationProfile:
    """
    Computed view for organization due diligence.
    """
    organization: Organization
    directors: List[Person] = field(default_factory=list)
    founders: List[Person] = field(default_factory=list)

    total_income_paid: float = 0.0
    employee_count: int = 0

    meta: Dict[str, Any] = field(default_factory=dict)

    
@dataclass
class IncomeAggregate:
    """
    Aggregated income statistics (computed view).
    WHY: For analyzing income patterns, tax compliance, and anomalies.
    """
    person_rnokpp: str
    tax_agent_edrpou: str
    tax_agent_name: str

    total_accrued: float = 0.0
    total_paid: float = 0.0
    total_tax_charged: float = 0.0
    total_tax_transferred: float = 0.0

    years: List[int] = field(default_factory=list)
    record_count: int = 0

    # Anomaly flags
    has_unpaid_income: bool = False  # accrued != paid
    has_unpaid_tax: bool = False  # charged != transferred


@dataclass
class FamilyWealthAggregate:
    """
    Aggregated wealth across family network (computed view).
    WHY: For detecting hidden wealth and beneficial ownership structures.
    """
    primary_person: Person
    family_members: List[Person] = field(default_factory=list)

    # Consolidated assets
    total_properties: int = 0
    properties: List[Property] = field(default_factory=list)

    # Consolidated income
    total_family_income: float = 0.0

    # Corporate control
    controlled_organizations: List[Organization] = field(default_factory=list)
