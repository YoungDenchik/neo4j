from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional, List, Dict, Any

from domain.enums import AssetType


@dataclass(frozen=True)
class Person:
    person_id: str
    name: str
    birth_date: Optional[str] = None  # ISO "YYYY-MM-DD" (якщо є)


@dataclass(frozen=True)
class Company:
    company_id: str
    name: str
    edrpou: Optional[str] = None


@dataclass(frozen=True)
class Asset:
    asset_id: str
    asset_type: AssetType
    value: Optional[float] = None
    description: Optional[str] = None


@dataclass
class PersonProfile:
    """Computed view (агрегований підграф) для UI/аналізу."""
    person: Person
    companies: List[Company] = field(default_factory=list)
    assets_direct: List[Asset] = field(default_factory=list)     # Person -[:OWNS]-> Asset
    assets_indirect: List[Asset] = field(default_factory=list)   # Person -> Company -> Asset
    meta: Dict[str, Any] = field(default_factory=dict)
