from __future__ import annotations

from enum import Enum


class NodeLabel(str, Enum):
    PERSON = "Person"
    COMPANY = "Company"
    ASSET = "Asset"


class RelType(str, Enum):
    # Person → Asset
    OWNS = "OWNS"

    # Person → Company
    DIRECTOR_OF = "DIRECTOR_OF"
    OWNER_OF = "OWNER_OF"  # optional but часто корисно

    # Company → Asset
    COMPANY_OWNS = "OWNS"  # той самий тип ребра; семантика визначається напрямком/лейблами


class AssetType(str, Enum):
    APARTMENT = "APARTMENT"
    HOUSE = "HOUSE"
    LAND = "LAND"
    VEHICLE = "VEHICLE"
    OTHER = "OTHER"
