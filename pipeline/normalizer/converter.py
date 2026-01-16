import hashlib
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Tuple

from domain.models import (
    Person,
    Organization,
    IncomeRecord,
    Property,
    Request,
    Executor,
    PowerOfAttorney,
    DirectorRelation,
    FounderRelation,
    ChildOfRelation,
    SpouseOfRelation,
    OwnershipRelation,
)
from domain.enums import PropertyType


@dataclass
class NormalizationResult:
    persons: List[Person] = field(default_factory=list)
    organizations: List[Organization] = field(default_factory=list)
    income_records: List[IncomeRecord] = field(default_factory=list)
    properties: List[Property] = field(default_factory=list)
    requests: List[Request] = field(default_factory=list)
    executors: List[Executor] = field(default_factory=list)
    poas: List[PowerOfAttorney] = field(default_factory=list)

    director_relations: List[DirectorRelation] = field(default_factory=list)
    founder_relations: List[FounderRelation] = field(default_factory=list)
    child_relations: List[ChildOfRelation] = field(default_factory=list)
    spouse_relations: List[SpouseOfRelation] = field(default_factory=list)
    ownership_relations: List[OwnershipRelation] = field(default_factory=list)

    person_income_relations: List[Tuple[str, str]] = field(default_factory=list)
    income_paid_by_relations: List[Tuple[str, str]] = field(default_factory=list)
    grantor_relations: List[Tuple[str, str]] = field(default_factory=list)
    representative_relations: List[Tuple[str, str]] = field(default_factory=list)
    poa_property_relations: List[Tuple[str, str]] = field(default_factory=list)
    executor_request_relations: List[Tuple[str, str]] = field(default_factory=list)
    request_subject_relations: List[Tuple[str, str]] = field(default_factory=list)


def _hash_string(value: str) -> str:
    return hashlib.sha1(value.encode("utf-8")).hexdigest()


def _compute_income_id(
    person_rnokpp: str,
    org_edrpou: str,
    period_year: int,
    period_quarter_month: str,
    income_type_code: str,
) -> str:
    composite = f"{person_rnokpp}|{org_edrpou}|{period_year}|{period_quarter_month}|{income_type_code}"
    return _hash_string(composite)


def _compute_property_id(
    property_type: str,
    description: str,
    government_reg_number: Optional[str],
    serial_number: Optional[str],
    address: Optional[str],
    area: Optional[float],
) -> str:
    composite = "|".join([
        property_type or "",
        description or "",
        government_reg_number or "",
        serial_number or "",
        address or "",
        str(area or ""),
    ])
    return _hash_string(composite)


def _compute_poa_id(
    notarial_reg_number: Optional[str],
    attested_date: Optional[str],
    finished_date: Optional[str],
    witness_name: Optional[str],
) -> str:
    composite = "|".join([
        notarial_reg_number or "",
        attested_date or "",
        finished_date or "",
        witness_name or "",
    ])
    return _hash_string(composite)


def convert_normalized_data(data: Dict) -> NormalizationResult:
    result = NormalizationResult()

    for p in data.get("persons", []) or []:
        try:
            person = Person(
                rnokpp=str(p["rnokpp"]),
                last_name=p.get("last_name", "") or "",
                first_name=p.get("first_name", "") or "",
                middle_name=p.get("middle_name"),
                date_birth=p.get("date_birth"),
            )
            result.persons.append(person)
        except Exception:
            continue

    for o in data.get("organizations", []) or []:
        try:
            org = Organization(
                edrpou=str(o["edrpou"]),
                name=o.get("name", "") or "",
                short_name=o.get("short_name"),
                state=o.get("state"),
                state_text=o.get("state_text"),
                olf_code=o.get("olf_code"),
                olf_name=o.get("olf_name"),
                authorised_capital=(
                    float(o["authorised_capital"]) if o.get("authorised_capital") is not None else None
                ),
                registration_date=o.get("registration_date"),
            )
            result.organizations.append(org)
        except Exception:
            continue

    for i in data.get("income_records", []) or []:
        try:
            person_rnokpp = str(i["person_rnokpp"])
            org_edrpou = str(i["org_edrpou"])
            period_year = int(i["period_year"])
            period_qm = i.get("period_quarter_month", "") or ""
            income_type_code = str(i.get("income_type_code", ""))
            income_id = _compute_income_id(
                person_rnokpp=person_rnokpp,
                org_edrpou=org_edrpou,
                period_year=period_year,
                period_quarter_month=period_qm,
                income_type_code=income_type_code,
            )
            income = IncomeRecord(
                income_id=income_id,
                income_accrued=float(i.get("income_accrued", 0.0) or 0.0),
                income_paid=float(i.get("income_paid", 0.0) or 0.0),
                tax_charged=float(i.get("tax_charged", 0.0) or 0.0),
                tax_transferred=float(i.get("tax_transferred", 0.0) or 0.0),
                income_type_code=income_type_code,
                income_type_description=i.get("income_type_description", "") or "",
                period_quarter_month=period_qm,
                period_year=period_year,
                result_income=int(i.get("result_income", 0) or 0),
            )
            result.income_records.append(income)
            result.person_income_relations.append((person_rnokpp, income_id))
            result.income_paid_by_relations.append((income_id, org_edrpou))
        except Exception:
            continue

    for prop in data.get("properties", []) or []:
        try:
            owner_rnokpp = str(prop["owner_rnokpp"])
            property_type_raw = prop.get("property_type", "UNKNOWN") or "UNKNOWN"
            try:
                property_type = PropertyType[property_type_raw]
            except KeyError:
                property_type = PropertyType.UNKNOWN
            description = prop.get("description", "") or ""
            government_reg_number = prop.get("government_reg_number")
            serial_number = prop.get("serial_number")
            address = prop.get("address")
            area_value = prop.get("area")
            try:
                area = float(area_value) if area_value is not None else None
            except Exception:
                area = None
            property_id = _compute_property_id(
                property_type=property_type.name,
                description=description,
                government_reg_number=government_reg_number,
                serial_number=serial_number,
                address=address,
                area=area,
            )
            property_obj = Property(
                property_id=property_id,
                property_type=property_type,
                description=description,
                government_reg_number=government_reg_number,
                serial_number=serial_number,
                address=address,
                area=area,
            )
            result.properties.append(property_obj)
            result.ownership_relations.append(
                OwnershipRelation(
                    person_rnokpp=owner_rnokpp,
                    property_id=property_id,
                    ownership_type=prop.get("ownership_type"),
                    since_date=prop.get("since_date"),
                )
            )
        except Exception:
            continue

    for r in data.get("requests", []) or []:
        try:
            request_id = str(r["request_id"])
            req = Request(
                request_id=request_id,
                basis_request=r.get("basis_request"),
                application_number=r.get("application_number"),
                application_date=r.get("application_date"),
                period_begin_month=(
                    int(r.get("period_begin_month")) if r.get("period_begin_month") is not None else None
                ),
                period_begin_year=(
                    int(r.get("period_begin_year")) if r.get("period_begin_year") is not None else None
                ),
                period_end_month=(
                    int(r.get("period_end_month")) if r.get("period_end_month") is not None else None
                ),
                period_end_year=(
                    int(r.get("period_end_year")) if r.get("period_end_year") is not None else None
                ),
            )
            result.requests.append(req)
            subj = r.get("subject_rnokpp")
            exec_r = r.get("executor_rnokpp")
            if exec_r:
                result.executor_request_relations.append((str(exec_r), request_id))
            if subj:
                result.request_subject_relations.append((request_id, str(subj)))
        except Exception:
            continue

    for e in data.get("executors", []) or []:
        try:
            executor = Executor(
                executor_rnokpp=str(e["executor_rnokpp"]),
                executor_edrpou=e.get("executor_edrpou"),
                full_name=e.get("full_name", "") or "",
            )
            result.executors.append(executor)
        except Exception:
            continue

    for p in data.get("power_of_attorney", []) or []:
        try:
            notarial_reg_number = p.get("notarial_reg_number")
            attested_date = p.get("attested_date")
            finished_date = p.get("finished_date")
            witness_name = p.get("witness_name")
            poa_id = _compute_poa_id(
                notarial_reg_number=notarial_reg_number,
                attested_date=attested_date,
                finished_date=finished_date,
                witness_name=witness_name,
            )
            poa_obj = PowerOfAttorney(
                poa_id=poa_id,
                notarial_reg_number=notarial_reg_number,
                attested_date=attested_date,
                finished_date=finished_date,
                witness_name=witness_name,
            )
            result.poas.append(poa_obj)
            grantor = p.get("grantor_rnokpp")
            representative = p.get("representative_rnokpp")
            if grantor:
                result.grantor_relations.append((str(grantor), poa_id))
            if representative:
                result.representative_relations.append((str(representative), poa_id))
            prop_obj = p.get("property")
            if isinstance(prop_obj, dict):
                try:
                    property_type_raw = prop_obj.get("property_type", "UNKNOWN") or "UNKNOWN"
                    try:
                        property_type_enum = PropertyType[property_type_raw]
                    except KeyError:
                        property_type_enum = PropertyType.UNKNOWN
                    description = prop_obj.get("description", "") or ""
                    government_reg_number = prop_obj.get("government_reg_number")
                    serial_number = prop_obj.get("serial_number")
                    address = prop_obj.get("address")
                    area_value = prop_obj.get("area")
                    try:
                        area = float(area_value) if area_value is not None else None
                    except Exception:
                        area = None
                    property_id = _compute_property_id(
                        property_type=property_type_enum.name,
                        description=description,
                        government_reg_number=government_reg_number,
                        serial_number=serial_number,
                        address=address,
                        area=area,
                    )
                    property_obj = Property(
                        property_id=property_id,
                        property_type=property_type_enum,
                        description=description,
                        government_reg_number=government_reg_number,
                        serial_number=serial_number,
                        address=address,
                        area=area,
                    )
                    result.properties.append(property_obj)
                    result.poa_property_relations.append((poa_id, property_id))
                except Exception:
                    pass
        except Exception:
            continue

    for rel in data.get("relations", []) or []:
        if not isinstance(rel, dict) or "type" not in rel:
            continue
        rel_type = rel["type"].upper()
        if rel_type == "DIRECTOR_OF":
            person_rnokpp = rel.get("person_rnokpp")
            org_edrpou = rel.get("org_edrpou")
            if person_rnokpp and org_edrpou:
                result.director_relations.append(
                    DirectorRelation(
                        person_rnokpp=str(person_rnokpp),
                        organization_edrpou=str(org_edrpou),
                        role_text=rel.get("role_text"),
                    )
                )
        elif rel_type == "FOUNDER_OF":
            person_rnokpp = rel.get("person_rnokpp")
            org_edrpou = rel.get("org_edrpou")
            if person_rnokpp and org_edrpou:
                capital = None
                if rel.get("capital") is not None:
                    try:
                        capital = float(rel["capital"])
                    except Exception:
                        capital = None
                result.founder_relations.append(
                    FounderRelation(
                        person_rnokpp=str(person_rnokpp),
                        organization_edrpou=str(org_edrpou),
                        capital=capital,
                        role_text=rel.get("role_text"),
                    )
                )
        elif rel_type == "CHILD_OF":
            child = rel.get("child_rnokpp")
            parent = rel.get("parent_rnokpp")
            if child and parent:
                result.child_relations.append(
                    ChildOfRelation(
                        child_rnokpp=str(child),
                        parent_rnokpp=str(parent),
                    )
                )
        elif rel_type == "SPOUSE_OF":
            p1 = rel.get("person1_rnokpp")
            p2 = rel.get("person2_rnokpp")
            if p1 and p2:
                result.spouse_relations.append(
                    SpouseOfRelation(
                        person_rnokpp=str(p1),
                        spouse_rnokpp=str(p2),
                        marriage_date=rel.get("marriage_date"),
                    )
                )

    return result
