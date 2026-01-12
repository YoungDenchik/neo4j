from core.neo4j_driver import init_driver, close_driver
from repositories.registry_repo import RegistryRepository
from repositories.mutation_repo import GraphMutationRepository
from repositories.read_repo import ReadRepository
from repositories.traversal_repo import TraversalRepository
from services.ingestion_service import IngestionService
from services.profile_service import ProfileService
from services.risk_analysis_service import RiskAnalysisService
from services.llm_service import LLMService
from domain.models import Person, Company, Asset
from domain.enums import AssetType

def main():
    init_driver()

    registry = RegistryRepository()
    registry.ensure_constraints()

    mutation = GraphMutationRepository()
    read_repo = ReadRepository()
    traversal = TraversalRepository()

    ingestion = IngestionService(registry, mutation)
    profiles = ProfileService(read_repo, traversal)
    risk = RiskAnalysisService(asset_value_threshold=1_000_000)
    llm = LLMService()

    # demo data
    p = Person(person_id="P1", name="Ivan Petrenko")
    c = Company(company_id="C1", name="ABC LLC")
    a = Asset(asset_id="A1", asset_type=AssetType.APARTMENT, value=2_500_000, description="Kyiv apartment")

    ingestion.fact_person_director_of_company(p, c)
    ingestion.fact_company_owns_asset(c, a)

    profile = profiles.get_person_profile("P1")
    if profile:
        signals = risk.analyze_profile(profile)
        print(llm.explain_risk(profile, signals))

    close_driver()

if __name__ == "__main__":
    main()
