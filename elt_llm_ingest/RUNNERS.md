# RAG Ingestion Runners - Complete Reference

## Quick Command Reference

| Command | Description |
|---------|-------------|
| `--status` | Show all collections with document counts |
| `--status -v` | Show collections with detailed metadata |
| `--list` | List available ingestion configs |
| `--cfg <name>` | Ingest documents from config |
| `--cfg <name> --no-rebuild` | Append mode (skip unchanged files) |
| `--cfg <name> --force` | Force re-ingestion (bypass hash check) |
| `--cfg <name> --delete` | Delete a collection |
| `--cfg <name> --delete -f` | Delete without confirmation |
| `-v` | Verbose output |

---

## Check Collection Status

```bash
# Show all collections with document counts
uv run python -m elt_llm_ingest.runner --status

# Show detailed metadata
uv run python -m elt_llm_ingest.runner --status -v
```

**Example Output:**
```
=== ChromaDB Status ===

Persist directory: /Users/rpatel/Documents/__code/git/emailrak/elt_llm_rag/elt_llm_ingest/chroma_db

Collection Name                        Documents  Metadata
----------------------------------------------------------------------
fa_handbook                                 9673  -
fa_data_architecture                        2261  -
dama_dmbok                                 11943  -
file_hashes                                    3  -

Total: 4 collection(s), 23880 document(s)
```

**Understanding the output:**

- **Collection Name**: ChromaDB collection identifier
- **Documents**: Number of document chunks stored
- **Metadata**: Collection metadata (shown with `-v`)
- **file_hashes**: Internal collection for smart ingest tracking

---

## List Available Configs

```bash
uv run python -m elt_llm_ingest.runner --list
```

**Output:**
```
=== Available RAG Ingestion Configs ===

Config directory: /path/to/elt_llm_ingest/config

  dama_dmbok
  fa_data_architecture
  fa_handbook
  leanix
  sad
  supplier_assess

=== Usage ===

Ingest:
  uv run python -m elt_llm_ingest.runner --cfg dama_dmbok
  ...
```

---

## Smart Ingest (with Change Detection)

By default, the ingestion system uses **file-level SHA256 hash detection** to avoid re-processing unchanged files:

| Mode | Command | Behavior |
|------|---------|----------|
| **Rebuild** (default) | `--cfg dama_dmbok` | Clears collection, re-ingests all files, resets hash tracking |
| **Append** | `--cfg dama_dmbok --no-rebuild` | Only ingests changed/new files, preserves existing data |
| **Force** | `--cfg dama_dmbok --force` | Bypasses hash check, re-ingests everything |

### How It Works

1. **First run**: All files are ingested; SHA256 hashes stored in `file_hashes` collection
2. **Subsequent runs**: System compares current file hashes against stored hashes
3. **Unchanged files**: Skipped entirely (no processing overhead)
4. **Changed files**: Re-ingested and hash updated

### Hash Storage

- Stored in dedicated `file_hashes` ChromaDB collection
- Uses file path + collection name as unique key
- Metadata includes: `file_path`, `hash`, `collection_name`, `timestamp`
- Queryable like any other collection (but used as key-value store)

---

## Ingest Documents

### DAMA-DMBOK2R (Data Management Body of Knowledge)

```bash
# Basic ingest (rebuild mode)
uv run python -m elt_llm_ingest.runner --cfg dama_dmbok

# Verbose output
uv run python -m elt_llm_ingest.runner --cfg dama_dmbok -v

# Append mode (skip unchanged files)
uv run python -m elt_llm_ingest.runner --cfg dama_dmbok --no-rebuild

# Force re-ingestion
uv run python -m elt_llm_ingest.runner --cfg dama_dmbok --force
```

### FA Handbook (Financial Accounting)

```bash
# Basic ingest
uv run python -m elt_llm_ingest.runner --cfg fa_handbook

# Verbose output
uv run python -m elt_llm_ingest.runner --cfg fa_handbook -v

# Append mode
uv run python -m elt_llm_ingest.runner --cfg fa_handbook --no-rebuild
```

### FA Data Architecture

```bash
# Basic ingest
uv run python -m elt_llm_ingest.runner --cfg fa_data_architecture

# Verbose output
uv run python -m elt_llm_ingest.runner --cfg fa_data_architecture -v

# Append mode
uv run python -m elt_llm_ingest.runner --cfg fa_data_architecture --no-rebuild
```

### SAD (Solution Architecture Definition)

```bash
# Basic ingest
uv run python -m elt_llm_ingest.runner --cfg sad

# Verbose output
uv run python -m elt_llm_ingest.runner --cfg sad -v

# Append mode
uv run python -m elt_llm_ingest.runner --cfg sad --no-rebuild
```

### LeanIX (Architecture Platform)

```bash
# Basic ingest
uv run python -m elt_llm_ingest.runner --cfg leanix

# Verbose output
uv run python -m elt_llm_ingest.runner --cfg leanix -v

# Append mode
uv run python -m elt_llm_ingest.runner --cfg leanix --no-rebuild
```

### Supplier Assessment

```bash
# Basic ingest
uv run python -m elt_llm_ingest.runner --cfg supplier_assess

# Verbose output
uv run python -m elt_llm_ingest.runner --cfg supplier_assess -v

# Append mode
uv run python -m elt_llm_ingest.runner --cfg supplier_assess --no-rebuild
```

---

## Delete Collections

```bash
# Delete with confirmation prompt
uv run python -m elt_llm_ingest.runner --cfg dama_dmbok --delete

# Delete without confirmation (force)
uv run python -m elt_llm_ingest.runner --cfg dama_dmbok --delete -f
```

**Available for all configs:**
- `dama_dmbok`
- `fa_handbook`
- `fa_data_architecture`
- `sad`
- `leanix`
- `supplier_assess`

---

## Common Workflows

### First-Time Setup

```bash
# 1. Pull required Ollama models
ollama pull nomic-embed-text
ollama pull llama3.2

# 2. Ingest all documents
uv run python -m elt_llm_ingest.runner --cfg dama_dmbok
uv run python -m elt_llm_ingest.runner --cfg fa_handbook
uv run python -m elt_llm_ingest.runner --cfg fa_data_architecture
uv run python -m elt_llm_ingest.runner --cfg sad
uv run python -m elt_llm_ingest.runner --cfg leanix
uv run python -m elt_llm_ingest.runner --cfg supplier_assess

# 3. Verify ingestion
uv run python -m elt_llm_ingest.runner --status

# 4. Query documents (see elt_llm_query/README.md)
uv run python -m elt_llm_query.runner --cfg all_collections
```

### Daily Update (Incremental)

```bash
# Check current status
uv run python -m elt_llm_ingest.runner --status

# Re-run all configs (only processes changed files)
uv run python -m elt_llm_ingest.runner --cfg dama_dmbok --no-rebuild
uv run python -m elt_llm_ingest.runner --cfg fa_handbook --no-rebuild
uv run python -m elt_llm_ingest.runner --cfg fa_data_architecture --no-rebuild

# Verify no changes detected
uv run python -m elt_llm_ingest.runner --status
```

### Rebuild a Collection

```bash
# Option 1: Simple re-run (default rebuild mode)
uv run python -m elt_llm_ingest.runner --cfg dama_dmbok -v

# Option 2: Delete and re-ingest (full reset)
uv run python -m elt_llm_ingest.runner --cfg dama_dmbok --delete -f
uv run python -m elt_llm_ingest.runner --cfg dama_dmbok -v
```

### Force Re-ingestion (Skip Hash Check)

```bash
# Re-process all files even if unchanged
uv run python -m elt_llm_ingest.runner --cfg dama_dmbok --no-rebuild --force
```

### Add New Document Version

```bash
# 1. Update the file path in config/<config>.yaml
# 2. Run append mode (only new/changed files processed)
uv run python -m elt_llm_ingest.runner --cfg dama_dmbok --no-rebuild
```

### Debug Ingestion Issues

```bash
# Verbose output to see what's happening
uv run python -m elt_llm_ingest.runner --cfg dama_dmbok -v

# Check file_hashes collection
uv run python -m elt_llm_ingest.runner --status -v
```

---

## Query Documents

After ingesting, use `elt_llm_query` to search the documents:

```bash
# List query configs
uv run python -m elt_llm_query.runner --list

# Query single collection
uv run python -m elt_llm_query.runner --cfg dama_only

# Query multiple collections
uv run python -m elt_llm_query.runner --cfg dama_fa_combined

# Single query
uv run python -m elt_llm_query.runner --cfg dama_only -q "What is data governance?"
```

See `../elt_llm_query/README.md` for complete query documentation.

---

## Configuration Reference

### Ingestion Config Format (`config/*.yaml`)

```yaml
collection_name: "dama_dmbok"

file_paths:
  - "~/Documents/__data/books/DAMA-DMBOK2R_unlocked.pdf"

metadata:
  domain: "data_management"
  type: "body_of_knowledge"
  source: "DAMA-DMBOK2R"

rebuild: true  # Default: true
```

| Field | Type | Required | Default | Description |
|-------|------|----------|---------|-------------|
| `collection_name` | string | ✅ | - | ChromaDB collection identifier |
| `file_paths` | list | ✅ | - | Paths to documents to ingest |
| `metadata` | dict | ❌ | `{}` | Metadata attached to all documents |
| `rebuild` | boolean | ❌ | `true` | Rebuild collection on each run |

### RAG Config (`config/rag_config.yaml`)

```yaml
chroma:
  persist_dir: "./chroma_db"
  tenant: "rag_tenants"
  database: "knowledge_base"

ollama:
  base_url: "http://localhost:11434"
  embedding_model: "nomic-embed-text"
  llm_model: "llama3.2"

chunking:
  strategy: "sentence"
  chunk_size: 1024
  chunk_overlap: 200
```

---

## Troubleshooting

### "No changes detected" but expected updates

The file hash hasn't changed. Verify the file was actually modified, or use `--force`:

```bash
uv run python -m elt_llm_ingest.runner --cfg dama_dmbok --force
```

### Collection shows 0 documents after ingest

Check verbose output for errors:

```bash
uv run python -m elt_llm_ingest.runner --cfg dama_dmbok -v
```

Common causes:
- File path doesn't exist
- File format not supported
- Permission issues

### ChromaDB connection errors

Verify persist directory and check collection status:

```bash
uv run python -m elt_llm_ingest.runner --status -v
```

### Reset Hash Tracking

To completely reset hash tracking for a collection:

```bash
# Delete the collection
uv run python -m elt_llm_ingest.runner --cfg dama_dmbok --delete -f

# Re-ingest (creates fresh hash entries)
uv run python -m elt_llm_ingest.runner --cfg dama_dmbok
```

### Clear All Hashes

To clear the `file_hashes` collection:

```bash
uv run python -m elt_llm_ingest.runner --cfg dama_dmbok --delete -f
# This removes hashes for files in dama_dmbok config

# Or manually delete the file_hashes collection via Python:
uv run python -c "
import chromadb
client = chromadb.PersistentClient(path='chroma_db')
client.delete_collection('file_hashes')
"
```

---

## Environment Variables

| Variable | Description |
|----------|-------------|
| `RAG_CHROMA_DIR` | Override ChromaDB persist directory |
| `RAG_DOCS_DIR` | Override base directory for document paths |

---

## See Also

- **README.md** - Package overview and installation
- **elt_llm_query/** - Query module documentation
- **elt_llm_core/** - Core RAG utilities
