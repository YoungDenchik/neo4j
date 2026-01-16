import json
import os

from domain.enums import NodeLabel, RelType
from repositories.ingest_repo import GraphRepository


class IngestionPipeline:

    def __init__(self, normalized_dir, repo=None):
        self.normalized_dir = normalized_dir
        self.repo = repo or GraphRepository()

    def _iter_files(self):
        for root, dirs, files in os.walk(self.normalized_dir):
            for name in files:
                if name.lower().endswith(".json"):
                    yield os.path.join(root, name)

    @staticmethod
    def _load_json(path):
        try:
            with open(path, "r", encoding="utf-8") as f:
                data = json.load(f)
            return data if isinstance(data, dict) else None
        except Exception as e:
            print(f"Failed to load JSON from {path}: {e}")
            return None

    def _merge_entity(self, label, data):
        id_key = GraphRepository.ID_KEYS.get(label)
        if not id_key:
            return
        id_value = data.get(id_key)
        if not id_value:
            return
        key_props = {id_key: id_value}
        self.repo.merge_node(label=label, key_props=key_props, set_props=data)

    def _persist_entities(self, data):
        entity_mapping = {
            "persons": NodeLabel.PERSON,
            "person_aliases": NodeLabel.PERSON_ALIAS,
            "organizations": NodeLabel.ORGANIZATION,
            "executors": NodeLabel.EXECUTOR,
            "requests": NodeLabel.REQUEST,
            "income_records": NodeLabel.INCOME_RECORD,
            "properties": NodeLabel.PROPERTY,
            "power_of_attorney": NodeLabel.POWER_OF_ATTORNEY,
            "notarial_blanks": NodeLabel.NOTARIAL_BLANK,
            "documents": NodeLabel.DOCUMENT,
        }
        for list_key, label in entity_mapping.items():
            items = data.get(list_key) or []
            if not isinstance(items, list):
                continue
            for obj in items:
                if not isinstance(obj, dict):
                    continue
                try:
                    self._merge_entity(label, obj)
                except Exception as e:
                    print(f"Failed to merge {label.value} entity: {e}")
                    continue

    def _persist_relationships(self, data):
        relationships = data.get("relationships")
        if not isinstance(relationships, dict):
            return
        for rel_type_key, rel_list in relationships.items():
            if not isinstance(rel_list, list):
                continue
            try:
                rel_enum = RelType[rel_type_key.upper()]
            except KeyError:
                print(f"Unknown relationship type: {rel_type_key}")
                continue
            if rel_enum is RelType.PROVIDED:
                for rel in rel_list:
                    if not isinstance(rel, dict):
                        continue
                    request_id = rel.get("request_id")
                    node_label_name = rel.get("node_label")
                    node_id = rel.get("node_id")
                    if not (request_id and node_label_name and node_id):
                        continue
                    try:
                        node_label = NodeLabel(node_label_name)
                    except KeyError:
                        print(f"Unknown node label: {node_label_name}")
                        continue
                    try:
                        self.repo.link_request_provided(
                            request_id=request_id,
                            provided_label=node_label,
                            provided_id_value=node_id,
                        )
                    except Exception as e:
                        print(f"Failed to link request {request_id} to {node_label.value}: {e}")
                        continue
                continue
            for rel in rel_list:
                if not isinstance(rel, dict):
                    continue
                try:
                    if rel_enum is RelType.DIRECTOR_OF:
                        person = rel.get("person_rnokpp")
                        org = rel.get("org_edrpou")
                        if person and org:
                            props = {}
                            if rel.get("role_text"):
                                props["role_text"] = rel.get("role_text")
                            self.repo.merge_relationship(
                                from_label=NodeLabel.PERSON,
                                from_id_value=person,
                                rel_type=rel_enum,
                                to_label=NodeLabel.ORGANIZATION,
                                to_id_value=org,
                                rel_props=props or None,
                            )
                    elif rel_enum is RelType.FOUNDER_OF:
                        person = rel.get("person_rnokpp")
                        org = rel.get("org_edrpou")
                        if person and org:
                            props = {}
                            if rel.get("capital") is not None:
                                props["capital"] = rel.get("capital")
                            if rel.get("role_text"):
                                props["role_text"] = rel.get("role_text")
                            self.repo.merge_relationship(
                                from_label=NodeLabel.PERSON,
                                from_id_value=person,
                                rel_type=rel_enum,
                                to_label=NodeLabel.ORGANIZATION,
                                to_id_value=org,
                                rel_props=props or None,
                            )
                    elif rel_enum is RelType.CHILD_OF:
                        child = rel.get("child_rnokpp")
                        parent = rel.get("parent_rnokpp")
                        if child and parent:
                            self.repo.merge_relationship(
                                from_label=NodeLabel.PERSON,
                                from_id_value=child,
                                rel_type=rel_enum,
                                to_label=NodeLabel.PERSON,
                                to_id_value=parent,
                                rel_props=None,
                            )
                    elif rel_enum is RelType.SPOUSE_OF:
                        p1 = rel.get("person1_rnokpp")
                        p2 = rel.get("person2_rnokpp")
                        if p1 and p2:
                            props = {}
                            if rel.get("marriage_date"):
                                props["marriage_date"] = rel.get("marriage_date")
                            self.repo.merge_relationship(
                                from_label=NodeLabel.PERSON,
                                from_id_value=p1,
                                rel_type=rel_enum,
                                to_label=NodeLabel.PERSON,
                                to_id_value=p2,
                                rel_props=props or None,
                            )
                    elif rel_enum is RelType.EARNED_INCOME:
                        person = rel.get("person_rnokpp")
                        income = rel.get("income_id")
                        if person and income:
                            self.repo.merge_relationship(
                                from_label=NodeLabel.PERSON,
                                from_id_value=person,
                                rel_type=rel_enum,
                                to_label=NodeLabel.INCOME_RECORD,
                                to_id_value=income,
                                rel_props=None,
                            )
                    elif rel_enum is RelType.PAID_BY:
                        income = rel.get("income_id")
                        org = rel.get("org_edrpou")
                        if income and org:
                            self.repo.merge_relationship(
                                from_label=NodeLabel.INCOME_RECORD,
                                from_id_value=income,
                                rel_type=rel_enum,
                                to_label=NodeLabel.ORGANIZATION,
                                to_id_value=org,
                                rel_props=None,
                            )
                    elif rel_enum is RelType.OWNS:
                        person = rel.get("person_rnokpp")
                        prop_id = rel.get("property_id")
                        if person and prop_id:
                            props = {}
                            if rel.get("ownership_type"):
                                props["ownership_type"] = rel.get("ownership_type")
                            if rel.get("since_date"):
                                props["since_date"] = rel.get("since_date")
                            self.repo.merge_relationship(
                                from_label=NodeLabel.PERSON,
                                from_id_value=person,
                                rel_type=rel_enum,
                                to_label=NodeLabel.PROPERTY,
                                to_id_value=prop_id,
                                rel_props=props or None,
                            )
                    elif rel_enum is RelType.HAS_GRANTOR:
                        poa = rel.get("poa_id")
                        grantor = rel.get("grantor_rnokpp")
                        if poa and grantor:
                            self.repo.merge_relationship(
                                from_label=NodeLabel.POWER_OF_ATTORNEY,
                                from_id_value=poa,
                                rel_type=rel_enum,
                                to_label=NodeLabel.PERSON,
                                to_id_value=grantor,
                                rel_props=None,
                            )
                    elif rel_enum is RelType.HAS_REPRESENTATIVE:
                        poa = rel.get("poa_id")
                        rep = rel.get("representative_rnokpp")
                        if poa and rep:
                            self.repo.merge_relationship(
                                from_label=NodeLabel.POWER_OF_ATTORNEY,
                                from_id_value=poa,
                                rel_type=rel_enum,
                                to_label=NodeLabel.PERSON,
                                to_id_value=rep,
                                rel_props=None,
                            )
                    elif rel_enum is RelType.HAS_PROPERTY:
                        poa = rel.get("poa_id")
                        prop_id = rel.get("property_id")
                        if poa and prop_id:
                            self.repo.merge_relationship(
                                from_label=NodeLabel.POWER_OF_ATTORNEY,
                                from_id_value=poa,
                                rel_type=rel_enum,
                                to_label=NodeLabel.PROPERTY,
                                to_id_value=prop_id,
                                rel_props=None,
                            )
                    elif rel_enum is RelType.HAS_NOTARIAL_BLANK:
                        poa = rel.get("poa_id")
                        blank = rel.get("blank_id")
                        if poa and blank:
                            self.repo.merge_relationship(
                                from_label=NodeLabel.POWER_OF_ATTORNEY,
                                from_id_value=poa,
                                rel_type=rel_enum,
                                to_label=NodeLabel.NOTARIAL_BLANK,
                                to_id_value=blank,
                                rel_props=None,
                            )
                    elif rel_enum is RelType.CREATED_BY:
                        request = rel.get("request_id")
                        executor = rel.get("executor_rnokpp")
                        if request and executor:
                            self.repo.merge_relationship(
                                from_label=NodeLabel.REQUEST,
                                from_id_value=request,
                                rel_type=rel_enum,
                                to_label=NodeLabel.EXECUTOR,
                                to_id_value=executor,
                                rel_props=None,
                            )
                    elif rel_enum is RelType.ABOUT:
                        request = rel.get("request_id")
                        subject = rel.get("subject_rnokpp")
                        if request and subject:
                            self.repo.merge_relationship(
                                from_label=NodeLabel.REQUEST,
                                from_id_value=request,
                                rel_type=rel_enum,
                                to_label=NodeLabel.PERSON,
                                to_id_value=subject,
                                rel_props=None,
                            )
                except Exception as e:
                    print(f"Failed to create {rel_enum.value} relationship: {e}")
                    continue

    def run(self):
        try:
            self.repo.ensure_constraints()
        except Exception as e:
            print(f"Failed to ensure constraints (may already exist): {e}")

        for file_path in self._iter_files():
            print(f"[INFO] Processing normalized file: {file_path}")
            record = self._load_json(file_path)
            if not record:
                print(f"[WARN] Skipping {file_path}: no valid JSON object")
                continue
            self._persist_entities(record)
            self._persist_relationships(record)
