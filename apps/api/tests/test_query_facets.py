from app.rag.retrieval.query_facets import plan_table_query


def test_plans_two_chinese_full_table_facets() -> None:
    plan = plan_table_query(
        "列出 Alpha Inventory 表格中的所有 server和列出 Beta Access table 的所有行"
    )

    assert plan.is_compound is True
    assert [facet.index for facet in plan.facets] == [0, 1]
    assert [facet.query for facet in plan.facets] == [
        "列出 Alpha Inventory 表格中的所有 server",
        "列出 Beta Access table 的所有行",
    ]


def test_plans_two_english_full_table_facets() -> None:
    plan = plan_table_query(
        "list all servers in Alpha Inventory and show all rows in Beta Access table"
    )

    assert plan.is_compound is True
    assert len(plan.facets) == 2


import pytest


@pytest.mark.parametrize(
    "query",
    [
        "find the username and password for node77-east",
        "list all rows in Rock and Roll inventory",
        "列出 Alpha 表格所有行和说明维护流程",
        "server列表",
    ],
)
def test_does_not_split_without_two_independent_full_table_clauses(query: str) -> None:
    plan = plan_table_query(query)
    assert plan.is_compound is False
    assert [facet.query for facet in plan.facets] == [query]


def test_limits_compound_plan_to_four_facets() -> None:
    query = "并且".join(f"列出 Table {index} 的所有行" for index in range(5))
    plan = plan_table_query(query)
    assert plan.is_compound is False
    assert [facet.query for facet in plan.facets] == [query]
