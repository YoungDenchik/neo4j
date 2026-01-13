from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional, List, Dict, Any
from datetime import date, datetime

from domain.enums import PropertyType, OrganizationState


# ============================================================================
# DOMAIN ENTITIES (Nodes in the graph)
# WHY: Immutable dataclasses represent real-world entities with stable identities.
# These map 1:1 to Neo4j nodes.
# ============================================================================


@dataclass(frozen=True)
class Person:
    """
    Natural person (taxpayer, director, family member).
    Identity: RNOKPP (Ukrainian tax identification number).
    WHY immutable: Person attributes don't change frequently; if they do, we MERGE.
    """
    rnokpp: str  # Unique tax ID
    last_name: str
    first_name: str
    middle_name: Optional[str] = None
    date_birth: Optional[str] = None  # ISO "YYYY-MM-DD"


@dataclass(frozen=True)
class Organization:
    """
    Legal entity (company, government agency, tax agent).
    Identity: EDRPOU (Ukrainian company registration code).
    WHY separate from Person: Different legal status, lifecycle, and compliance rules.
    """
    edrpou: str  # Unique company code
    name: str
    short_name: Optional[str] = None
    state: Optional[str] = None  # e.g., "1" = registered, "3" = terminated
    state_text: Optional[str] = None  # Human-readable state
    olf_code: Optional[str] = None  # Organizational-legal form code
    olf_name: Optional[str] = None  # e.g., "ТОВАРИСТВО З ОБМЕЖЕНОЮ ВІДПОВІДАЛЬНІСТЮ"
    authorised_capital: Optional[float] = None
    registration_date: Optional[str] = None  # ISO "YYYY-MM-DD"


@dataclass(frozen=True)
class IncomeRecord:
    """
    Individual income payment event.
    Identity: Synthetic income_id (hash of person + tax_agent + period + type).
    WHY as node (not relationship): Each payment is a queryable fact with many attributes.
    Allows temporal queries and prevents relationship property explosion.
    """
    income_id: str  # Synthetic unique ID
    income_accrued: float  # Нараховано
    income_paid: float  # Виплачено
    tax_charged: float  # Податок нарахований
    tax_transferred: float  # Податок перерахований
    income_type_code: str  # e.g., "101", "150", "195"
    income_type_description: str  # Human-readable type
    period_quarter_month: str  # e.g., "1 квартал", "Січень", "Квітень"
    period_year: int
    result_income: int  # Typically 1 (success) or 2 (self-declaration)


@dataclass(frozen=True)
class Property:
    """
    Real estate or vehicle.
    Identity: Synthetic property_id (generated from source data).
    WHY: Properties are key in AML - unexplained ownership is a red flag.
    """
    property_id: str  # Synthetic unique ID
    property_type: PropertyType
    description: str
    government_reg_number: Optional[str] = None  # For vehicles (license plate)
    serial_number: Optional[str] = None  # VIN for vehicles
    address: Optional[str] = None  # For real estate
    area: Optional[float] = None  # Square meters for real estate


@dataclass(frozen=True)
class Request:
    """
    Investigation request document.
    Identity: request_id (from IDrequest field in source data).
    WHY: Tracks provenance - which investigations triggered which data collection.
    """
    request_id: str  # e.g., "З-2025-1898-062-1A0"
    basis_request: Optional[str] = None  # e.g., "6161-ТІТ"
    application_number: Optional[str] = None
    application_date: Optional[str] = None  # ISO datetime
    period_begin_month: Optional[int] = None
    period_begin_year: Optional[int] = None
    period_end_month: Optional[int] = None
    period_end_year: Optional[int] = None


@dataclass(frozen=True)
class Executor:
    """
    Person who created the investigation request.
    Identity: executor_rnokpp.
    WHY separate from Person: Executors are investigators, not subjects.
    Different domain role prevents query confusion.
    """
    executor_rnokpp: str  # Tax ID
    executor_edrpou: Optional[str] = None  # Organization code
    full_name: str


@dataclass(frozen=True)
class PowerOfAttorney:
    """
    Legal power of attorney document.
    Identity: Synthetic poa_id (from notarial registration number + date).
    WHY: Shows control relationships - who can act on behalf of whom.
    Critical for detecting hidden beneficial owners.
    """
    poa_id: str  # Synthetic unique ID
    notarial_reg_number: Optional[str] = None
    attested_date: Optional[str] = None  # ISO datetime
    finished_date: Optional[str] = None  # ISO datetime (expiration)
    witness_name: Optional[str] = None  # Notary details


# ============================================================================
# RELATIONSHIP FACTS (with properties)
# WHY: These are not nodes - they're structured data for relationship creation.
# Services transform these into Neo4j relationships.
# ============================================================================


@dataclass(frozen=True)
class DirectorRelation:
    """Person is director of organization."""
    person_rnokpp: str
    organization_edrpou: str
    role_text: Optional[str] = None  # e.g., "керівник"


@dataclass(frozen=True)
class FounderRelation:
    """Person is founder/shareholder of organization."""
    person_rnokpp: str
    organization_edrpou: str
    capital: Optional[float] = None  # Investment amount
    role_text: Optional[str] = None  # e.g., "засновник"


@dataclass(frozen=True)
class ChildOfRelation:
    """Person is child of another person."""
    child_rnokpp: str
    parent_rnokpp: str


@dataclass(frozen=True)
class SpouseOfRelation:
    """Person is married to another person."""
    person_rnokpp: str
    spouse_rnokpp: str
    marriage_date: Optional[str] = None


@dataclass(frozen=True)
class OwnershipRelation:
    """Person owns property."""
    person_rnokpp: str
    property_id: str
    ownership_type: Optional[str] = None
    since_date: Optional[str] = None


# ============================================================================
# COMPUTED VIEWS (Aggregated graph data for UI/analysis)
# WHY: These are NOT stored in Neo4j. They're constructed by services
# from graph queries. Represent complex subgraphs for business logic.
# ============================================================================


@dataclass
class PersonProfile:
    """
    Comprehensive person profile (computed view).
    WHY: Aggregates data from multiple graph traversals for risk analysis.
    Not stored - computed on-demand from graph.
    """
    person: Person

    # Corporate connections
    organizations_director: List[Organization] = field(default_factory=list)
    organizations_founder: List[Organization] = field(default_factory=list)

    # Income sources
    income_records: List[IncomeRecord] = field(default_factory=list)
    total_income_paid: float = 0.0
    total_tax_paid: float = 0.0

    # Properties
    properties_direct: List[Property] = field(default_factory=list)
    properties_via_poa: List[Property] = field(default_factory=list)

    # Family network
    children: List[Person] = field(default_factory=list)
    parents: List[Person] = field(default_factory=list)
    spouse: Optional[Person] = None

    # Investigation metadata
    requests: List[Request] = field(default_factory=list)

    # Metadata for additional context
    meta: Dict[str, Any] = field(default_factory=dict)


@dataclass
class OrganizationProfile:
    """
    Comprehensive organization profile (computed view).
    WHY: Aggregates corporate structure for due diligence.
    """
    organization: Organization

    # People connected to this organization
    directors: List[Person] = field(default_factory=list)
    founders: List[Person] = field(default_factory=list)

    # Financial activity
    total_income_paid: float = 0.0  # Total paid to all employees
    employee_count: int = 0  # Number of people who received income

    # Metadata
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
