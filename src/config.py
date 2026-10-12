"""
Au2CAD — Global configuration loader.

Reads settings from environment variables / .env file.
All modules import from here instead of reading env directly.
"""

from __future__ import annotations

import os
from pathlib import Path

from dotenv import load_dotenv

# Load .env from project root (works regardless of cwd)
_PROJECT_ROOT = Path(__file__).resolve().parent.parent
load_dotenv(_PROJECT_ROOT / ".env", override=False)
load_dotenv(_PROJECT_ROOT / ".env.example", override=False)


# ── LLM ───────────────────────────────────────────────────────
LLM_PROVIDER: str = os.getenv("LLM_PROVIDER", "openai")
LLM_MODEL: str = os.getenv("LLM_MODEL", "gpt-4o")
OPENAI_API_KEY: str = os.getenv("OPENAI_API_KEY", "")
ANTHROPIC_API_KEY: str = os.getenv("ANTHROPIC_API_KEY", "")
GOOGLE_API_KEY: str = os.getenv("GOOGLE_API_KEY", "")
FPT_API_KEY: str = os.getenv("FPT_API_KEY") or os.getenv("FPT_AI_FACTORY_API_KEY", "")
FPT_BASE_URL: str = os.getenv("FPT_BASE_URL", "https://mkp-api.fptcloud.com/v1")
FPT_SYSTEMONE_URL: str = os.getenv("FPT_SYSTEMONE_URL", "https://mkp-api.fptcloud.com/v1/systemone")

# ── VLM ───────────────────────────────────────────────────────
VLM_PROVIDER: str = os.getenv("VLM_PROVIDER", "google")
VLM_MODEL: str = os.getenv("VLM_MODEL", "models/gemini-3.8-flash")

# ── Hunyuan3D ─────────────────────────────────────────────────
HUNYUAN3D_MODE: str = os.getenv("HUNYUAN3D_MODE", "api")
HUNYUAN3D_API_URL: str = os.getenv("HUNYUAN3D_API_URL", "")
HUNYUAN3D_API_KEY: str = os.getenv("HUNYUAN3D_API_KEY", "")
HUNYUAN3D_LOCAL_PATH: Path = Path(os.getenv("HUNYUAN3D_LOCAL_PATH", "./third_party/Hunyuan3D"))

# ── CADFit ────────────────────────────────────────────────────
CADFIT_PATH: Path = Path(os.getenv("CADFIT_PATH", "./third_party/CADFit"))
CADFIT_MAX_ITERATIONS: int = int(os.getenv("CADFIT_MAX_ITERATIONS", "10"))

# ── Validation ────────────────────────────────────────────────
VALIDATION_IOU_THRESHOLD: float = float(os.getenv("VALIDATION_IOU_THRESHOLD", "0.90"))
VALIDATION_DIM_ERROR_MM: float = float(os.getenv("VALIDATION_DIM_ERROR_MM", "0.5"))

# ── Paths ─────────────────────────────────────────────────────
DEMO_PART_DIR: Path = _PROJECT_ROOT / os.getenv("DEMO_PART_DIR", "demo_part")
GROUND_TRUTH_DIR: Path = _PROJECT_ROOT / os.getenv("GROUND_TRUTH_DIR", "ground_truth")
OUTPUT_DIR: Path = _PROJECT_ROOT / os.getenv("OUTPUT_DIR", "output")
