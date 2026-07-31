"""Language-aware lexical tokenization for keyword retrieval."""

import re
from dataclasses import dataclass, field

_MIN_IDENT_CLASSIFY = 4
_MIN_IDENT_NGRAM = 5
_MIN_IDENT_CONTAIN = 5
_NGRAM_SIZE = 3
_MIN_NGRAM_OVERLAP = 0.5
_MIN_CONTAINMENT_RATIO = 0.4
_MAX_GENERAL_TERM_SCORE = 4.0

_PROV_WHOLE = "whole"
_PROV_NORMALIZED = "normalized"
_PROV_DERIVED = "derived"
_EXACT_PROVS = {_PROV_WHOLE, _PROV_NORMALIZED}
# Containment is only evaluated between whole/normalized identifiers
_CONTAIN_PROVS = {_PROV_WHOLE, _PROV_NORMALIZED}


@dataclass
class LexicalTerms:
    ascii_terms: list[str] = field(default_factory=list)
    identifier_terms: list[str] = field(default_factory=list)
    cjk_terms: list[str] = field(default_factory=list)
    identifier_ngrams: dict[str, set[str]] = field(default_factory=dict)
    # id_records[i] corresponds to identifier_terms[i]:
    # (surface, source_group_id, provenance_tag)
    id_records: list[tuple[str, int, str]] = field(default_factory=list)


def _is_plain_identifier(token: str) -> bool:
    if len(token) < _MIN_IDENT_CLASSIFY:
        return False
    return any(c.isalpha() for c in token) and any(c.isdigit() for c in token)


def _add_ident(idents: list[str], records: list[tuple[str, int, str]],
               surface: str, gid: int, prov: str) -> None:
    """Append an identifier variant with its occurrence record."""
    idents.append(surface)
    records.append((surface, gid, prov))


def tokenize(text: str) -> LexicalTerms:
    lowered = text.casefold()
    next_group = 0

    # ── Separator-bearing identifiers ──
    sep_id_pattern = re.compile(
        r"(?<![a-z0-9])(?=[a-z0-9]*[.\-/_+:])([a-z0-9][a-z0-9._\-/:+]*[a-z0-9])(?![a-z0-9])"
    )
    sep_matches = list(sep_id_pattern.finditer(lowered))

    identifiers: list[str] = []
    id_records: list[tuple[str, int, str]] = []

    for m in sep_matches:
        token = m.group(0).strip(".")
        if len(token) < 2:
            continue
        gid = next_group
        next_group += 1
        _add_ident(identifiers, id_records, token, gid, _PROV_WHOLE)
        normalized = re.sub(r"[.\-/_:\s]+", ".", token)
        if normalized != token:
            _add_ident(identifiers, id_records, normalized, gid, _PROV_NORMALIZED)

    # ── General ASCII terms ──
    ascii_word_pattern = re.compile(r"[a-z0-9]+")

    # ── Plain alphanumeric identifiers (occurrence-aware) ──
    for m in ascii_word_pattern.finditer(lowered):
        word = m.group(0)
        if not _is_plain_identifier(word):
            continue

        word_start = m.start()
        parent_gid = -1
        for sm in sep_matches:
            if sm.start() <= word_start < sm.end():
                sep_token = sm.group(0).strip(".")
                # Find the record for this separator token to get its gid
                for surf, g, _ in id_records:
                    if surf == sep_token and g >= 0:
                        parent_gid = g
                        break
                break

        if parent_gid >= 0:
            _add_ident(identifiers, id_records, word, parent_gid, _PROV_DERIVED)
        else:
            gid = next_group
            next_group += 1
            _add_ident(identifiers, id_records, word, gid, _PROV_WHOLE)

    # Filter ascii terms
    all_surfaces = {rec[0] for rec in id_records}
    ascii_terms = [w for w in ascii_word_pattern.findall(lowered)
                   if len(w) >= 2 and w not in all_surfaces]

    # ── CJK ──
    cjk_pattern = re.compile(r"[一-鿿]+")
    cjk_raw = cjk_pattern.findall(text)
    cjk_bigrams: list[str] = []
    for s in cjk_raw:
        for i in range(len(s) - 1):
            cjk_bigrams.append(s[i:i + 2])
    cjk_terms: list[str] = []
    seen_cjk: set[str] = set()
    for t in cjk_raw + cjk_bigrams:
        if t not in seen_cjk:
            seen_cjk.add(t)
            cjk_terms.append(t)

    # ── N-grams ──
    id_ngrams: dict[str, set[str]] = {}
    for token in set(identifiers):
        if len(token) >= _MIN_IDENT_NGRAM:
            ngrams = {token[i:i + _NGRAM_SIZE] for i in range(len(token) - _NGRAM_SIZE + 1)}
            if ngrams:
                id_ngrams[token] = ngrams

    return LexicalTerms(
        ascii_terms=ascii_terms, identifier_terms=identifiers,
        cjk_terms=cjk_terms, identifier_ngrams=id_ngrams, id_records=id_records,
    )


# ── Scoring helpers ─────────────────────────────────────────────────

def _terminal_numeric(identifier: str) -> str | None:
    m = re.search(r"(\d+)$", identifier)
    return m.group(1) if m else None


def _is_substring_pair(a: str, b: str) -> bool:
    return a in b or b in a


def _is_boundary_contained(shorter: str, longer: str) -> bool:
    if shorter not in longer:
        return False
    if len(shorter) / len(longer) < _MIN_CONTAINMENT_RATIO:
        return False
    idx = longer.find(shorter)
    at_start, at_end = idx == 0, idx + len(shorter) == len(longer)
    end_idx = idx + len(shorter)
    if at_start and not at_end:
        if end_idx < len(longer):
            after = longer[end_idx]
            return (after in ".-_/:+" or shorter[-1].isalpha() != after.isalpha()
                    or shorter[-1].isdigit() != after.isdigit())
        return True
    if at_end and not at_start:
        return True
    left_ok = idx == 0
    if not left_ok:
        lc, rc = longer[idx - 1], shorter[0]
        left_ok = lc in ".-_/:+" or lc.isalpha() != rc.isalpha() or lc.isdigit() != rc.isdigit()
    if not left_ok:
        return False
    right_ok = end_idx >= len(longer)
    if not right_ok:
        lc, rc = shorter[-1], longer[end_idx]
        right_ok = rc in ".-_/:+" or lc.isalpha() != rc.isalpha() or lc.isdigit() != rc.isdigit()
    return right_ok


def _ngram_eligible(shorter: str, longer: str) -> bool:
    if _is_substring_pair(shorter, longer):
        return False
    sn, ln = _terminal_numeric(shorter), _terminal_numeric(longer)
    return not (sn is not None and ln is not None and sn != ln)


_STRONG_TIERS = {"exact", "contain"}


def _build_query_groups(
    id_records: list[tuple[str, int, str]],
) -> dict[int, list[tuple[str, str, int]]]:
    """Group query identifier variants by source group.

    Returns {gid: [(surface, provenance, occurrence_index), ...]}.
    Using occurrence_index for stable ordering.
    """
    groups: dict[int, list[tuple[str, str, int]]] = {}
    for i, (surface, gid, prov) in enumerate(id_records):
        groups.setdefault(gid, []).append((surface, prov, i))
    return groups


def _chunk_ident_map(
    id_records: list[tuple[str, int, str]],
) -> list[tuple[str, str]]:
    """Return list of (surface, provenance) for chunk identifiers."""
    return [(surface, prov) for surface, _, prov in id_records]


def score_chunk(
    query_terms: LexicalTerms,
    chunk_terms: LexicalTerms,
) -> tuple[float, dict, dict[int, str]]:
    metadata: dict = {
        "exact_identifiers": 0, "exact_ascii_terms": 0, "exact_cjk_terms": 0,
        "contained_identifiers": 0, "ngram_matches": 0,
    }
    score = 0.0
    chunk_idents = _chunk_ident_map(chunk_terms.id_records)
    chunk_ngrams = chunk_terms.identifier_ngrams
    query_groups = _build_query_groups(query_terms.id_records)
    group_tiers: dict[int, str] = {}

    for gid, qid_variants in query_groups.items():
        best = 0.0
        best_tier = ""

        for qid, q_prov, _ in qid_variants:
            # Exact: both sides whole/normalized
            if q_prov in _EXACT_PROVS:
                for cid, c_prov in chunk_idents:
                    if c_prov in _EXACT_PROVS and qid == cid:
                        best, best_tier = 5.0, "exact"
                        break
            if best >= 5.0:
                continue

            # Containment: both sides whole/normalized (not derived)
            if q_prov in _CONTAIN_PROVS and len(qid) >= _MIN_IDENT_CONTAIN:
                for cid, c_prov in chunk_idents:
                    if c_prov not in _CONTAIN_PROVS:
                        continue
                    if qid == cid or len(cid) < _MIN_IDENT_CONTAIN:
                        continue
                    shorter, longer = (qid, cid) if len(qid) <= len(cid) else (cid, qid)
                    if _is_boundary_contained(shorter, longer):
                        best, best_tier = 3.0, "contain"
                        break
            if best >= 3.0:
                continue

            # N-gram
            if qid in query_terms.identifier_ngrams:
                q_ngrams = query_terms.identifier_ngrams[qid]
                for cid, _ in chunk_idents:
                    if qid == cid:
                        continue
                    c_ngrams = chunk_ngrams.get(cid)
                    if not c_ngrams or not q_ngrams:
                        continue
                    if not _ngram_eligible(qid, cid):
                        continue
                    overlap = len(q_ngrams & c_ngrams)
                    min_size = min(len(q_ngrams), len(c_ngrams))
                    if min_size > 0 and overlap / min_size >= _MIN_NGRAM_OVERLAP:
                        best, best_tier = 2.0, "ngram"
                        break

        group_tiers[gid] = best_tier
        if best_tier == "exact":
            metadata["exact_identifiers"] += 1
        elif best_tier == "contain":
            metadata["contained_identifiers"] += 1
        elif best_tier == "ngram":
            metadata["ngram_matches"] += 1
        score += best

    # ── General term matches (capped) ──
    term_score = 0.0
    chunk_ascii_set = set(chunk_terms.ascii_terms)
    for term in query_terms.ascii_terms:
        if term in chunk_ascii_set:
            metadata["exact_ascii_terms"] += 1
            term_score += 1.0
    chunk_cjk_set = set(chunk_terms.cjk_terms)
    for term in query_terms.cjk_terms:
        if term in chunk_cjk_set:
            metadata["exact_cjk_terms"] += 1
            term_score += 1.0
    score += min(term_score, _MAX_GENERAL_TERM_SCORE)

    return score, metadata, group_tiers


def suppress_ngram_for_strong_groups(
    candidates_evidence: list[tuple[object, float, dict, dict[int, str]]],
    strong_groups: set[int],
) -> list[tuple[object, float, dict]]:
    result: list[tuple[object, float, dict]] = []
    for candidate, score, meta, group_tiers in candidates_evidence:
        removed = 0
        new_meta = dict(meta)
        for gid, tier in group_tiers.items():
            if tier == "ngram" and gid in strong_groups:
                removed += 2.0
                new_meta["ngram_matches"] = max(0, new_meta.get("ngram_matches", 0) - 1)
        result.append((candidate, score - removed, new_meta))
    return result
