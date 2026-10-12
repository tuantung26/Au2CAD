"""
Knowledge Base Loader
=====================
Reads all markdown files in the docs/knowledge_base directory
and concatenates them into a single context string for the LLM.
"""

import logging
from pathlib import Path

logger = logging.getLogger(__name__)

KNOWLEDGE_BASE_DIR = Path("docs/knowledge_base")

def load_knowledge_base() -> str:
    """Reads all .md and .txt files in the knowledge base directory."""
    if not KNOWLEDGE_BASE_DIR.exists():
        logger.warning(f"Knowledge base directory not found at {KNOWLEDGE_BASE_DIR}")
        return ""
        
    knowledge_texts = []
    
    # Process both .md and .txt files
    for ext in ["*.md", "*.txt"]:
        for file_path in KNOWLEDGE_BASE_DIR.glob(ext):
            try:
                content = file_path.read_text(encoding="utf-8").strip()
                if content:
                    knowledge_texts.append(f"--- Document: {file_path.name} ---\n{content}")
            except Exception as e:
                logger.error(f"Failed to read knowledge file {file_path}: {e}")
                
    if not knowledge_texts:
        return ""
        
    return "\n\n".join(knowledge_texts)
