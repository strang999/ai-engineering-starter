"""Lesson 10: chunks, three searches, embeddings (mock route), answers with checked sources, eval kinds."""

import json

import pytest
from fastapi.testclient import TestClient

from support.contract import RagAnswer
from support.evals import load_cases, select
from support.evals.__main__ import main as evals_main
from support.llm import embed
from support.llm.mock import use_scenario
from support.rag import (NOT_FOUND, SearchError, answer_from_kb, build_index, check_answer, hybrid_search,
                         keyword_search, load_chunks, search_kb, split_doc, vector_search)
from support.rag.chunk import KB_DIR
from support.server import app

QUESTION = "Скільки днів є, щоб повернути товар?"


def happy():
    return select(load_cases(), kind="retrieval", tag="happy")


# --- chunks ---------------------------------------------------------------------------------

def test_default_chunking_is_one_chunk_per_file_and_the_archive_is_not_read():
    chunks = load_chunks()
    assert len(chunks) == 7 and {c.source for c in chunks} == {p.name for p in KB_DIR.glob("*.md")}
    assert all(c.id == f"{c.source}#0" for c in chunks)
    assert "30 днів" not in " ".join(c.text for c in chunks)
    assert chunks[0].passage.startswith(chunks[0].title + ". ")


def test_small_chunks_overlap_by_one_sentence():
    chunks = load_chunks(max_chars=200)
    assert len(chunks) == 20
    pov = [c for c in chunks if c.source == "povernennya.md"]
    assert len(pov) >= 2
    last_sentence = pov[0].text.replace("\n", " ").split(". ")[-1]
    assert last_sentence.strip(". ") in pov[1].text


def test_split_doc_titles_and_paragraphs():
    chunks = split_doc("# Заголовок\n\nПерший абзац.\n\nДругий абзац.", "x.md", max_chars=15)
    assert [c.title for c in chunks] == ["Заголовок"] * len(chunks) and len(chunks) == 2


# --- searches -------------------------------------------------------------------------------

def test_keyword_search_returns_nothing_without_a_shared_word():
    idx = build_index()
    assert keyword_search(idx, "how long do I have to return an item?") == []
    assert keyword_search(idx, "povernennya tovaru") == []


def test_empty_question_searches_nothing():
    assert search_kb("   ") == []


def test_unknown_mode_is_a_programmer_error():
    with pytest.raises(ValueError):
        search_kb(QUESTION, mode="magic")


def hits(search, idx, k):
    got = 0
    for c in happy():
        found = search(idx, c["input"]["question"], k)
        got += any(c["expect"]["evidence"] in ch.text for ch in found)
    return got


@pytest.mark.parametrize("size,expected", [
    # the lesson's table: (keyword, vector, hybrid) as (hit@1, hit@3) of 10
    (800, {"keyword": (9, 10), "vector": (10, 10), "hybrid": (9, 10)}),
    (200, {"keyword": (8, 9), "vector": (9, 10), "hybrid": (8, 10)}),
])
def test_hit_at_k_table_of_the_lesson(size, expected):
    idx = build_index(max_chars=size)
    fns = {"keyword": keyword_search, "vector": vector_search, "hybrid": hybrid_search}
    for mode, (h1, h3) in expected.items():
        assert (hits(fns[mode], idx, 1), hits(fns[mode], idx, 3)) == (h1, h3), (size, mode)


def test_synonym_is_missed_by_keywords_and_found_by_vectors():
    idx = build_index()
    assert keyword_search(idx, "крем") == []
    assert vector_search(idx, "крем", 3)[0].source == "povernennya.md"


def test_hybrid_merges_two_lists_by_rank():
    idx = build_index()
    ids = [c.id for c in hybrid_search(idx, "Що означає E-218", 3)]
    assert ids[0] == "kody.md#0" and len(ids) == 3


def test_vector_search_without_vectors_says_how_to_get_them():
    with pytest.raises(SearchError, match="mock_no_vector"):
        search_kb("розкажи анекдот про котів", mode="vector")


# --- embed ----------------------------------------------------------------------------------

def test_embed_mock_has_course_vectors_and_normalised():
    r = embed(["крем"], kind="query")
    assert r.status == "ok" and r.dim == 384 and r.route == "mock"
    assert abs(sum(x * x for x in r.vectors[0]) - 1) < 1e-3


def test_embed_programmer_errors():
    for bad in ([], [""], ["ok", "  "], "text"):
        with pytest.raises(ValueError):
            embed(bad)
    with pytest.raises(ValueError):
        embed(["a"], kind="doc")


def test_embed_routes_fail_with_readable_codes(monkeypatch):
    monkeypatch.setenv("AIEZ_EMBED", "anthropic")
    assert embed(["a"]).error.startswith("no_embeddings")
    monkeypatch.setenv("AIEZ_EMBED", "nope")
    assert embed(["a"]).error.startswith("unknown_route")
    for name, key in (("openai", "OPENAI_API_KEY"), ("gemini", "GEMINI_API_KEY")):
        monkeypatch.setenv("AIEZ_EMBED", name)
        monkeypatch.delenv(key, raising=False)
        monkeypatch.delenv("GOOGLE_API_KEY", raising=False)
        assert embed(["a"]).error.startswith("no_api_key")


# --- answers --------------------------------------------------------------------------------

def test_answer_cites_a_retrieved_chunk_that_holds_the_quote():
    r = answer_from_kb(QUESTION)
    assert r.status == "ok" and r.found and r.sources == ["povernennya.md#0"]
    assert set(r.sources) <= set(r.retrieved) and "14 днів" in r.answer


def test_answer_says_the_base_has_nothing():
    r = answer_from_kb("Чи доставляєте ви в Польщу?")
    assert r.status == "ok" and r.found is False and r.answer.startswith(NOT_FOUND) and r.sources == []


def test_empty_question_makes_no_call():
    assert answer_from_kb("  ").status == "empty_input"


def test_no_vector_is_an_error_status_not_an_exception():
    r = answer_from_kb("розкажи анекдот про котів")
    assert r.status == "error" and "mock_no_vector" in r.error


@pytest.mark.parametrize("scenario,status", [
    ("invented_source", "needs_review"), ("no_sources", "needs_review"),
    ("refusal", "refusal"), ("truncated", "truncated"), ("timeout", "error"), ("spend_cap", "error"),
])
def test_every_model_status_has_a_branch(scenario, status):
    with use_scenario(scenario):
        assert answer_from_kb(QUESTION).status == status


def test_a_confident_wrong_answer_is_not_caught_by_the_source_check():
    """The limit of check_answer: the cited chunk exists, so code accepts it. Only an eval catches this."""
    with use_scenario("answers_without_basis"):
        r = answer_from_kb("Чи доставляєте ви в Польщу?")
    assert r.status == "ok" and r.found is True


def test_check_answer_rules():
    ids = ["a#0", "b#0"]
    assert check_answer(RagAnswer(found=True, answer="x [a#0]", sources=["a#0"]), ids) == {"sources": "accept"}
    assert check_answer(RagAnswer(found=True, answer="x", sources=["z#9"]), ids)["sources"].startswith("reject")
    assert check_answer(RagAnswer(found=True, answer="x", sources=[]), ids)["sources"].startswith("reject")
    assert check_answer(RagAnswer(found=False, answer=NOT_FOUND + ": нема", sources=[]), ids) == {"not_found": "accept"}
    assert check_answer(RagAnswer(found=False, answer="Не знаю", sources=[]), ids)["not_found"].startswith("reject")


# --- the eval set ---------------------------------------------------------------------------

def test_every_evidence_quote_is_in_the_knowledge_base_and_ids_are_ordered():
    corpus = " ".join(p.read_text(encoding="utf-8") for p in KB_DIR.glob("*.md"))
    rows = [r for r in load_cases() if r["kind"] in ("retrieval", "answer")]
    for r in rows:
        quote = r["expect"].get("evidence")
        if quote:
            assert quote in corpus, r["id"]
    ids = [r["id"] for r in rows]
    assert ids == sorted(ids, key=lambda i: (i[0] != "r", i)) and len(ids) == len(set(ids))
    assert sum(r["kind"] == "retrieval" for r in rows) == 16


def test_mock_fixtures_cover_every_case_question():
    known = {json.loads(line)["question"] for line in
             open("fixtures/mock_rag.jsonl", encoding="utf-8").read().splitlines() if line.strip()}
    for r in load_cases():
        if r["kind"] in ("retrieval", "answer") and not r.get("mock"):
            assert r["input"]["question"] in known, r["id"]


def run(capsys, *args):
    code = evals_main(list(args))
    return code, capsys.readouterr().out


def test_run_evals_retrieval_prints_hits_and_a_mode_table(capsys):
    code, out = run(capsys, "--kind", "retrieval", "--mode", "all", "--tag", "happy")
    assert code == 0
    assert "kind=retrieval · mode keyword" in out and "hit@1 9/10 · hit@3 10/10" in out
    assert "mode      hit@1    hit@3" in out and "vector     10/10    10/10" in out


def test_run_evals_retrieval_baseline_is_keywords_only(capsys):
    code, out = run(capsys, "--kind", "retrieval", "--baseline", "--tag", "edge")
    assert code == 0 and "mode keyword" in out and "FAIL r012" in out and "FAIL r014" in out


def test_run_evals_answer_leaves_one_deliberate_failure(capsys):
    code, out = run(capsys, "--kind", "answer")
    assert code == 0
    assert "pass 16/17" in out and "FAIL a017" in out and out.count("FAIL") == 1


def test_run_evals_answer_dry_run_calls_nothing(capsys):
    code, out = run(capsys, "--kind", "answer", "--dry-run")
    assert code == 0 and "nothing was called" in out


def test_run_evals_answer_refuses_baseline_and_all(capsys):
    assert run(capsys, "--kind", "answer", "--baseline")[0] == 2
    assert run(capsys, "--kind", "answer", "--mode", "all")[0] == 2


# --- server ---------------------------------------------------------------------------------

def test_api_answer():
    client = TestClient(app)
    r = client.post("/api/answer", json={"question": QUESTION})
    assert r.status_code == 200 and r.json()["sources"] == ["povernennya.md#0"]
    assert client.post("/api/answer", json={"question": QUESTION, "customer_id": "c-99"}).status_code == 422
    assert client.post("/api/answer?k=99", json={"question": QUESTION}).status_code == 422


# --- own questions --------------------------------------------------------------------------

def test_add_question_writes_a_retrieval_case_that_runs(capsys):
    assert evals_main(["add-question", "Скільки діє гарантія на ноутбук?", "--evidence", "гарантія виробника 12 місяців"]) == 0
    assert evals_main(["add-question", "Чи є знижка студентам?", "--no-answer", "--kind", "answer"]) == 0
    capsys.readouterr()
    code, out = run(capsys, "--kind", "retrieval", "--tag", "own", "--mode", "keyword")
    assert code == 0 and "cases 1 (dev)" in out and "hit@1 1/1" in out


@pytest.mark.parametrize("args", [
    ["x"], ["x", "--evidence", "a", "--no-answer"], ["x", "--no-answer"], ["  ", "--evidence", "a"],
])
def test_add_question_refuses_nonsense(capsys, args):
    assert evals_main(["add-question", *args]) == 2


def test_run_evals_reads_your_own_documents(tmp_path, capsys):
    # BM25 needs at least 3 chunks: with 1 or 2 the idf of a word that is in half of them is 0
    (tmp_path / "garantiya.md").write_text("# Гарантія\n\nНа ноутбуки гарантія виробника 12 місяців.", encoding="utf-8")
    (tmp_path / "dostavka.md").write_text("# Доставка\n\nВідправляємо Новою поштою.", encoding="utf-8")
    (tmp_path / "oplata.md").write_text("# Оплата\n\nПриймаємо картки Visa.", encoding="utf-8")
    evals_main(["add-question", "Скільки діє гарантія на ноутбук?", "--evidence", "гарантія виробника 12 місяців"])
    capsys.readouterr()
    code, out = run(capsys, "--kind", "retrieval", "--tag", "own", "--mode", "keyword", "--kb", str(tmp_path))
    assert code == 0 and "3 chunks" in out and "hit@1 1/1" in out
