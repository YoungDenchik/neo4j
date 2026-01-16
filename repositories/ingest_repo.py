from __future__ import annotations

from dataclasses import asdict, is_dataclass
from typing import Any, Dict, Optional, Iterable, Tuple

from neo4j import Driver

from core.neo4j_driver import get_driver, get_db_name
from domain.enums import NodeLabel, RelType


class GraphRepository:
    """
    Universal Neo4j mutation repository.

    RESPONSIBILITIES:
    - Ensure database constraints (unique constraints + indexes)
    - Merge nodes (upsert) by stable identity keys
    - Merge relationships between nodes
    - Optionally set relationship properties
    - Keep schema governance via NodeLabel / RelType enums

    NOTE:
    This repo contains NO business logic, NO analytics, NO complex reads.
    Only graph mutations (writes).
    """

    # ---------------------------------------------------------------------
    # Node identity keys
    # ---------------------------------------------------------------------
    # Each node label must have exactly 1 stable id key for MERGE.
    ID_KEYS: Dict[NodeLabel, str] = {
        NodeLabel.PERSON: "rnokpp",
        NodeLabel.PERSON_ALIAS: "alias_id",
        NodeLabel.ORGANIZATION: "edrpou",
        NodeLabel.KVED_ACTIVITY: "code",
        NodeLabel.REQUEST: "request_id",
        NodeLabel.EXECUTOR: "executor_id",
        NodeLabel.INCOME_RECORD: "income_id",
        NodeLabel.PROPERTY: "property_id",
        NodeLabel.LAND_PARCEL: "land_id",
        NodeLabel.POWER_OF_ATTORNEY: "poa_id",
        NodeLabel.NOTARIAL_BLANK: "blank_id",
        NodeLabel.ADDRESS: "address_id",
        NodeLabel.DOCUMENT: "doc_id",
        NodeLabel.COURT_CASE: "case_id",
        NodeLabel.BIRTH_RECORD: "record_id",
    }

    def __init__(self, driver: Driver | None = None):
        self._driver = driver or get_driver()
        self._db = get_db_name()

    # =====================================================================
    # Helpers
    # =====================================================================

    @staticmethod
    def _to_props(obj: Any) -> Dict[str, Any]:
        """
        Convert dataclass or dict to plain property dict.
        - Removes None values
        - Converts Enum -> .value
        """
        if obj is None:
            return {}

        if isinstance(obj, dict):
            raw = obj
        elif is_dataclass(obj):
            raw = asdict(obj)
        else:
            raise TypeError(f"Unsupported props type: {type(obj)}")

        clean: Dict[str, Any] = {}
        for k, v in raw.items():
            if v is None:
                continue
            # Enum support
            if hasattr(v, "value"):
                clean[k] = v.value
            else:
                clean[k] = v
        return clean

    def _id_key(self, label: NodeLabel) -> str:
        if label not in self.ID_KEYS:
            raise ValueError(f"No ID key configured for label: {label}")
        return self.ID_KEYS[label]

    # =====================================================================
    # Constraints / Indexes
    # =====================================================================

    def ensure_constraints(self) -> None:
        """
        Idempotent schema setup for Neo4j 5+.
        Creates uniqueness constraints and indexes.

        IMPORTANT:
        - uniqueness constraints protect you from duplicate nodes
        - indexes speed up queries and merges
        """

        unique_constraints = [
            (NodeLabel.PERSON, "rnokpp"),
            (NodeLabel.PERSON_ALIAS, "alias_id"),
            (NodeLabel.ORGANIZATION, "edrpou"),
            (NodeLabel.KVED_ACTIVITY, "code"),
            (NodeLabel.REQUEST, "request_id"),
            (NodeLabel.EXECUTOR, "executor_id"),
            (NodeLabel.INCOME_RECORD, "income_id"),
            (NodeLabel.PROPERTY, "property_id"),
            (NodeLabel.LAND_PARCEL, "land_id"),
            (NodeLabel.POWER_OF_ATTORNEY, "poa_id"),
            (NodeLabel.NOTARIAL_BLANK, "blank_id"),
            (NodeLabel.ADDRESS, "address_id"),
            (NodeLabel.DOCUMENT, "doc_id"),
            (NodeLabel.COURT_CASE, "case_id"),
            (NodeLabel.BIRTH_RECORD, "record_id"),
        ]

        indexes = [
            (NodeLabel.PERSON, ["last_name", "first_name"]),
            (NodeLabel.PERSON, ["date_birth"]),
            (NodeLabel.ORGANIZATION, ["name"]),
            (NodeLabel.ORGANIZATION, ["state"]),
            (NodeLabel.INCOME_RECORD, ["period_year"]),
            (NodeLabel.INCOME_RECORD, ["income_type_code"]),
            (NodeLabel.REQUEST, ["application_date"]),
        ]

        cypher_statements: list[str] = []

        # Uniqueness constraints
        for label, prop in unique_constraints:
            cypher_statements.append(
                f"""
                CREATE CONSTRAINT {label.value.lower()}_{prop}_unique IF NOT EXISTS
                FOR (n:{label.value})
                REQUIRE n.{prop} IS UNIQUE
                """
            )

        # Indexes
        for label, props in indexes:
            props_str = ", ".join([f"n.{p}" for p in props])
            idx_name = f"{label.value.lower()}_{'_'.join(props)}_idx"
            cypher_statements.append(
                f"""
                CREATE INDEX {idx_name} IF NOT EXISTS
                FOR (n:{label.value})
                ON ({props_str})
                """
            )

        def _tx(tx):
            for stmt in cypher_statements:
                tx.run(stmt)

        with self._driver.session(database=self._db) as session:
            session.execute_write(_tx)

    # =====================================================================
    # Node operations
    # =====================================================================

    def merge_node(
        self,
        label: NodeLabel,
        key_props: Dict[str, Any],
        set_props: Optional[Dict[str, Any]] = None,
    ) -> None:
        """
        MERGE node by key_props and SET set_props.

        Example:
            repo.merge_node(
                label=NodeLabel.PERSON,
                key_props={"rnokpp": "123"},
                set_props={"last_name": "Ivanov"}
            )
        """
        if not key_props:
            raise ValueError("key_props must not be empty")

        # Filter None and Enum conversions
        key_props = self._to_props(key_props)
        set_props = self._to_props(set_props or {})

        # Build SET clause dynamically
        set_clause = ""
        if set_props:
            assignments = ", ".join([f"n.{k} = ${k}" for k in set_props.keys()])
            set_clause = f"SET {assignments}"

        params: Dict[str, Any] = {**key_props, **set_props}

        # MERGE on keys only
        merge_keys = ", ".join([f"{k}: ${k}" for k in key_props.keys()])

        cypher = f"""
        MERGE (n:{label.value} {{{merge_keys}}})
        {set_clause}
        """

        def _tx(tx):
            tx.run(cypher, params)

        with self._driver.session(database=self._db) as session:
            session.execute_write(_tx)

    def merge_entity(self, label: NodeLabel, entity: Any) -> None:
        """
        Merge a dataclass entity using label's ID key.

        Example:
            repo.merge_entity(NodeLabel.PERSON, person_obj)
        """
        props = self._to_props(entity)
        id_key = self._id_key(label)

        if id_key not in props or props[id_key] is None:
            raise ValueError(f"Entity for {label.value} must contain non-null '{id_key}'")

        key_props = {id_key: props[id_key]}
        # keep all other props in SET as well (including id_key is ok)
        self.merge_node(label=label, key_props=key_props, set_props=props)

    # =====================================================================
    # Relationship operations
    # =====================================================================

    def merge_relationship(
        self,
        from_label: NodeLabel,
        from_id_value: Any,
        rel_type: RelType,
        to_label: NodeLabel,
        to_id_value: Any,
        rel_props: Optional[Dict[str, Any]] = None,
    ) -> None:
        """
        MERGE relationship between two existing nodes.

        from_label/from_id_value uniquely identifies the source node
        to_label/to_id_value uniquely identifies the target node

        rel_props are optional relationship attributes (stored on relationship).
        """

        from_id_key = self._id_key(from_label)
        to_id_key = self._id_key(to_label)

        rel_props = self._to_props(rel_props or {})

        set_clause = ""
        if rel_props:
            assignments = ", ".join([f"r.{k} = $rel_{k}" for k in rel_props.keys()])
            set_clause = f"SET {assignments}"

        params: Dict[str, Any] = {
            "from_id": from_id_value,
            "to_id": to_id_value,
            **{f"rel_{k}": v for k, v in rel_props.items()},
        }

        cypher = f"""
        MATCH (a:{from_label.value} {{{from_id_key}: $from_id}})
        MATCH (b:{to_label.value} {{{to_id_key}: $to_id}})
        MERGE (a)-[r:{rel_type.value}]->(b)
        {set_clause}
        """

        def _tx(tx):
            tx.run(cypher, params)

        with self._driver.session(database=self._db) as session:
            session.execute_write(_tx)

    # =====================================================================
    # Convenience helpers for provenance links
    # =====================================================================

    def link_request_provided(
        self,
        request_id: str,
        provided_label: NodeLabel,
        provided_id_value: Any,
    ) -> None:
        """
        Standard provenance link:
            (Request)-[:PROVIDED]->(AnyNode)

        This is extremely useful to track which request produced which data.
        """
        self.merge_relationship(
            from_label=NodeLabel.REQUEST,
            from_id_value=request_id,
            rel_type=RelType.PROVIDED,
            to_label=provided_label,
            to_id_value=provided_id_value,
        )

    # =====================================================================
    # Batch helpers (optional but convenient)
    # =====================================================================

    def merge_entities(self, items: Iterable[Tuple[NodeLabel, Any]]) -> None:
        """
        Batch merge entities sequentially (simple version).
        Later you can optimize to UNWIND for speed.
        """
        for label, entity in items:
            self.merge_entity(label, entity)

    def merge_relationships(self, items: Iterable[dict]) -> None:
        """
        Batch merge relationships sequentially.

        Expected dict format:
            {
              "from_label": NodeLabel.PERSON,
              "from_id": "123",
              "rel_type": RelType.OWNS,
              "to_label": NodeLabel.PROPERTY,
              "to_id": "prop_1",
              "rel_props": {...}
            }
        """
        for item in items:
            self.merge_relationship(
                from_label=item["from_label"],
                from_id_value=item["from_id"],
                rel_type=item["rel_type"],
                to_label=item["to_label"],
                to_id_value=item["to_id"],
                rel_props=item.get("rel_props"),
            )
