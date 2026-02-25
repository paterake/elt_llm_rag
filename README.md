# ELT LLM RAG

**Retrieval-Augmented Generation (RAG) platform for FA architecture knowledge, data governance, and automated documentation generation.**

---

## Quick Links

| Document | Purpose |
|----------|---------|
| **[ARCHITECTURE.md](ARCHITECTURE.md)** | Full system architecture, conceptual model alignment, legal considerations |
| **[ROADMAP.md](ROADMAP.md)** | Implementation roadmap with phases, deliverables, and timelines |
| **[PROJECT_REVIEW.md](PROJECT_REVIEW.md)** | Independent project review (strengths, gaps, recommendations) |

---

## Prerequisites

- Python 3.11, 3.12, or 3.13 (ChromaDB incompatible with 3.14)
- Ollama running locally (`ollama serve`)
- uv for dependency management

## Quick Start

```bash
cd /Users/rpatel/Documents/__code/git/emailrak/elt_llm_rag
uv sync

# Pull models
ollama pull nomic-embed-text
ollama pull llama3.2
ollama pull qwen2.5:14b

# Ingest
cd elt_llm_ingest
uv run python -m elt_llm_ingest.runner --cfg dama_dmbok

# Query
cd ../elt_llm_query
uv run python -m elt_llm_query.runner --cfg dama_only
```

## Structure

| Module | Purpose | README |
|--------|---------|--------|
| `elt_llm_core/` | Core RAG infrastructure (ChromaDB, Ollama, config) | [elt_llm_core/README.md](elt_llm_core/README.md) |
| `elt_llm_ingest/` | Document ingestion with preprocessing and smart change detection | [elt_llm_ingest/README.md](elt_llm_ingest/README.md) |
| `elt_llm_query/` | Query interface (single/multi-collection, hybrid search) | [elt_llm_query/README.md](elt_llm_query/README.md) |
| `elt_llm_api/` | Programmatic API for querying (optional) | - |

## Key Features

- **Hybrid Search**: BM25 (keyword) + vector (semantic) for better retrieval
- **Smart Ingest**: SHA256 file change detection avoids reprocessing unchanged files
- **LeanIX Integration**: XML→Markdown preprocessing for conceptual data models
- **Multi-Collection Queries**: Query across DAMA, FA Handbook, LeanIX simultaneously
- **Local-Only Processing**: All data stays on your machine (DPO compliant)

## Strategic Alignment

- **Data Working Group**: Traceability from business terms → conceptual model → physical systems
- **Architecture Review Board**: Auto-generated SADs with consistent structure
- **Data Modellers**: Conceptual model as the frame for all artefacts
- **Project Teams**: Query-based access to standards, glossaries, patterns

## Current Collections

| Collection | Documents | Chunks | Status |
|------------|-----------|--------|--------|
| `dama_dmbok` | DAMA-DMBOK2 (PDF) | ~11,943 | ✅ Ingested |
| `fa_handbook` | FA Handbook (PDF) | ~9,673 | ✅ Ingested |
| `fa_leanix_*` (11 collections) | LeanIX conceptual model (XML) — split by domain | 15 | ✅ Ingested |
| `fa_data_architecture` | FA Data Architecture | TBD | ⏳ Config ready |

## Common Commands

```bash
# List available ingestion configs
uv run python -m elt_llm_ingest.runner --list

# Show ChromaDB status
uv run python -m elt_llm_ingest.runner --status

# Ingest with verbose output
uv run python -m elt_llm_ingest.runner --cfg dama_dmbok -v

# Ingest without rebuild (append mode, skip unchanged files)
uv run python -m elt_llm_ingest.runner --cfg dama_dmbok --no-rebuild

# List available query configs
uv run python -m elt_llm_query.runner --list

# Interactive query
uv run python -m elt_llm_query.runner --cfg leanix_fa_combined

# Single query
uv run python -m elt_llm_query.runner --cfg leanix_fa_combined -q "What is a Club?"

# Delete a collection
uv run python -m elt_llm_ingest.runner --cfg dama_dmbok --delete
```

## Roadmap Summary

| Phase | Focus | Timeline | Status |
|-------|-------|----------|--------|
| **Phase 0** | Foundation | Done | ✅ Complete |
| **Phase 1** | Business Catalogues (Glossary + Reference Data) | Weeks 1-4 | 🟡 In Progress |
| **Phase 2** | SAD Generator | Weeks 5-8 | ⏳ Pending |
| **Phase 3** | ERD Automation | Weeks 9-12 | ⏳ Pending |
| **Phase 4** | Purview Integration | Weeks 13-16 | ⏳ Pending |
| **Phase 5** | Vendor Assessment | Weeks 17-20 | ⏳ Pending |

See [ROADMAP.md](ROADMAP.md) for detailed deliverables.

## Legal & Compliance

**Data Protection (DPO)**: All data stays local — no FA assets leave your infrastructure.

| Aspect | Status |
|--------|--------|
| Data Residency | ✅ Local filesystem |
| Vector Store | ✅ ChromaDB local |
| LLM Processing | ✅ Ollama localhost |
| External APIs | ✅ None |

**Copyright**: DAMA-DMBOK2 and ISO standards are copyrighted. For personal/team use, risk is low. For organisation-wide deployment, seek legal review and check licensing.

See [ARCHITECTURE.md §9](ARCHITECTURE.md#9-legal--compliance-considerations) for full details.

## Contact

**Author**: Rakesh Patel  
**Repository**: `emailrak/elt_llm_rag`  
**Last Updated**: February 2026

