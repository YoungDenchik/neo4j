"""
Neo4j Tax/AML Knowledge Graph - Example Usage

This demonstrates the complete system:
1. Initialize database with constraints
2. Ingest data from all_data.txt
3. Query person profiles
4. Analyze family wealth networks
5. Detect anomalies
"""

from core.neo4j_driver import init_driver, close_driver
from repositories.registry_repo import RegistryRepository
from repositories.mutation_repo import GraphMutationRepository
from repositories.read_repo import ReadRepository
from repositories.traversal_repo import TraversalRepository
from services.ingestion_service import IngestionService
from services.profile_service import ProfileService


def setup_database():
    """Initialize database schema (run once)."""
    print("Setting up database schema...")
    registry = RegistryRepository()
    registry.ensure_constraints()
    print("✓ Constraints and indexes created")


def ingest_data(file_path: str = "all_data.txt"):
    """Ingest data from JSON file."""
    print(f"\nIngesting data from {file_path}...")

    registry = RegistryRepository()
    mutation = GraphMutationRepository()
    ingestion = IngestionService(registry, mutation)

    line_count = 0
    try:
        with open(file_path, "r", encoding="utf-8") as f:
            for line in f:
                ingestion.ingest_json_record(line)
                line_count += 1
                if line_count % 50 == 0:
                    print(f"  Processed {line_count} records...")

        print(f"✓ Ingested {line_count} records successfully")

    except FileNotFoundError:
        print(f"⚠ File {file_path} not found. Skipping data ingestion.")
        print("  To ingest data, place all_data.txt in the project root.")


def query_statistics():
    """Display database statistics."""
    print("\nDatabase Statistics:")
    read_repo = ReadRepository()

    stats = {
        "Person": read_repo.count_nodes_by_label("Person"),
        "Organization": read_repo.count_nodes_by_label("Organization"),
        "IncomeRecord": read_repo.count_nodes_by_label("IncomeRecord"),
        "Property": read_repo.count_nodes_by_label("Property"),
        "Request": read_repo.count_nodes_by_label("Request"),
    }

    for label, count in stats.items():
        print(f"  {label}: {count}")


def demo_person_profile():
    """Demonstrate person profile queries."""
    print("\n" + "="*60)
    print("DEMO: Person Profile Analysis")
    print("="*60)

    read_repo = ReadRepository()
    traversal_repo = TraversalRepository()
    profile_service = ProfileService(read_repo, traversal_repo)

    # Find a person
    persons = read_repo.search_persons_by_name(last_name="АДЕЛЬРЕЇВ", limit=1)
    if not persons:
        print("No persons found in database. Run with data ingestion first.")
        return

    person = persons[0]
    rnokpp = person.rnokpp

    print(f"\nAnalyzing: {person.last_name} {person.first_name} (RNOKPP: {rnokpp})")

    # Get comprehensive profile
    profile = profile_service.get_person_profile(rnokpp)
    if not profile:
        print("Could not build profile.")
        return

    print(f"\n📊 FINANCIAL PROFILE:")
    print(f"  Total Income Paid: {profile.total_income_paid:,.2f} UAH")
    print(f"  Total Tax Paid: {profile.total_tax_paid:,.2f} UAH")
    print(f"  Income Records: {len(profile.income_records)}")
    print(f"  Income Sources: {profile.meta.get('income_sources_count', 0)}")

    print(f"\n🏢 CORPORATE CONNECTIONS:")
    print(f"  Director of {len(profile.organizations_director)} companies")
    print(f"  Founder of {len(profile.organizations_founder)} companies")

    for org in profile.organizations_director[:3]:  # Show first 3
        print(f"    • {org.name} (EDRPOU: {org.edrpou})")

    print(f"\n🏠 PROPERTY OWNERSHIP:")
    print(f"  Direct: {len(profile.properties_direct)} properties")
    print(f"  Via PoA: {len(profile.properties_via_poa)} properties")

    for prop in profile.properties_direct[:3]:  # Show first 3
        print(f"    • {prop.property_type.value}: {prop.description}")

    print(f"\n👨‍👩‍👧‍👦 FAMILY NETWORK:")
    print(f"  Children: {len(profile.children)}")
    print(f"  Parents: {len(profile.parents)}")
    print(f"  Spouse: {'Yes' if profile.spouse else 'No'}")

    # Income source analysis
    print(f"\n💰 TOP INCOME SOURCES:")
    income_by_agent = traversal_repo.get_income_by_tax_agent(rnokpp)
    for agg in income_by_agent[:5]:  # Top 5
        print(f"  • {agg.tax_agent_name}")
        print(f"    Total: {agg.total_paid:,.2f} UAH")
        print(f"    Years: {', '.join(map(str, sorted(agg.years)))}")
        if agg.has_unpaid_income:
            print(f"    ⚠ Has unpaid income!")
        if agg.has_unpaid_tax:
            print(f"    ⚠ Has unpaid tax!")


def demo_family_wealth():
    """Demonstrate family wealth aggregation."""
    print("\n" + "="*60)
    print("DEMO: Family Wealth Analysis")
    print("="*60)

    read_repo = ReadRepository()
    traversal_repo = TraversalRepository()
    profile_service = ProfileService(read_repo, traversal_repo)

    # Find a person with family
    persons = read_repo.search_persons_by_name(last_name="СВІФТ", limit=1)
    if not persons:
        print("No matching persons found.")
        return

    person = persons[0]
    rnokpp = person.rnokpp

    print(f"\nAnalyzing family of: {person.last_name} {person.first_name}")

    # Get family wealth aggregate
    aggregate = profile_service.get_family_wealth_aggregate(rnokpp, family_depth=2)
    if not aggregate:
        print("Could not build family aggregate.")
        return

    print(f"\n👨‍👩‍👧‍👦 FAMILY NETWORK:")
    print(f"  Primary Person: {aggregate.primary_person.last_name} {aggregate.primary_person.first_name}")
    print(f"  Family Members: {len(aggregate.family_members)}")

    print(f"\n💎 CONSOLIDATED WEALTH:")
    print(f"  Total Properties: {aggregate.total_properties}")
    print(f"  Total Family Income: {aggregate.total_family_income:,.2f} UAH")
    print(f"  Controlled Organizations: {len(aggregate.controlled_organizations)}")

    print(f"\n🏢 FAMILY-CONTROLLED COMPANIES:")
    for org in aggregate.controlled_organizations[:5]:  # First 5
        print(f"  • {org.name} ({org.state_text})")


def demo_network_analysis():
    """Demonstrate network analysis queries."""
    print("\n" + "="*60)
    print("DEMO: Network Analysis")
    print("="*60)

    traversal_repo = TraversalRepository()

    # Find circular ownership
    print("\n🔄 CIRCULAR OWNERSHIP DETECTION:")
    cycles = traversal_repo.find_circular_ownership(max_depth=5)
    if cycles:
        print(f"  Found {len(cycles)} circular ownership structures")
        for i, cycle in enumerate(cycles[:3], 1):  # Show first 3
            print(f"  {i}. {' → '.join(cycle[:5])}...")  # First 5 nodes
    else:
        print("  No circular ownership detected")

    # Co-director analysis
    print("\n🤝 CO-DIRECTOR ANALYSIS:")
    read_repo = ReadRepository()
    persons = read_repo.search_persons_by_name(last_name="АДЕЛЬРЕЇВ", limit=1)
    if persons:
        person = persons[0]
        co_directors = traversal_repo.get_co_directors(person.rnokpp)
        if co_directors:
            print(f"  {person.last_name} shares boards with {len(co_directors)} people:")
            for cd in co_directors[:5]:  # First 5
                p = cd['person']
                print(f"  • {p.last_name} {p.first_name}: {cd['shared_count']} shared companies")
        else:
            print(f"  {person.last_name} has no co-directors")


def main():
    """Main entry point."""
    print("\n" + "="*60)
    print("Neo4j Tax/AML Knowledge Graph - Demo")
    print("="*60)

    # Initialize Neo4j driver
    init_driver()

    try:
        # 1. Setup database schema
        setup_database()

        # 2. Ingest data (optional if file doesn't exist)
        ingest_data()

        # 3. Display statistics
        query_statistics()

        # 4. Run demonstrations
        demo_person_profile()
        demo_family_wealth()
        demo_network_analysis()

        print("\n" + "="*60)
        print("Demo completed successfully!")
        print("="*60)

    except Exception as e:
        print(f"\n❌ Error: {e}")
        raise

    finally:
        # Cleanup
        close_driver()


if __name__ == "__main__":
    main()
