from __future__ import annotations

from repositories.read_repo import ReadRepository
from repositories.traversal_repo import TraversalRepository
from domain.models import PersonProfile, OrganizationProfile, FamilyWealthAggregate


class ProfileService:
    """
    Profile aggregation service (computed views).

    RESPONSIBILITIES:
    - Build comprehensive entity profiles from graph data
    - Aggregate data from multiple repositories
    - Apply business logic for profile computation
    - NO direct database access (uses repositories)

    WHY: Separates profile construction from data retrieval.
    Business logic for "what makes a complete profile" lives here.

    DESIGN PRINCIPLE: Services orchestrate multiple repositories.
    Repositories return raw data, services transform into domain models.
    """

    def __init__(
        self,
        read_repo: ReadRepository,
        traversal_repo: TraversalRepository,
    ):
        self.read_repo = read_repo
        self.traversal_repo = traversal_repo

    # ========================================================================
    # Person profiles
    # ========================================================================

    def get_person_profile(self, rnokpp: str) -> PersonProfile | None:
        """
        Build comprehensive person profile.
        WHY: Aggregates all relevant data for AML/KYC analysis.
        """
        # Fetch person entity
        person = self.read_repo.get_person_by_rnokpp(rnokpp)
        if person is None:
            return None

        # Build profile with all related data
        profile = PersonProfile(person=person)

        # Corporate connections
        org_data = self.traversal_repo.get_organizations_controlled_by_person(rnokpp)
        profile.organizations_director = org_data.get("director_of", [])
        profile.organizations_founder = org_data.get("founder_of", [])

        # Income data
        profile.income_records = self.read_repo.get_income_records_for_person(rnokpp)
        profile.total_income_paid = self.read_repo.get_total_income_for_person(rnokpp)
        profile.total_tax_paid = sum(
            record.tax_transferred for record in profile.income_records
        )

        # Property ownership
        profile.properties_direct = self.read_repo.get_properties_owned_by_person(rnokpp)
        profile.properties_via_poa = self.traversal_repo.get_properties_controlled_via_poa(rnokpp)

        # Family network
        family = self.traversal_repo.get_family_network(rnokpp, depth=2)
        profile.children = family.get("children", [])
        profile.parents = family.get("parents", [])
        profile.spouse = family.get("spouse")

        # Metadata
        profile.meta["income_sources_count"] = len(
            set(
                record.income_id.split("|")[1]
                for record in profile.income_records
                if "|" in record.income_id
            )
        )
        profile.meta["controlled_organizations_count"] = (
            len(profile.organizations_director) + len(profile.organizations_founder)
        )

        return profile

    # ========================================================================
    # Organization profiles
    # ========================================================================

    def get_organization_profile(self, edrpou: str) -> OrganizationProfile | None:
        """
        Build comprehensive organization profile.
        WHY: Corporate due diligence requires understanding ownership and control.
        """
        # Fetch organization entity
        org = self.read_repo.get_organization_by_edrpou(edrpou)
        if org is None:
            return None

        # Build profile with all related data
        profile = OrganizationProfile(organization=org)

        # People connected to organization
        profile.directors = self.traversal_repo.get_directors_for_organization(edrpou)
        founders_data = self.traversal_repo.get_founders_for_organization(edrpou)
        profile.founders = [f["person"] for f in founders_data]

        # Financial activity (count employees who received income)
        # This would require a repository method to query income payments
        # For now, leave at defaults
        profile.employee_count = 0  # TODO: implement if needed

        # Metadata
        profile.meta["founder_count"] = len(profile.founders)
        profile.meta["director_count"] = len(profile.directors)
        profile.meta["total_founder_capital"] = sum(
            f["capital"] for f in founders_data if f["capital"] is not None
        )

        return profile

    # ========================================================================
    # Family wealth aggregation
    # ========================================================================

    def get_family_wealth_aggregate(
        self,
        rnokpp: str,
        family_depth: int = 2,
    ) -> FamilyWealthAggregate | None:
        """
        Aggregate wealth across family network.
        WHY: AML analysis - hidden wealth through family members.
        """
        # Fetch primary person
        person = self.read_repo.get_person_by_rnokpp(rnokpp)
        if person is None:
            return None

        # Get family network
        family = self.traversal_repo.get_family_network(rnokpp, depth=family_depth)
        family_members = (
            family.get("children", [])
            + family.get("parents", [])
            + family.get("extended", [])
        )
        if family.get("spouse"):
            family_members.append(family["spouse"])

        # Initialize aggregate
        aggregate = FamilyWealthAggregate(
            primary_person=person,
            family_members=family_members,
        )

        # Collect properties from all family members
        all_rnokpps = [person.rnokpp] + [fm.rnokpp for fm in family_members]
        for family_rnokpp in all_rnokpps:
            properties = self.read_repo.get_properties_owned_by_person(family_rnokpp)
            aggregate.properties.extend(properties)

        aggregate.total_properties = len(aggregate.properties)

        # Collect total family income
        total_income = 0.0
        for family_rnokpp in all_rnokpps:
            total_income += self.read_repo.get_total_income_for_person(family_rnokpp)

        aggregate.total_family_income = total_income

        # Collect controlled organizations
        for family_rnokpp in all_rnokpps:
            org_data = self.traversal_repo.get_organizations_controlled_by_person(family_rnokpp)
            aggregate.controlled_organizations.extend(org_data.get("director_of", []))
            aggregate.controlled_organizations.extend(org_data.get("founder_of", []))

        # Deduplicate organizations
        seen_edrpous = set()
        unique_orgs = []
        for org in aggregate.controlled_organizations:
            if org.edrpou not in seen_edrpous:
                seen_edrpous.add(org.edrpou)
                unique_orgs.append(org)
        aggregate.controlled_organizations = unique_orgs

        return aggregate
