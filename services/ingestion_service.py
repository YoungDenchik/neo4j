from __future__ import annotations

from domain.models import Person, Company, Asset
from repositories.registry_repo import RegistryRepository
from repositories.mutation_repo import GraphMutationRepository


class IngestionService:
    """
    Facts → Graph:
    - merge nodes (identity)
    - create relationships (facts)
    """

    def __init__(
        self,
        registry_repo: RegistryRepository,
        mutation_repo: GraphMutationRepository,
    ):
        self.registry = registry_repo
        self.mutation = mutation_repo

    def upsert_person(self, person: Person) -> None:
        self.registry.merge_person(person)

    def upsert_company(self, company: Company) -> None:
        self.registry.merge_company(company)

    def upsert_asset(self, asset: Asset) -> None:
        self.registry.merge_asset(asset)

    # --- Domain facts (relationships) ---

    def fact_person_owns_asset(self, person: Person, asset: Asset, since_year: int | None = None) -> None:
        self.registry.merge_person(person)
        self.registry.merge_asset(asset)
        self.mutation.link_person_owns_asset(person.person_id, asset.asset_id, since_year=since_year)

    def fact_person_director_of_company(self, person: Person, company: Company) -> None:
        self.registry.merge_person(person)
        self.registry.merge_company(company)
        self.mutation.link_person_director_of_company(person.person_id, company.company_id)

    def fact_person_owner_of_company(self, person: Person, company: Company, share: float | None = None) -> None:
        self.registry.merge_person(person)
        self.registry.merge_company(company)
        self.mutation.link_person_owner_of_company(person.person_id, company.company_id, share=share)

    def fact_company_owns_asset(self, company: Company, asset: Asset) -> None:
        self.registry.merge_company(company)
        self.registry.merge_asset(asset)
        self.mutation.link_company_owns_asset(company.company_id, asset.asset_id)
