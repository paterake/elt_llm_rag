
import shutil
import sys
from pathlib import Path
import logging

# Configure logging
logging.basicConfig(level=logging.INFO, format="%(message)s")
logger = logging.getLogger(__name__)

from elt_llm_core.config import RagConfig

def main():
    """Clear all RAG data (ChromaDB and LlamaIndex artifacts)."""
    # 1. Locate config
    repo_root = Path(__file__).resolve().parent.parent.parent.parent
    config_path = repo_root / "elt_llm_ingest" / "config" / "rag_config.yaml"
    
    if not config_path.exists():
        logger.error(f"❌ Config not found at {config_path}")
        return 1

    # 2. Load config to get persist_dir
    try:
        rag_config = RagConfig.from_yaml(config_path)
        # Resolve persist_dir relative to config file if it's a relative path
        persist_dir = Path(rag_config.chroma.persist_dir)
        if not persist_dir.is_absolute():
            persist_dir = (config_path.parent / persist_dir).resolve()
            
    except Exception as e:
        logger.error(f"❌ Failed to load config: {e}")
        return 1

    # 3. Confirm deletion
    logger.info(f"🗑️  Targeting ChromaDB directory: {persist_dir}")
    
    if not persist_dir.exists():
        logger.info("✅ Directory does not exist. Nothing to clean.")
        return 0

    # 4. Delete
    try:
        shutil.rmtree(persist_dir)
        logger.info(f"✅ Successfully deleted {persist_dir}")
    except Exception as e:
        logger.error(f"❌ Failed to delete directory: {e}")
        return 1

    return 0

if __name__ == "__main__":
    sys.exit(main())
