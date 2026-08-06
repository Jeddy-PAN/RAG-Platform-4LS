"""Conservative generic evidence-facet planning for Round 4B.

The planner receives only the current user question and never retrieved chunks,
source text, search text, conversation secrets, or stored credentials. A false
split negative is always preferred over a false positive split.
"""

import re

from app.rag.providers.query_planner import PlannerProviderError
from app.rag.providers.types import QueryFacetPlannerProvider
from app.rag.retrieval.evidence_types import (
    EvidenceFacet,
    EvidenceQueryPlan,
    QueryEntity,
    MAX_EVIDENCE_FACETS,
)
from app.rag.retrieval.lexical import tokenize
from app.rag.retrieval.query_facets import plan_table_query

_MAX_QUESTION_LENGTH = 2000

# Word conjunctions that may separate independent clauses.
_CLAUSE_CONJUNCTION = re.compile(r"\s+(?:and|also)\s+|以及|并且|同时")

# Any generic compound/conjunction signal worth structured planning latency.
_COMPOUND_SIGNAL = re.compile(r"\s+(?:and|also)\s+|以及|并且|同时|和|、|,|，")


def _has_compound_signal(question: str) -> bool:
    if re.search(r"以及|并且|同时|和|、|,|，", question):
        return True
    for match in re.finditer(r"\s+(?:and|also)\s+", question):
        left = question[: match.start()].split()[-1:]
        right = question[match.end() :].split()[:1]
        if left and right and left[0][:1].isupper() and right[0][:1].isupper():
            continue
        return True
    return False

# Attribute list joined by conjunctions followed by an entity: "a and b for e".
_ATTRIBUTE_FOR_ENTITY = re.compile(
    r"(?P<attrs>[a-z㐀-鿿]+(?:\s+(?:and|以及|和)\s+[a-z㐀-鿿]+)+)"
    r"\s+(?:for|of|为)\s+(?P<entity>[^\s.,;!?，。；！]+)"
)

_ENTITY_STOPWORDS = {"the", "a", "an", "of", "for", "this", "that"}
_ATTRIBUTE_START_FUNCTION_WORDS = {
    "a",
    "an",
    "find",
    "get",
    "give",
    "list",
    "show",
    "the",
    "what",
    "which",
}


def _normalize_entity(text: str) -> str:
    return re.sub(r"[^a-z0-9㐀-鿿]+", "", text.casefold())


def _looks_like_entity(text: str) -> bool:
    """Identifier-like or CJK entity span, never a bare article."""

    if not text or text.casefold() in _ENTITY_STOPWORDS:
        return False
    return any(ch.isdigit() for ch in text) or any("㐀" <= ch <= "鿿" for ch in text)


def _clause_grounded(clause: str) -> bool:
    """A clause is independently grounded when it contains an identifier."""

    return bool(tokenize(clause).identifier_terms)


def _single_plan(
    question: str,
    fallback_reason: str | None = None,
) -> EvidenceQueryPlan:
    return EvidenceQueryPlan(
        original_query=question,
        facets=(EvidenceFacet(index=0, query=question),),
        route="fallback" if fallback_reason else "single",
        confidence=0.0 if fallback_reason else 0.1,
        fallback_reason=fallback_reason,
    )


def _plan_attribute_conjunction(
    question: str,
    max_facets: int,
) -> EvidenceQueryPlan | None:
    """Handle one entity with several requested attributes (lowercase/CJK only)."""

    match = _ATTRIBUTE_FOR_ENTITY.search(question)
    if match is None:
        return None
    # ``search`` can otherwise begin at the suffix of an ambiguous noun
    # phrase (``user name`` -> ``name``).  Only accept an ASCII attribute list
    # when its left boundary is a grammatical query boundary; an unknown
    # preceding noun means completeness cannot be established generically.
    if match.group("attrs")[0].isascii():
        prefix = question[: match.start("attrs")]
        preceding_words = re.findall(r"[a-z]+", prefix.casefold())
        if preceding_words and preceding_words[-1] not in _ATTRIBUTE_START_FUNCTION_WORDS:
            return None
    attrs = [
        part.strip()
        for part in re.split(r"\s+(?:and|以及|和)\s+", match.group("attrs"))
    ]
    entity = match.group("entity")
    if not 2 <= len(attrs) <= max_facets:
        return None
    if not _looks_like_entity(entity):
        return None
    normalized = _normalize_entity(entity)
    facets = tuple(
        EvidenceFacet(
            index=index,
            query=f"{attr} {entity}",
            entities=(QueryEntity(text=entity, normalized=normalized),),
            attributes=(attr,),
        )
        for index, attr in enumerate(attrs)
    )
    return EvidenceQueryPlan(
        original_query=question,
        facets=facets,
        route="deterministic",
        confidence=0.6,
    )


def _plan_independent_clauses(
    question: str,
    max_facets: int,
) -> EvidenceQueryPlan | None:
    """Handle clearly independent grounded clauses in original order."""

    clauses = [clause.strip() for clause in _CLAUSE_CONJUNCTION.split(question)]
    clauses = [clause for clause in clauses if clause]
    if not 2 <= len(clauses) <= max_facets:
        return None
    if not all(_clause_grounded(clause) for clause in clauses):
        return None
    facets = tuple(
        EvidenceFacet(index=index, query=clause)
        for index, clause in enumerate(clauses)
    )
    return EvidenceQueryPlan(
        original_query=question,
        facets=facets,
        route="deterministic",
        confidence=0.6,
    )


def _plan_deterministic(
    question: str,
    max_facets: int,
) -> EvidenceQueryPlan | None:
    plan = _plan_attribute_conjunction(question, max_facets)
    if plan is not None:
        return plan
    return _plan_independent_clauses(question, max_facets)


def plan_evidence_facets(
    question: str,
    planner_provider: QueryFacetPlannerProvider | None = None,
    max_facets: int = MAX_EVIDENCE_FACETS,
) -> EvidenceQueryPlan:
    """Plan generic evidence facets conservatively.

    The Round 4A full-table route takes precedence: a compound full-table
    question never becomes generic evidence facets and never calls the
    structured provider. A deterministic fast path handles clear cases;
    otherwise the injectable provider is tried; any failure falls back to one
    facet containing the original question.
    """
    if not question or not question.strip():
        return _single_plan(question, "empty_question")
    if len(question) > _MAX_QUESTION_LENGTH:
        return _single_plan(question, "oversized_question")
    if plan_table_query(question).is_compound:
        return _single_plan(question, "full_table_route")

    deterministic = _plan_deterministic(question, max_facets)
    if deterministic is not None:
        return deterministic
    # A clear single-fact question never pays structured-planning latency.
    if not _has_compound_signal(question):
        return _single_plan(question)
    if planner_provider is None:
        return _single_plan(question, "planner_unavailable")
    try:
        return planner_provider.plan(question, max_facets=max_facets)
    except PlannerProviderError as exc:
        return _single_plan(question, exc.reason_code)
    except Exception:
        return _single_plan(question, "planner_error")
