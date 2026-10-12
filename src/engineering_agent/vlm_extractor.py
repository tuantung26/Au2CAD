"""
VLM Extractor
=============
Extracts mechanical geometry, dimensions, tolerances, and features
from 2D technical drawing images using Vision-Language Models (Gemini).
"""

from __future__ import annotations

import logging
from pathlib import Path
from PIL import Image

from src.config import GOOGLE_API_KEY, VLM_MODEL

logger = logging.getLogger(__name__)

VLM_DRAWING_PROMPT = """You are a Principal Mechanical CAD Reconstruction Engineer inspecting an engineering drawing blueprint.
The technical drawing is the PRIMARY SINGLE SOURCE OF TRUTH (SSOT).
Meticulously decompose this drawing into an exhaustive inventory of 3D primitive shapes, their exact quantities, and the topological assembly rules showing how they are joined together.

Your report MUST contain these 4 mandatory sections:

### 1. Part Classification & Primary Datums
- Component Type & Function (e.g. Bearing block / Support bracket, Housing, Flange, Shaft).
- Primary Datum Origin (0,0,0) and reference coordinate axes (XY bottom base, YZ rear face, XZ symmetry plane).

### 2. Exhaustive Primitive Shapes & Quantity Inventory
List EVERY single geometric solid and feature without omitting any shape:
- **Base Root Solid**: Shape type (e.g. Box / Block), Dimensions (L x W x H), Quantity (e.g. 1).
- **Secondary Additive Solids**: Cylinders, Bosses, Lugs, Webs/Ribs with their individual dimensions and quantities.
- **Subtractive Cavities & Cuts**: Central through-bores, counterbores, bottom notches/slots, side channels, front cutouts with exact dimensions and quantities.
- **Edge Treatments**: Exact chamfer sizes (e.g. 10x45°) and fillet radii (e.g. R5).

### 3. Assembly & Joining Topology (How Shapes Connect)
For each shape identified above, clearly define the joining relationship:
- **Parent Body**: Which base entity does it attach to or cut into?
- **Attachment Interface**: Which face or plane? (e.g., Top face >Z, Bottom face <Z, Front face >Y, Coaxial center).
- **Join Operation**: `ADD` (Union boss), `SUBTRACT` (Cut/Hole/Pocket), or `BLEND` (Fillet/Chamfer).
- **Relative Position / Alignment**: Exact offset [dx, dy, dz] from datum or coaxial alignment.

### 4. Consolidated Dimension Table
A complete lookup table of all numerical values read directly from the blueprint (Length, Width, Height, Diameters Ø, Radii R, Offsets, Wall thicknesses).
"""


def analyze_drawing(drawing_path: Path, force_refresh: bool = False) -> str:
    """
    Run VLM inspection on a technical drawing image and return structured geometric notes.
    The blueprint drawing is the primary source of truth.
    Results are cached to disk so subsequent runs consume 0 API quota.
    """
    if not drawing_path or not drawing_path.exists():
        logger.warning("[VLM] Drawing path does not exist: %s", drawing_path)
        return ""

    # Check local cache first to avoid redundant API calls & rate limits
    cache_path = drawing_path.parent / f"{drawing_path.stem}_vlm_notes.txt"
    if cache_path.exists():
        try:
            cached_text = cache_path.read_text(encoding="utf-8").strip()
            if cached_text:
                logger.info("[VLM] Loaded cached drawing analysis from %s (0 API calls)", cache_path.name)
                return cached_text
        except Exception as e:
            logger.debug("[VLM] Could not read cache: %s", e)

    if not GOOGLE_API_KEY:
        logger.warning("[VLM] GOOGLE_API_KEY is not configured in .env; skipping VLM extraction.")
        return ""

    logger.info("[VLM] Analyzing technical drawing %s using %s ...", drawing_path.name, VLM_MODEL)

    try:
        from google import genai

        client = genai.Client(api_key=GOOGLE_API_KEY)

        # Open image (if PDF, try to extract first page or convert)
        if drawing_path.suffix.lower() == ".pdf":
            try:
                import pypdfium2
                pdf = pypdfium2.PdfDocument(str(drawing_path))
                page = pdf[0]
                img = page.render(scale=2).to_pil()
            except Exception as e:
                logger.warning("[VLM] Could not render PDF to image: %s", e)
                return ""
        else:
            img = Image.open(drawing_path)

        # Lightweight, high-quota candidate models
        candidate_models = [VLM_MODEL]
        for fallback in ["models/gemini-flash-lite-latest", "models/gemini-3.1-flash-lite", "models/gemini-flash-latest"]:
            if fallback not in candidate_models:
                candidate_models.append(fallback)

        last_err = None
        for model_name in candidate_models:
            # Skip deprecated models
            if "2.5-flash" in model_name or "2.0-flash" in model_name:
                continue
            try:
                response = client.models.generate_content(
                    model=model_name,
                    contents=[img, VLM_DRAWING_PROMPT],
                )
                if response and response.text:
                    logger.info("[VLM] Analysis completed successfully using %s.", model_name)
                    # Cache to disk for future runs
                    try:
                        cache_path.write_text(response.text, encoding="utf-8")
                        logger.info("[VLM] Cached drawing analysis to %s", cache_path.name)
                    except Exception:
                        pass
                    return response.text
            except Exception as err:
                last_err = err
                logger.warning("[VLM] Model %s failed: %s. Trying next candidate...", model_name, err)

        if last_err:
            logger.error("[VLM] All candidate models failed: %s", last_err)

    except Exception as exc:
        logger.error("[VLM] Failed to run drawing analysis: %s", exc)

    return ""


VLM_PHOTO_PROMPT = """You are a 3D Reverse Engineering Specialist analyzing PHOTOGRAPHS of a physical manufactured part.
Unlike engineering drawings, these are real-world photos with perspective and lighting — focus on shape estimation, not exact numbers.

Your task is to identify the 3D geometry that can be modeled in CAD.

### 1. Part Overview
- What type of mechanical part is this? (bracket, housing, flange, shaft, plate, etc.)
- Approximate overall shape and proportions.
- Visible surfaces and faces.

### 2. Primary Geometric Primitives Observed
For each visible feature, describe:
- **Shape type**: Box, Cylinder, Cone, Fillet, Chamfer, Slot, Hole, Boss, Rib, Web
- **Relative size**: (e.g., "large base plate", "small boss on top", "through-hole roughly 1/3 of plate width")
- **Position**: Where on the part? (top, center, bottom, left side, front face)
- **Count**: How many of each?

### 3. Surface & Edge Details
- Sharp vs. rounded edges (chamfers / fillets)
- Any visible threaded holes, counterbores, or blind holes
- Symmetry: is the part symmetric along any axis?

### 4. Estimated Proportions (relative, not exact)
Give rough dimensional ratios:
- Height : Width : Depth (e.g., 1 : 1.5 : 0.8)
- Boss diameter vs. base width (e.g., ~40%)
- Wall thickness vs. overall height

### 5. Material / Manufacturing Clues
- Visible machining marks, casting surfaces, or injection molding parting lines
- Color / finish hints (anodized, painted, raw metal, plastic)

Important: Do NOT invent precise dimensions. Focus on SHAPE and TOPOLOGY that can guide CAD reconstruction.
"""


def analyze_object_photos(photo_paths: list, force_refresh: bool = False) -> str:
    """
    Run VLM inspection on one or more real-world object photographs.
    Returns a structured shape description combining analysis from all photos.
    Results are cached per photo set (keyed by sorted filenames).
    """
    if not photo_paths:
        return ""

    # Cache key based on sorted filenames
    cache_key = "_".join(sorted(p.stem for p in photo_paths))
    cache_path = photo_paths[0].parent / f"{cache_key}_photo_vlm_notes.txt"
    if not force_refresh and cache_path.exists():
        try:
            cached = cache_path.read_text(encoding="utf-8").strip()
            if cached:
                logger.info("[VLM-Photo] Loaded cached photo analysis (0 API calls)")
                return cached
        except Exception:
            pass

    if not GOOGLE_API_KEY:
        logger.warning("[VLM-Photo] GOOGLE_API_KEY not set; skipping photo VLM analysis.")
        return ""

    logger.info("[VLM-Photo] Analyzing %d object photo(s)...", len(photo_paths))

    try:
        from google import genai

        client = genai.Client(api_key=GOOGLE_API_KEY)

        # Load all images
        images = []
        for p in photo_paths:
            try:
                img = Image.open(p).convert("RGB")
                # Downscale if too large to keep within API limits
                max_dim = 1024
                w, h = img.size
                if max(w, h) > max_dim:
                    scale = max_dim / max(w, h)
                    img = img.resize((int(w * scale), int(h * scale)), Image.LANCZOS)
                images.append(img)
            except Exception as e:
                logger.warning("[VLM-Photo] Could not open %s: %s", p.name, e)

        if not images:
            return ""

        # Build content: all images + prompt
        contents = images + [VLM_PHOTO_PROMPT]

        candidate_models = [VLM_MODEL]
        for fallback in ["models/gemini-flash-lite-latest", "models/gemini-3.1-flash-lite"]:
            if fallback not in candidate_models:
                candidate_models.append(fallback)

        last_err = None
        for model_name in candidate_models:
            if "2.5-flash" in model_name or "2.0-flash" in model_name:
                continue
            try:
                response = client.models.generate_content(
                    model=model_name,
                    contents=contents,
                )
                if response and response.text:
                    logger.info("[VLM-Photo] Analysis completed using %s.", model_name)
                    try:
                        cache_path.write_text(response.text, encoding="utf-8")
                    except Exception:
                        pass
                    return response.text
            except Exception as err:
                last_err = err
                logger.warning("[VLM-Photo] Model %s failed: %s", model_name, err)

        if last_err:
            logger.error("[VLM-Photo] All models failed: %s", last_err)

    except Exception as exc:
        logger.error("[VLM-Photo] Failed: %s", exc)

    return ""

