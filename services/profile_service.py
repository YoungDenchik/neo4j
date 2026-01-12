from __future__ import annotations

from repositories.read_repo import ReadRepository
from repositories.traversal_repo import TraversalRepository
from domain.models import PersonProfile


class ProfileService:
    def __init__(self, read_repo: ReadRepository, traversal_repo: TraversalRepository):
        self.read_repo = read_repo
        self.traversal_repo = traversal_repo

    def get_person_profile(self, person_id: str) -> PersonProfile | None:
        profile = self.read_repo.load_person_profile(person_id)
        if profile is None:
            return None

        # attach indirect assets via companies
        profile.assets_indirect = self.traversal_repo.find_indirect_assets_via_companies(person_id)
        return profile
