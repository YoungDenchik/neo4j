import json
import os
from typing import Iterator

from repositories.registry_repo import RegistryRepository
from repositories.mutation_repo import GraphMutationRepository
from pipeline.normalizer.core import LLMNormalizer
from pipeline.normalizer.converter import  NormalizationResult, convert_normalized_data


class IngestionPipeline:
    def __init__(self, parsed_dir: str) -> None:
        self.parsed_dir = parsed_dir
        self.normalizer = LLMNormalizer()
        self.registry_repo = RegistryRepository()
        self.mutation_repo = GraphMutationRepository()

    @staticmethod
    def _iter_parsed_files(parsed_dir: str) -> Iterator[str]:
        for root, dirs, files in os.walk(parsed_dir):
            for name in files:
                if name == "parsed.json":
                    yield os.path.join(root, name)

    def _load_items_from_file(self, path: str) -> list:
        try:
            with open(path, "r", encoding="utf-8") as f:
                data = json.load(f)
            if isinstance(data, dict) and "items" in data:
                items = data["items"]
                if isinstance(items, list):
                    return items
        except Exception:
            pass
        return []

    def run(self) -> None:
        self.registry_repo.ensure_constraints()

        for file_path in self._iter_parsed_files(self.parsed_dir):
            items = self._load_items_from_file(file_path)
            for item in items:
                try:
                    normalised = self.normalizer.normalize(item)
                    norm_result = convert_normalized_data(normalised)
                    self._persist_entities(norm_result)
                    self._persist_relationships(norm_result)
                except Exception:
                    continue

    def _persist_entities(self, result: NormalizationResult) -> None:
        for person in result.persons:
            try:
                self.registry_repo.merge_person(person)
            except Exception:
                pass
        for org in result.organizations:
            try:
                self.registry_repo.merge_organization(org)
            except Exception:
                pass
        for income in result.income_records:
            try:
                self.registry_repo.merge_income_record(income)
            except Exception:
                pass
        for prop in result.properties:
            try:
                self.registry_repo.merge_property(prop)
            except Exception:
                pass
        for request in result.requests:
            try:
                self.registry_repo.merge_request(request)
            except Exception:
                pass
        for executor in result.executors:
            try:
                self.registry_repo.merge_executor(executor)
            except Exception:
                pass
        for poa in result.poas:
            try:
                self.registry_repo.merge_power_of_attorney(poa)
            except Exception:
                pass

    def _persist_relationships(self, result: NormalizationResult) -> None:
        for rel in result.director_relations:
            try:
                self.mutation_repo.link_person_director_of_organization(
                    person_rnokpp=rel.person_rnokpp,
                    org_edrpou=rel.organization_edrpou,
                    role_text=rel.role_text,
                )
            except Exception:
                pass

        for rel in result.founder_relations:
            try:
                self.mutation_repo.link_person_founder_of_organization(
                    person_rnokpp=rel.person_rnokpp,
                    org_edrpou=rel.organization_edrpou,
                    capital=rel.capital,
                    role_text=rel.role_text,
                )
            except Exception:
                pass

        for rel in result.child_relations:
            try:
                self.mutation_repo.link_person_child_of_person(
                    child_rnokpp=rel.child_rnokpp,
                    parent_rnokpp=rel.parent_rnokpp,
                )
            except Exception:
                pass

        for rel in result.spouse_relations:
            try:
                self.mutation_repo.link_person_spouse_of_person(
                    person1_rnokpp=rel.person_rnokpp,
                    person2_rnokpp=rel.spouse_rnokpp,
                    marriage_date=rel.marriage_date,
                )
            except Exception:
                pass

        for rel in result.ownership_relations:
            try:
                self.mutation_repo.link_person_owns_property(
                    person_rnokpp=rel.person_rnokpp,
                    property_id=rel.property_id,
                    ownership_type=rel.ownership_type,
                    since_date=rel.since_date,
                )
            except Exception:
                pass

        for person_rnokpp, income_id in result.person_income_relations:
            try:
                self.mutation_repo.link_person_earned_income(
                    person_rnokpp=person_rnokpp,
                    income_id=income_id,
                )
            except Exception:
                pass

        for income_id, org_edrpou in result.income_paid_by_relations:
            try:
                self.mutation_repo.link_income_paid_by_organization(
                    income_id=income_id,
                    org_edrpou=org_edrpou,
                )
            except Exception:
                pass

        for person_rnokpp, poa_id in result.grantor_relations:
            try:
                self.mutation_repo.link_person_grantor_of_poa(
                    person_rnokpp=person_rnokpp,
                    poa_id=poa_id,
                )
            except Exception:
                pass

        for person_rnokpp, poa_id in result.representative_relations:
            try:
                self.mutation_repo.link_person_representative_of_poa(
                    person_rnokpp=person_rnokpp,
                    poa_id=poa_id,
                )
            except Exception:
                pass

        for poa_id, property_id in result.poa_property_relations:
            try:
                self.mutation_repo.link_poa_authorizes_property(
                    poa_id=poa_id,
                    property_id=property_id,
                )
            except Exception:
                pass

        for executor_rnokpp, request_id in result.executor_request_relations:
            try:
                self.mutation_repo.link_executor_created_request(
                    executor_rnokpp=executor_rnokpp,
                    request_id=request_id,
                )
            except Exception:
                pass

        for request_id, person_rnokpp in result.request_subject_relations:
            try:
                self.mutation_repo.link_request_subject_of_person(
                    request_id=request_id,
                    person_rnokpp=person_rnokpp,
                )
            except Exception:
                pass
