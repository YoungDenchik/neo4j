from __future__ import annotations

from enum import Enum


class NodeLabel(str, Enum):
    """
    Exhaustive list of all node types in the graph.
    WHY: Enforces schema governance - no dynamic label creation.
    """
    PERSON = "Person"
    ORGANIZATION = "Organization"
    INCOME_RECORD = "IncomeRecord"
    PROPERTY = "Property"
    REQUEST = "Request"
    EXECUTOR = "Executor"
    POWER_OF_ATTORNEY = "PowerOfAttorney"
    ADDRESS = "Address"
    DOCUMENT = "Document"
    COURT_CASE = "CourtCase"
    LAND_PARCEL = "LandParcel"
    BIRTH_RECORD = "BirthRecord"
    KVED_ACTIVITY = "KvedActivity"
    NOTARIAL_BLANK = "NotarialBlank"
    PERSON_ALIAS = "PersonAlias"  # дуже бажано, якщо в court rnokpp=null



class RelType(str, Enum):
    """
    Exhaustive list of relationship types in the graph.

    WHY:
    - Enforces a controlled, finite vocabulary of relationships (schema governance)
    - Prevents accidental/dynamic relationship creation
    - Makes traversals predictable for analytics, risk scoring, and investigation views

    Convention:
    - Relationship direction is meaningful (left -> right)
    - Each relationship represents exactly one fact / semantic meaning
    """

    # ============================================================
    # Corporate relationships (business / corporate governance)
    # ============================================================

    DIRECTOR_OF = "DIRECTOR_OF"   # Person -> Organization
                                 # The person acts as director / head / executive of the organization

    FOUNDER_OF = "FOUNDER_OF"     # Person -> Organization
                                 # The person is a founder / shareholder / beneficial owner of the organization

    HAS_KVED = "HAS_KVED"         # Organization -> KvedActivity
                                 # The organization is registered with a specific economic activity code (KVED)

    # ============================================================
    # Family relationships (civil registry / kinship network)
    # ============================================================

    CHILD_OF = "CHILD_OF"         # Person(child) -> Person(parent)
                                 # The person is a child of another person (parent relationship)

    SPOUSE_OF = "SPOUSE_OF"       # Person -> Person
                                 # Marriage / spouse relationship
                                 # (can be treated as symmetric during queries if needed)

    # ============================================================
    # Income relationships (fact-based financial events)
    # ============================================================

    EARNED_INCOME = "EARNED_INCOME"  # Person -> IncomeRecord
                                    # The person received/earned this specific income record

    PAID_BY = "PAID_BY"              # IncomeRecord -> Organization
                                    # The income record was paid by this organization (tax agent / employer)

    # ============================================================
    # Property / assets relationships
    # ============================================================

    OWNS = "OWNS"                 # Person -> Property (or LandParcel if modeled as Property)
                                 # The person is the legal owner of the asset

    # ============================================================
    # Power of Attorney (PoA) relationships (document-centric model)
    # ============================================================

    HAS_GRANTOR = "HAS_GRANTOR"   # PowerOfAttorney -> Person|Organization
                                 # The PoA was issued by the grantor (the entity delegating authority)

    HAS_REPRESENTATIVE = "HAS_REPRESENTATIVE"  # PowerOfAttorney -> Person|Organization
                                              # The PoA assigns authority to this representative (proxy/agent)

    HAS_PROPERTY = "HAS_PROPERTY" # PowerOfAttorney -> Property
                                 # The PoA is related to a specific asset (vehicle/real estate/etc.)

    HAS_NOTARIAL_BLANK = "HAS_NOTARIAL_BLANK"  # PowerOfAttorney -> NotarialBlank
                                              # The PoA was registered using a specific notarial blank (serial/number)

    # ============================================================
    # Investigation provenance (data lineage / audit trail)
    # ============================================================

    CREATED_BY = "CREATED_BY"     # Request -> Executor
                                 # The request was created by this executor/investigator

    ABOUT = "ABOUT"               # Request -> Person
                                 # The request targets or concerns this person (subject of investigation)

    PROVIDED = "PROVIDED"         # Request -> Any node (IncomeRecord/CourtCase/PoA/Property/...)
                                 # The request produced/returned this data entity (provenance link)


class PropertyType(str, Enum):
    """
    Types of property that can be owned.
    WHY: Controlled vocabulary for consistent categorization.
    """
    REAL_ESTATE = "REAL_ESTATE"        # Houses, apartments
    VEHICLE = "VEHICLE"                # Cars, motorcycles, etc.
    OTHER = "OTHER"
    LAND = "LAND"


# class IncomeType(str, Enum):
#     """
#     Common income type codes from Ukrainian tax system.
#     WHY: These are standard government codes - mapping them enables
#     consistent categorization across the entire dataset.

#     Note: This is not exhaustive - source data has 100+ codes.
#     We map the most common ones and use "OTHER" as fallback.
#     """
#     SALARY_PRIMARY = "101"             # Заробітна плата за основним місцем роботи
#     SCHOLARSHIP = "150"                # Сума стипендії
#     SOCIAL_PAYMENT = "128"             # Соціальні виплати з відповідних бюджетів
#     LAND_RENT = "195"                  # Надання зем. ділянки, паю в оренду
#     CIVIL_CONTRACT = "102"             # Виплати за цивільно-правовим договором
#     SELF_EMPLOYED = "157"              # Дохід самозайнятої особи
#     BONUS = "126"                      # Додаткове благо
#     TAX_DECLARATION = "512"            # Податкова декларація (єдиний податок)
#     OTHER = "999"                      # Unknown/other income type


class IncomeCategory(str, Enum):
    """
    High-level semantic categories for income records.

    WHY:
    - Source income_type_code contains many (100+) codes
    - We keep raw code, but map it into a stable category for analytics / risk scoring
    """
    SALARY = "SALARY"                # official employment salary
    CONTRACT = "CONTRACT"            # civil contracts / services
    BUSINESS = "BUSINESS"            # self-employed / entrepreneur income
    RENT = "RENT"                    # rent/lease payments (land/property)
    SOCIAL = "SOCIAL"                # social benefits / state payments
    SCHOLARSHIP = "SCHOLARSHIP"      # scholarships
    DIVIDENDS = "DIVIDENDS"          # dividends / corporate profit distribution
    INTEREST = "INTEREST"            # bank interest / deposits
    CAPITAL_GAIN = "CAPITAL_GAIN"    # sale of property / investment gains
    GIFT_INHERITANCE = "GIFT_INHERITANCE"  # gifts / inheritance
    BONUS_BENEFIT = "BONUS_BENEFIT"  # bonuses / additional benefits (додаткове благо)
    OTHER = "OTHER"                  # fallback


class OrganizationState(str, Enum):
    """
    Organization registration state.
    WHY: Critical for AML - dissolved companies are red flags.
    """
    REGISTERED = "1"                   # зареєстровано
    TERMINATED = "3"                   # припинено
    IN_LIQUIDATION = "2"               # в процесі припинення
    UNKNOWN = "0"


class OrganizationalLegalForm(str, Enum):
    """
    Common organizational-legal forms in Ukraine.
    WHY: Different entity types have different compliance requirements.
    """
    TOV = "240"                        # Товариство з обмеженою відповідальністю (LLC)
    PP = "260"                         # Приватне підприємство (Private Enterprise)
    AT = "230"                         # Акціонерне товариство (Joint-Stock Company)
    FOP = "801"                        # Фізична особа-підприємець (Sole Proprietor)
    GOVERNMENT = "070"                 # Державна організація
    OTHER = "999"
