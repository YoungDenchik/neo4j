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


class RelType(str, Enum):
    """
    Exhaustive list of all relationship types.
    WHY: Enforces schema governance - explicit, finite set of relationship types.
    Each relationship represents exactly one fact or action.
    """
    # Person → Organization
    DIRECTOR_OF = "DIRECTOR_OF"        # Person is director/head of organization
    FOUNDER_OF = "FOUNDER_OF"          # Person is founder/shareholder

    # Person → Person (family relationships)
    CHILD_OF = "CHILD_OF"              # Person is child of another person
    SPOUSE_OF = "SPOUSE_OF"            # Person is married to another person

    # IncomeRecord relationships (fact-based, not direct person-org)
    # WHY split: Allows efficient queries in both directions + clear money flow semantics
    EARNED_INCOME = "EARNED_INCOME"    # Person → IncomeRecord
    PAID_BY = "PAID_BY"                # IncomeRecord → Organization

    # Property relationships
    OWNS = "OWNS"                      # Person → Property

    # Power of Attorney relationships
    GRANTOR_OF = "GRANTOR_OF"          # Person granted PoA
    REPRESENTATIVE_OF = "REPRESENTATIVE_OF"  # Person received PoA
    AUTHORIZES_PROPERTY = "AUTHORIZES_PROPERTY"  # PoA → Property

    # Investigation relationships
    CREATED_REQUEST = "CREATED_REQUEST"  # Executor → Request
    SUBJECT_OF = "SUBJECT_OF"          # Request → Person (investigation target)


class PropertyType(str, Enum):
    """
    Types of property that can be owned.
    WHY: Controlled vocabulary for consistent categorization.
    """
    REAL_ESTATE = "REAL_ESTATE"        # Houses, apartments, land
    VEHICLE = "VEHICLE"                # Cars, motorcycles, etc.
    OTHER = "OTHER"


class IncomeType(str, Enum):
    """
    Common income type codes from Ukrainian tax system.
    WHY: These are standard government codes - mapping them enables
    consistent categorization across the entire dataset.

    Note: This is not exhaustive - source data has 100+ codes.
    We map the most common ones and use "OTHER" as fallback.
    """
    SALARY_PRIMARY = "101"             # Заробітна плата за основним місцем роботи
    SCHOLARSHIP = "150"                # Сума стипендії
    SOCIAL_PAYMENT = "128"             # Соціальні виплати з відповідних бюджетів
    LAND_RENT = "195"                  # Надання зем. ділянки, паю в оренду
    CIVIL_CONTRACT = "102"             # Виплати за цивільно-правовим договором
    SELF_EMPLOYED = "157"              # Дохід самозайнятої особи
    BONUS = "126"                      # Додаткове благо
    TAX_DECLARATION = "512"            # Податкова декларація (єдиний податок)
    OTHER = "999"                      # Unknown/other income type


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
