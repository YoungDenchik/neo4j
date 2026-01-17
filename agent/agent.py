# from __future__ import annotations

# from dataclasses import dataclass, field
# from typing import Any, Dict, List, Optional, TypedDict

# from langgraph.graph import StateGraph, END

# from agent.schema import GraphFactsPayload
# from agent.validator import validate
# from agent.canonicalizer import normalize
# from agent.extractor import call_llm_extract
# from agent.fixer import call_llm_fix
# from agent.writer import persist_to_neo4j
# from agent.safe_json import safe_parse_raw_input, RawJsonParseError

# from repositories.ingest_repo import GraphRepository


# class IngestionState(TypedDict, total=False):
#     # input
#     raw_input: Any
#     raw_json: Dict[str, Any]

#     # extracted
#     facts: GraphFactsPayload
#     errors: List[str]

#     # control
#     fix_attempts: int
#     max_fix_attempts: int

#     # output status
#     persisted: bool
#     fatal_error: Optional[str]


# @dataclass
# class LangGraphIngestionAgent:
#     repo: GraphRepository
#     app: Any = field(init=False)

#     def __post_init__(self) -> None:
#         self.app = self._build_graph()

#     def _build_graph(self):
#         g = StateGraph(IngestionState)

#         # -----------------------------
#         # Nodes
#         # -----------------------------
#         def parse_input_node(state: IngestionState) -> IngestionState:
#             raw_input = state["raw_input"]

#             try:
#                 parsed = safe_parse_raw_input(raw_input)
#             except RawJsonParseError as e:
#                 return {**state, "fatal_error": f"Invalid input JSON: {e}"}

#             if not isinstance(parsed, dict):
#                 return {**state, "fatal_error": f"Expected dict record, got {type(parsed)}"}

#             return {**state, "raw_json": parsed}

#         def extract_node(state: IngestionState) -> IngestionState:
#             if state.get("fatal_error"):
#                 return state

#             raw_json = state["raw_json"]
#             facts = call_llm_extract(raw_json, GraphFactsPayload, features={})
#             return {**state, "facts": facts}

#         def normalize_node(state: IngestionState) -> IngestionState:
#             if state.get("fatal_error"):
#                 return state

#             facts = state["facts"]
#             facts = normalize(facts)
#             return {**state, "facts": facts}

#         def validate_node(state: IngestionState) -> IngestionState:
#             if state.get("fatal_error"):
#                 return state

#             facts = state["facts"]
#             errors = validate(facts)
#             return {**state, "errors": errors}

#         def fix_node(state: IngestionState) -> IngestionState:
#             if state.get("fatal_error"):
#                 return state

#             facts = state["facts"]
#             errors = state.get("errors", [])

#             fix_attempts = state.get("fix_attempts", 0) + 1
#             max_fix_attempts = state.get("max_fix_attempts", 2)

#             # IMPORTANT: no raise here → just stop gracefully
#             if fix_attempts > max_fix_attempts:
#                 return {
#                     **state,
#                     "fatal_error": f"Exceeded max_fix_attempts={max_fix_attempts}. Last errors={errors}",
#                 }

#             fixed = call_llm_fix(facts, errors)
#             fixed = normalize(fixed)

#             return {
#                 **state,
#                 "facts": fixed,
#                 "fix_attempts": fix_attempts,
#             }

#         def persist_node(state: IngestionState) -> IngestionState:
#             if state.get("fatal_error"):
#                 return state

#             facts = state["facts"]
#             persist_to_neo4j(facts, self.repo)
#             return {**state, "persisted": True}

#         # -----------------------------
#         # Conditional routing
#         # -----------------------------
#         def decide_after_parse(state: IngestionState) -> str:
#             if state.get("fatal_error"):
#                 return "end"
#             return "extract"

#         def decide_after_validate(state: IngestionState) -> str:
#             if state.get("fatal_error"):
#                 return "end"

#             errors = state.get("errors", [])
#             if errors:
#                 return "fix"
#             return "persist"

#         # -----------------------------
#         # Graph edges
#         # -----------------------------
#         g.add_node("parse", parse_input_node)
#         g.add_node("extract", extract_node)
#         g.add_node("normalize", normalize_node)
#         g.add_node("validate", validate_node)
#         g.add_node("fix", fix_node)
#         g.add_node("persist", persist_node)

#         g.set_entry_point("parse")

#         g.add_conditional_edges(
#             "parse",
#             decide_after_parse,
#             {
#                 "extract": "extract",
#                 "end": END,
#             },
#         )

#         g.add_edge("extract", "normalize")
#         g.add_edge("normalize", "validate")

#         g.add_conditional_edges(
#             "validate",
#             decide_after_validate,
#             {
#                 "fix": "fix",
#                 "persist": "persist",
#                 "end": END,
#             },
#         )

#         g.add_edge("fix", "validate")
#         g.add_edge("persist", END)

#         return g.compile()

#     def run(self, raw_input: Any, max_fix_attempts: int = 2) -> GraphFactsPayload:
#         final_state: IngestionState = self.app.invoke(
#             {
#                 "raw_input": raw_input,
#                 "fix_attempts": 0,
#                 "max_fix_attempts": max_fix_attempts,
#                 "persisted": False,
#                 "fatal_error": None,
#             }
#         )

#         if final_state.get("fatal_error"):
#             raise ValueError(final_state["fatal_error"])

#         errors = final_state.get("errors", [])
#         if errors:
#             raise ValueError(f"Ingestion finished with errors: {errors}")

#         if not final_state.get("persisted"):
#             raise ValueError("Ingestion finished but data was not persisted (unknown reason)")

#         return final_state["facts"]


from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, TypedDict, Callable

import logging

from langgraph.graph import StateGraph, END

from agent.schema import GraphFactsPayload
from agent.validator import validate
from agent.canonicalizer import normalize
from agent.extractor import call_llm_extract
from agent.fixer import call_llm_fix
from agent.writer import persist_to_neo4j
from agent.safe_json import safe_parse_raw_input, RawJsonParseError

from repositories.ingest_repo import GraphRepository

logger = logging.getLogger(__name__)


class IngestionState(TypedDict, total=False):
    # input
    raw_input: Any
    raw_json: Dict[str, Any]

    # extracted
    facts: GraphFactsPayload
    errors: List[str]

    # control
    fix_attempts: int
    max_fix_attempts: int

    # output status
    persisted: bool
    fatal_error: Optional[str]


def _set_fatal(state: IngestionState, msg: str) -> IngestionState:
    return {**state, "fatal_error": msg}


def _safe_node(fn: Callable[[IngestionState], IngestionState]) -> Callable[[IngestionState], IngestionState]:
    """
    Wrap node execution to prevent hard crashes.
    Any unhandled exception becomes fatal_error.
    """
    def wrapped(state: IngestionState) -> IngestionState:
        if state.get("fatal_error"):
            return state
        try:
            return fn(state)
        except Exception as e:
            logger.exception("Node failed: %s", fn.__name__)
            return _set_fatal(state, f"{fn.__name__} failed: {e}")
    return wrapped


@dataclass
class LangGraphIngestionAgent:
    repo: GraphRepository
    features: Dict[str, Any] = field(default_factory=dict)
    app: Any = field(init=False)

    def __post_init__(self) -> None:
        self.app = self._build_graph()

    def _build_graph(self):
        g = StateGraph(IngestionState)

        # -----------------------------
        # Nodes
        # -----------------------------
        @_safe_node
        def parse_input_node(state: IngestionState) -> IngestionState:
            raw_input = state.get("raw_input")
            if raw_input is None:
                return _set_fatal(state, "raw_input is None")

            try:
                parsed = safe_parse_raw_input(raw_input)
            except RawJsonParseError as e:
                return _set_fatal(state, f"Invalid input JSON: {e}")

            if not isinstance(parsed, dict):
                return _set_fatal(state, f"Expected dict record, got {type(parsed)}")
            
            print("1")
            print(state)

            return {**state, "raw_json": parsed}

        @_safe_node
        def extract_node(state: IngestionState) -> IngestionState:
            raw_json = state["raw_json"]

            # LLM extraction
            extracted = call_llm_extract(raw_json, GraphFactsPayload, features=self.features)

            # Guard: ensure Pydantic model instance
            if isinstance(extracted, GraphFactsPayload):
                facts = extracted
            else:
                # If extractor returns dict-like, validate it here
                facts = GraphFactsPayload.model_validate(extracted)

            print("2")
            print(state)
            return {**state, "facts": facts}

        @_safe_node
        def normalize_node(state: IngestionState) -> IngestionState:
            facts = state["facts"]
            facts = normalize(facts)

            print("3")
            print(state)
            return {**state, "facts": facts}

        @_safe_node
        def validate_node(state: IngestionState) -> IngestionState:
            facts = state["facts"]
            errors = validate(facts) or []
            # ensure list[str]
            errors = [str(e) for e in errors]
            print("4")
            print(state)
            return {**state, "errors": errors}

        @_safe_node
        def fix_node(state: IngestionState) -> IngestionState:
            facts = state["facts"]
            errors = state.get("errors", [])

            fix_attempts = int(state.get("fix_attempts", 0)) + 1
            max_fix_attempts = int(state.get("max_fix_attempts", 2))

            if fix_attempts > max_fix_attempts:
                return _set_fatal(
                    {**state, "fix_attempts": fix_attempts},
                    f"Exceeded max_fix_attempts={max_fix_attempts}. Last errors={errors}",
                )

            fixed = call_llm_fix(facts, errors)

            # Guard: ensure Pydantic model instance
            if isinstance(fixed, GraphFactsPayload):
                fixed_facts = fixed
            else:
                fixed_facts = GraphFactsPayload.model_validate(fixed)

            print("5")
            print(state)
            # IMPORTANT: we do not validate here; pipeline will normalize -> validate after this node
            return {
                **state,
                "facts": fixed_facts,
                "fix_attempts": fix_attempts,
                # optional: clear old errors to avoid confusion in state
                "errors": [],
            }

        @_safe_node
        def persist_node(state: IngestionState) -> IngestionState:
            facts = state["facts"]

            # Persist should never crash the graph; convert to fatal_error
            try:
                persist_to_neo4j(facts, self.repo)
            except Exception as e:
                logger.exception("Persist failed")
                return _set_fatal(state, f"Persist failed: {e}")
            
            print("6")
            print(state)
            return {**state, "persisted": True}

        # -----------------------------
        # Conditional routing
        # -----------------------------
        def decide_after_parse(state: IngestionState) -> str:
            return "end" if state.get("fatal_error") else "extract"

        def decide_after_validate(state: IngestionState) -> str:
            if state.get("fatal_error"):
                return "end"
            errors = state.get("errors", [])
            return "fix" if errors else "persist"

        # -----------------------------
        # Graph edges
        # -----------------------------
        g.add_node("parse", parse_input_node)
        g.add_node("extract", extract_node)
        g.add_node("normalize", normalize_node)
        g.add_node("validate", validate_node)
        g.add_node("fix", fix_node)
        g.add_node("persist", persist_node)

        g.set_entry_point("parse")

        g.add_conditional_edges(
            "parse",
            decide_after_parse,
            {"extract": "extract", "end": END},
        )

        g.add_edge("extract", "normalize")
        g.add_edge("normalize", "validate")

        g.add_conditional_edges(
            "validate",
            decide_after_validate,
            {"fix": "fix", "persist": "persist", "end": END},
        )

        # ✅ CRITICAL FIX:
        # After fix you must normalize again before validate
        g.add_edge("fix", "normalize")

        g.add_edge("persist", END)

        return g.compile()

    def run(self, raw_input: Any, max_fix_attempts: int = 2) -> GraphFactsPayload:
        final_state: IngestionState = self.app.invoke(
            {
                "raw_input": raw_input,
                "fix_attempts": 0,
                "max_fix_attempts": max_fix_attempts,
                "persisted": False,
                "fatal_error": None,
                "errors": [],
            }
        )

        fatal = final_state.get("fatal_error")
        if fatal:
            raise ValueError(fatal)

        errors = final_state.get("errors", [])
        if errors:
            raise ValueError(f"Ingestion finished with errors: {errors}")

        if not final_state.get("persisted"):
            raise ValueError("Ingestion finished but data was not persisted (unknown reason)")

        return final_state["facts"]
