"""Small deterministic grounded-provider responses for local tests."""

import json
import re


def grounded_content(messages, text: str | None = None) -> str:
    system = next((item["content"] for item in messages if item.get("role") == "system"), "")
    blocks = re.findall(r"\[Source (\d+)\].*?content: (.*?)(?=\n\[Source \d+\]|\Z)", system, re.S)
    sources = {int(number): content.strip() for number, content in blocks if content.strip()}
    policies = re.findall(r"Facet (\d+) may cite only source numbers: ([0-9, ]+)", system)
    if not policies:
        policies = [("0", ", ".join(str(number) for number in sources))]
    claims = []
    for facet, raw_numbers in policies:
        numbers = [int(value) for value in raw_numbers.split(",") if value.strip()]
        if not numbers:
            continue
        source_number = next((number for number in numbers if number in sources), None)
        if source_number is None:
            continue
        quote = sources[source_number][:500]
        claims.append({
            "claim_index": len(claims) + 1,
            "facet_index": int(facet),
            "text": text or quote,
            "conflict_group_index": None,
            "citations": [{"source_number": source_number, "quote": quote}],
        })
    return json.dumps({"version": "grounded-answer-v1", "claims": claims}, ensure_ascii=False)
