"""Tests for lexical tokenization and tiered keyword scoring.

Covers:
- Separator-bearing and plain alphanumeric identifier extraction
- Tiered scoring (exact > containment > n-gram) with deduplication
- Start-/end-aligned containment for plain identifiers
- Separate CJK / ASCII evidence in metadata
- Five-character short identifier handling
- Document_id filtering within same project
- Two-document regression with plain alphanumeric pair
"""

from app.rag.retrieval.keyword import retrieve_keyword
from app.rag.retrieval.lexical import score_chunk, tokenize
from tests.retrieval_test_helpers import seed_retrieval_chunk


# ── Tokenization: separator-bearing identifiers ─────────────────────

def test_tokenize_chinese_with_adjacent_ascii_identifier() -> None:
    terms = tokenize("服务器 web-01 的状态是什么")
    assert "web-01" in terms.identifier_terms
    assert "服务器" in terms.cjk_terms


def test_tokenize_hostname() -> None:
    terms = tokenize("aaasiaw01.asi.local")
    assert "aaasiaw01.asi.local" in terms.identifier_terms


def test_tokenize_ip_address() -> None:
    terms = tokenize("connect to 168.106.21.84 via ssh")
    assert "168.106.21.84" in terms.identifier_terms


def test_tokenize_hyphenated_code() -> None:
    terms = tokenize("deploy server-node-01 now")
    assert "server-node-01" in terms.identifier_terms


def test_tokenize_underscored_code() -> None:
    terms = tokenize("user asi_supoort login")
    assert "asi_supoort" in terms.identifier_terms


def test_tokenize_version_like() -> None:
    terms = tokenize("upgrade to v2.4.1-beta")
    assert "v2.4.1-beta" in terms.identifier_terms


# ── Tokenization: plain alphanumeric identifiers ────────────────────

def test_plain_alphanumeric_is_identifier() -> None:
    terms = tokenize("regionnode01")
    assert "regionnode01" in terms.identifier_terms


def test_five_char_mixed_is_identifier() -> None:
    """abc01 (5 chars, letters+digits) is classified as identifier."""
    terms = tokenize("abc01")
    assert "abc01" in terms.identifier_terms


def test_plain_alphanumeric_short_rejected() -> None:
    """a1 (too short, <4) is NOT an identifier."""
    terms = tokenize("a1")
    assert "a1" not in terms.identifier_terms


def test_short_word_not_identifier() -> None:
    """host, go, server are plain words, not identifiers."""
    terms = tokenize("go to the host server")
    for t in terms.identifier_ngrams:
        assert len(t) >= 5  # n-gram threshold is 5


# ── Negative containment/n-gram: public scorer rejection ────────────

def test_neighbor_pairs_have_zero_score() -> None:
    """Rejected near-neighbor pairs produce zero evidence in score_chunk."""
    pairs = [("node01", "node012"), ("device01", "device010"),
             ("node01", "node02"), ("server01", "server02")]
    for query_text, chunk_text in pairs:
        q = tokenize(query_text)
        c = tokenize(chunk_text)
        _, meta, _ = score_chunk(q, c)
        assert meta["contained_identifiers"] == 0, f"{query_text} vs {chunk_text}: containment must be 0"
        assert meta["ngram_matches"] == 0, f"{query_text} vs {chunk_text}: ngram must be 0"


def test_internal_substring_not_match() -> None:
    """'abc01' inside 'xabc01y' produces zero evidence."""
    q = tokenize("abc01")
    c = tokenize("xabc01y")
    _, meta, _ = score_chunk(q, c)
    assert meta["contained_identifiers"] == 0
    assert meta["ngram_matches"] == 0


def test_one_pair_no_weaker_tiers() -> None:
    """Exact match produces ONLY exact evidence, zero containment/ngram."""
    q = tokenize("server01-east")
    c = tokenize("server01-east active")
    _, meta, _ = score_chunk(q, c)
    assert meta["exact_identifiers"] == 1
    assert meta["contained_identifiers"] == 0
    assert meta["ngram_matches"] == 0


def test_identifier_scoring_is_invariant_to_query_and_chunk_order() -> None:
    query_a = score_chunk(tokenize("node01-east node01"), tokenize("node01"))
    query_b = score_chunk(tokenize("node01 node01-east"), tokenize("node01"))
    assert query_a == query_b

    chunk_a = score_chunk(tokenize("node01"), tokenize("node01-east node01"))
    chunk_b = score_chunk(tokenize("node01"), tokenize("node01 node01-east"))
    assert chunk_a == chunk_b


def test_sibling_identifier_cannot_create_strong_containment() -> None:
    score, metadata, tiers = score_chunk(
        tokenize("node01-east"), tokenize("node01-west"),
    )

    assert score == 2.0
    assert metadata["contained_identifiers"] == 0
    assert metadata["ngram_matches"] == 1
    assert set(tiers.values()) == {"ngram"}


def test_parent_child_containment_remains_symmetric() -> None:
    forward = score_chunk(tokenize("node01"), tokenize("node01-east"))
    reverse = score_chunk(tokenize("node01-east"), tokenize("node01"))

    assert forward[0] == reverse[0] == 3.0
    assert forward[1]["contained_identifiers"] == 1
    assert reverse[1]["contained_identifiers"] == 1


# ── Matching: tiered scoring with dedup ─────────────────────────────

def test_exact_identifier_ranks_above_general_terms() -> None:
    query = tokenize("web-01 status")
    chunk_a = tokenize("web-01 active")
    chunk_b = tokenize("web server status check")
    sa, _, _ = score_chunk(query, chunk_a)
    sb, _, _ = score_chunk(query, chunk_b)
    assert sa > sb


def test_contained_identifier_scores_lower_than_exact() -> None:
    """Containment (3.0) scores strictly below exact match (5.0)."""
    query = tokenize("server01-east")
    chunk_exact = tokenize("server01-east active")
    chunk_contained = tokenize("server01 standby")

    se, _, _ = score_chunk(query, chunk_exact)
    sc, mc, _ = score_chunk(query, chunk_contained)

    assert se > 0
    assert sc > 0
    assert se > sc, f"exact={se} must be > containment={sc}"


def test_one_pair_not_double_counted() -> None:
    """Exact entity reports 1 evidence, zero containment, zero n-gram."""
    query = tokenize("server01-east")
    chunk = tokenize("server01-east active")

    _, meta, _ = score_chunk(query, chunk)
    assert meta["exact_identifiers"] == 1
    assert meta["contained_identifiers"] == 0
    assert meta["ngram_matches"] == 0


# ── Containment: boundaries ─────────────────────────────────────────

def test_boundary_containment_rejects_mid_token_match() -> None:
    """'node01' inside 'anode012' is NOT a valid match (mid-token, no boundary)."""
    query = tokenize("node01")
    chunk = tokenize("anode012")
    _, meta, _ = score_chunk(query, chunk)
    assert meta["contained_identifiers"] == 0


def test_boundary_containment_accepts_at_separator() -> None:
    """Containment works with separator boundary — direct unit test."""
    from app.rag.retrieval.lexical import _is_boundary_contained
    assert _is_boundary_contained("node01", "region.node01")


def test_end_aligned_containment_accepted() -> None:
    """'node01' inside 'regionnode01' (end-aligned suffix) is a valid match."""
    query = tokenize("node01")
    chunk = tokenize("regionnode01")
    _, meta, _ = score_chunk(query, chunk)
    assert meta["contained_identifiers"] >= 1


def test_start_aligned_containment_accepted() -> None:
    """'srv01' inside 'srv01node02' (start-aligned prefix) is valid."""
    query = tokenize("srv01")
    chunk = tokenize("srv01node02")
    _, meta, _ = score_chunk(query, chunk)
    assert meta["contained_identifiers"] >= 1


def test_boundary_containment_rejects_short_ratio() -> None:
    """Short token contained in much longer one with low ratio is rejected."""
    # xy is too short to be an identifier anyway; verify no containment
    query = tokenize("abcdefghxy")
    chunk = tokenize("xy")
    _, meta, _ = score_chunk(query, chunk)
    assert meta["contained_identifiers"] == 0


def test_unrelated_identifier_rejected() -> None:
    query = tokenize("web-01")
    chunk_match = tokenize("web-01 active")
    chunk_unrelated = tokenize("web-99 standby")
    sm, _, _ = score_chunk(query, chunk_match)
    su, _, _ = score_chunk(query, chunk_unrelated)
    assert sm > su


def test_repeated_common_terms_dont_overpower_identifier() -> None:
    query = tokenize("web-01")
    chunk_id = tokenize("web-01")
    chunk_spam = tokenize("web web web web web web web web web web")
    si, _, _ = score_chunk(query, chunk_id)
    ss, _, _ = score_chunk(query, chunk_spam)
    assert si >= ss


def test_score_metadata_explains_match() -> None:
    query = tokenize("web-01 active")
    chunk = tokenize("web-01 is active and standby")
    _, meta, _ = score_chunk(query, chunk)
    assert meta["exact_identifiers"] >= 1
    assert meta["exact_ascii_terms"] >= 1


# ── CJK evidence isolation ──────────────────────────────────────────

def test_cjk_terms_contribute_independently() -> None:
    """CJK-only query against a CJK-only chunk produces cjk evidence, not ascii."""
    query = tokenize("服务器")
    chunk = tokenize("服务器状态检查")
    _, meta, _ = score_chunk(query, chunk)
    assert meta["exact_cjk_terms"] > 0, "CJK match must produce cjk evidence"
    assert meta["exact_ascii_terms"] == 0, "no ASCII in pure CJK query"


# ── Integration: keyword retrieval ──────────────────────────────────

def test_keyword_retrieval_finds_identifier_in_chunk(sqlite_session_factory) -> None:
    with sqlite_session_factory() as db:
        proj, _, _ = seed_retrieval_chunk(db, "ident", "server web-01 is active", embedding=None)
        db.commit()
        results = retrieve_keyword(db, proj.id, "web-01", top_k=5)
    assert len(results) >= 1


def test_keyword_retrieval_handles_chinese_query(sqlite_session_factory) -> None:
    with sqlite_session_factory() as db:
        proj, _, _ = seed_retrieval_chunk(db, "cn", "服务器 web-01 当前处于活跃状态", embedding=None)
        db.commit()
        results = retrieve_keyword(db, proj.id, "web-01 服务器", top_k=5)
    assert len(results) >= 1
    cjk_evidence = any(
        (r.score_metadata or {}).get("exact_cjk_terms", 0) > 0 for r in results
    )
    assert cjk_evidence


def test_candidate_pool_suppresses_weak_sibling_when_strong_evidence_exists(
    sqlite_session_factory,
) -> None:
    import uuid as _uuid

    from app.models.chunk import Chunk
    from app.models.document import Document as DocModel, DocumentStatus
    from app.models.project import Project

    rows = {
        "exact": "node01-east alpha",
        "containment": "node01 alpha",
        "sibling-west": "node01-west alpha beta gamma delta",
        "sibling-north": "node01-north alpha beta gamma delta",
        "unrelated": "asset77-north alpha beta gamma delta",
    }
    with sqlite_session_factory() as db:
        project = Project(name=f"candidate-pool-{_uuid.uuid4()}")
        db.add(project)
        db.flush()
        for index, (name, content) in enumerate(rows.items()):
            document = DocModel(
                project_id=project.id,
                filename=f"{name}.txt",
                storage_path=f"/tmp/{name}.txt",
                file_size_bytes=len(content),
                status=DocumentStatus.indexed,
            )
            db.add(document)
            db.flush()
            db.add(Chunk(
                project_id=project.id,
                document_id=document.id,
                chunk_index=0,
                text=content,
                content_hash=f"pool-{index}",
            ))
        db.commit()
        results = retrieve_keyword(
            db,
            project.id,
            "node01-east alpha beta gamma delta",
            top_k=10,
        )

    by_name = {result.document_name: result for result in results}
    assert set(by_name) == {f"{name}.txt" for name in rows}
    assert results[0].document_name == "exact.txt"
    assert by_name["exact.txt"].score_metadata["exact_identifiers"] == 1
    assert by_name["containment.txt"].score_metadata["contained_identifiers"] == 1
    for sibling in ("sibling-west.txt", "sibling-north.txt"):
        assert by_name[sibling].score_metadata["ngram_matches"] == 0
        assert by_name[sibling].keyword_score < by_name["exact.txt"].keyword_score
    assert by_name["unrelated.txt"].keyword_score < by_name["exact.txt"].keyword_score


def test_candidate_pool_suppression_is_scoped_to_each_identifier_group(
    sqlite_session_factory,
) -> None:
    import uuid as _uuid

    from app.models.chunk import Chunk
    from app.models.document import Document as DocModel, DocumentStatus
    from app.models.project import Project

    rows = {
        "first-exact": "node01-east",
        "first-sibling": "node01-west",
        "second-fallback": "asset77-south",
    }
    with sqlite_session_factory() as db:
        project = Project(name=f"group-suppression-{_uuid.uuid4()}")
        db.add(project)
        db.flush()
        for name, content in rows.items():
            document = DocModel(
                project_id=project.id,
                filename=f"{name}.txt",
                storage_path=f"/tmp/{name}.txt",
                file_size_bytes=len(content),
                status=DocumentStatus.indexed,
            )
            db.add(document)
            db.flush()
            db.add(Chunk(
                project_id=project.id,
                document_id=document.id,
                chunk_index=0,
                text=content,
                content_hash=name,
            ))
        db.commit()
        results = retrieve_keyword(
            db, project.id, "node01-east asset77-north", top_k=10,
        )

    by_name = {result.document_name: result for result in results}
    assert set(by_name) == {"first-exact.txt", "second-fallback.txt"}
    assert by_name["first-exact.txt"].score_metadata["exact_identifiers"] == 1
    assert by_name["second-fallback.txt"].score_metadata["ngram_matches"] == 1


def test_keyword_retrieval_document_id_filter(sqlite_session_factory) -> None:
    """document_id filter excludes another document in the SAME project."""
    import uuid as _uuid
    from app.models.project import Project
    from app.models.document import Document as DocModel, DocumentStatus
    from app.models.chunk import Chunk

    with sqlite_session_factory() as db:
        proj = Project(name=f"docfilt-{_uuid.uuid4()}")
        db.add(proj)
        db.flush()

        def _add(text: str) -> tuple:
            doc = DocModel(project_id=proj.id, filename="f.txt",
                           storage_path="/tmp/f.txt", file_size_bytes=len(text),
                           status=DocumentStatus.indexed)
            db.add(doc)
            db.flush()
            chunk = Chunk(project_id=proj.id, document_id=doc.id,
                          chunk_index=0, text=text,
                          content_hash=str(_uuid.uuid4()))
            db.add(chunk)
            return doc, chunk

        doc_a, _ = _add("alpha active")
        doc_b, chunk_b = _add("alpha standby")
        chunk_b_id = chunk_b.id
        db.commit()

        results = retrieve_keyword(db, proj.id, "alpha", top_k=10, document_id=doc_a.id)

    assert all(r.document_id == doc_a.id for r in results)
    assert chunk_b_id not in {r.chunk_id for r in results}


def test_keyword_project_isolation_with_identifiers(sqlite_session_factory) -> None:
    with sqlite_session_factory() as db:
        proj_a, _, _ = seed_retrieval_chunk(db, "iso-a", "node-alpha-01 active", embedding=None)
        proj_b, _, chunk_b = seed_retrieval_chunk(db, "iso-b", "node-alpha-01 standby", embedding=None)
        chunk_b_id = chunk_b.id
        db.commit()
        results = retrieve_keyword(db, proj_a.id, "node-alpha-01", top_k=5)
    assert all(r.chunk_id != chunk_b_id for r in results)


def test_keyword_retrieval_empty_query_graceful(sqlite_session_factory) -> None:
    with sqlite_session_factory() as db:
        proj, _, _ = seed_retrieval_chunk(db, "empty-q", "some content", embedding=None)
        db.commit()
        results = retrieve_keyword(db, proj.id, "   ", top_k=5)
    assert results == []


# ── Tie-breaking ────────────────────────────────────────────────────

def test_equal_score_stable_tiebreak(sqlite_session_factory) -> None:
    """Equal-score chunks ordered by chunk_index ascending within same document."""
    import uuid as _uuid
    from app.models.project import Project
    from app.models.document import Document as DocModel, DocumentStatus
    from app.models.chunk import Chunk

    with sqlite_session_factory() as db:
        proj = Project(name=f"tie-{_uuid.uuid4()}")
        db.add(proj)
        db.flush()
        doc = DocModel(project_id=proj.id, filename="tie.txt",
                       storage_path="/tmp/t.txt", file_size_bytes=10,
                       status=DocumentStatus.indexed)
        db.add(doc)
        db.flush()
        db.add(Chunk(project_id=proj.id, document_id=doc.id,
                     chunk_index=0, text="alpha beta", content_hash="h1"))
        db.add(Chunk(project_id=proj.id, document_id=doc.id,
                     chunk_index=1, text="alpha gamma", content_hash="h2"))
        db.commit()
        results = retrieve_keyword(db, proj.id, "alpha", top_k=10)

    assert len(results) >= 2, f"expected >=2, got {len(results)}"
    assert results[0].keyword_score == results[1].keyword_score
    assert (results[0].chunk_index or 0) <= (results[1].chunk_index or 0)


def test_equal_score_duplicate_names_use_stable_document_and_chunk_ids(
    sqlite_session_factory,
) -> None:
    import uuid as _uuid

    from app.models.chunk import Chunk
    from app.models.document import Document as DocModel, DocumentStatus
    from app.models.project import Project

    low_document_id = _uuid.UUID(int=1)
    high_document_id = _uuid.UUID(int=2)
    low_chunk_id = _uuid.UUID(int=11)
    high_chunk_id = _uuid.UUID(int=22)

    with sqlite_session_factory() as db:
        project = Project(name=f"tie-identities-{_uuid.uuid4()}")
        db.add(project)
        db.flush()
        for document_id, chunk_id in (
            (high_document_id, high_chunk_id),
            (low_document_id, low_chunk_id),
        ):
            document = DocModel(
                id=document_id,
                project_id=project.id,
                filename="same.txt",
                storage_path=f"/tmp/{document_id}.txt",
                file_size_bytes=10,
                status=DocumentStatus.indexed,
            )
            db.add(document)
            db.flush()
            db.add(Chunk(
                id=chunk_id,
                project_id=project.id,
                document_id=document_id,
                chunk_index=0,
                text="alpha",
                content_hash=str(chunk_id),
            ))
        db.commit()
        results = retrieve_keyword(db, project.id, "alpha", top_k=2)

    assert [result.chunk_id for result in results] == [low_chunk_id, high_chunk_id]


# ── Regression: plain alphanumeric pair (no separator) ──────────────

def test_containment_recalls_shorter_identifier() -> None:
    """Longer plain id query recalls shorter id via containment (unit test)."""
    query = tokenize("regionabc01")
    chunk_long = tokenize("server regionabc01 IP 10.0.0.1 status active")
    chunk_short = tokenize("abc01 | 10.0.0.1 | active")

    _, meta_long, _ = score_chunk(query, chunk_long)
    _, meta_short, _ = score_chunk(query, chunk_short)

    assert meta_long["exact_identifiers"] >= 1, "doc A must exact-match"
    assert meta_short["contained_identifiers"] + meta_short["ngram_matches"] > 0, (
        f"doc B must use containment or n-gram; got {meta_short}"
    )


def test_plain_alphanumeric_pair_both_recalled(sqlite_session_factory) -> None:
    """Both longer and shorter plain alphanumeric identifier chunks are recalled."""
    import uuid as _uuid
    from app.models.project import Project
    from app.models.document import Document as DocModel, DocumentStatus
    from app.models.chunk import Chunk

    with sqlite_session_factory() as db:
        proj = Project(name=f"regress-{_uuid.uuid4()}")
        db.add(proj)
        db.flush()

        def _add(text: str) -> None:
            doc = DocModel(project_id=proj.id, filename="r.txt",
                           storage_path="/tmp/r.txt", file_size_bytes=len(text),
                           status=DocumentStatus.indexed)
            db.add(doc)
            db.flush()
            db.add(Chunk(project_id=proj.id, document_id=doc.id,
                         chunk_index=0, text=text,
                         content_hash=str(_uuid.uuid4())))

        _add("server regionabc01 IP 10.0.0.1 status active")
        _add("abc01 | 10.0.0.1 | active")
        _add("server region configuration for alpha routing")
        db.commit()

        results = retrieve_keyword(db, proj.id, "regionabc01", top_k=10)

    texts = [r.text for r in results]
    assert any("regionabc01" in t for t in texts), "doc A must be recalled"
    assert any("abc01" in t and "10.0.0.1" in t for t in texts), (
        f"doc B must be recalled; got texts={texts}"
    )
    # Both relevant docs must rank ahead of unrelated doc C if present
    a_idx = next(i for i, t in enumerate(texts) if "regionabc01" in t)
    b_idx = next(i for i, t in enumerate(texts) if "abc01" in t and "10.0.0.1" in t)
    c_matches = [i for i, t in enumerate(texts) if "alpha routing" in t]
    if c_matches:
        assert a_idx < c_matches[0], f"doc A (idx {a_idx}) must rank before doc C"
        assert b_idx < c_matches[0], f"doc B (idx {b_idx}) must rank before doc C"
