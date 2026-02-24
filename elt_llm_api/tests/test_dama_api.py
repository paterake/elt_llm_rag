from elt_llm_api import ask_dama


def test_dama_query_returns_sources_from_dama_document():
    question = "According to DAMA-DMBOK2, what is data governance?"
    result = ask_dama(question)
    assert result.response
    assert result.source_nodes
    source_files = [s["metadata"].get("source_file", "") for s in result.source_nodes]
    assert any("DAMA-DMBOK2R_unlocked.pdf" in path for path in source_files)

