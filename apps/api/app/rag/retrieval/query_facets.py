"""Conservative decomposition of compound full-table requests."""

import re

from app.rag.retrieval.table_expansion import detect_table_intent
from app.rag.retrieval.types import TableQueryFacet, TableQueryPlan


_CONNECTOR = re.compile(
    r"\s+(?:and|also)\s+|(?:以及|并且|同时|和)",
    flags=re.IGNORECASE,
)


def _single_plan(query: str) -> TableQueryPlan:
    return TableQueryPlan(
        original_query=query,
        facets=[TableQueryFacet(index=0, query=query)],
        is_compound=False,
    )


def plan_table_query(query: str, max_facets: int = 4) -> TableQueryPlan:
    normalized = query.strip()
    if not normalized or max_facets < 2:
        return _single_plan(normalized)

    clauses = [clause.strip(" ,;，；") for clause in _CONNECTOR.split(normalized)]
    clauses = [clause for clause in clauses if clause]
    if not 2 <= len(clauses) <= max_facets:
        return _single_plan(normalized)
    if not all(detect_table_intent(clause)[1] for clause in clauses):
        return _single_plan(normalized)

    return TableQueryPlan(
        original_query=normalized,
        facets=[
            TableQueryFacet(index=index, query=clause)
            for index, clause in enumerate(clauses)
        ],
        is_compound=True,
    )
