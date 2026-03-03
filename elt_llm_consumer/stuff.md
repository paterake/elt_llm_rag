To confirm whether the inventory collections actually contain PARTY-type entities at all, you could run:


uv run --package elt-llm-core python3 - <<'EOF'
from pathlib import Path
from llama_index.core import StorageContext
from elt_llm_core.config import load_config
from elt_llm_core.vector_store import get_docstore_path
from elt_llm_query.query import resolve_collection_prefixes

cfg = load_config(Path("elt_llm_ingest/config/rag_config.yaml"))
colls = resolve_collection_prefixes(["fa_leanix_global_inventory"], cfg)
print(f"Inventory collections: {colls}")
for c in colls[:2]:
    path = get_docstore_path(cfg.chroma, c)
    storage = StorageContext.from_defaults(persist_dir=str(path))
    nodes = list(storage.docstore.docs.values())
    print(f"\n--- {c} ({len(nodes)} nodes) ---")
    for node in nodes[:3]:
        print(repr((getattr(node, 'text', '') or '')[:200]))
EOF
That will tell us what's actually in the inventory and whether it's even expected to cover PARTY entities.

