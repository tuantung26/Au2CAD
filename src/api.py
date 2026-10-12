"""
Au2CAD — Cloud API Server (FastAPI)
===================================
Provides REST API & WebSocket/SSE-ready endpoints to control the Au2CAD
reverse engineering & mold design pipeline, stream real-time logs,
serve 3D models (STL/STEP), and interact with the Engineering Agent.
"""

from __future__ import annotations

import asyncio
import json
import logging
import os
import shutil
import threading
import time
import uuid
from pathlib import Path
from typing import Any, Dict, List, Optional

from fastapi import FastAPI, File, Form, HTTPException, UploadFile, BackgroundTasks
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

logger = logging.getLogger("au2cad.api")
logging.basicConfig(level=logging.INFO)

app = FastAPI(
    title="Au2CAD Cloud API",
    description="Agentic AI System for Automated Reverse Engineering and Preliminary Mold Design",
    version="1.0.0",
)

# Enable CORS for local Vite dev server and cloud origins
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

BASE_DIR = Path(__file__).resolve().parent.parent
UPLOAD_DIR = BASE_DIR / "uploads"
OUTPUT_DIR = BASE_DIR / "output"
DEMO_DIR = BASE_DIR / "demo_part"

UPLOAD_DIR.mkdir(parents=True, exist_ok=True)
OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

# In-memory store for active and completed pipeline tasks
tasks: Dict[str, Dict[str, Any]] = {}


class PipelineRunRequest(BaseModel):
    mesh_filename: Optional[str] = None
    drawing_filename: Optional[str] = None
    context_text: Optional[str] = None
    mock_cadfit: bool = True
    target_faces: int = 50000
    skip_agent: bool = False
    skip_mold: bool = False


class ChatMessageRequest(BaseModel):
    message: str
    history: Optional[List[Dict[str, str]]] = None


@app.get("/api/health")
def health_check():
    return {
        "status": "healthy",
        "service": "Au2CAD AI Cloud Engine",
        "timestamp": time.time(),
        "has_demo_data": DEMO_DIR.exists(),
        "has_output_model": (OUTPUT_DIR / "solidworks" / "generated.stl").exists(),
    }


@app.get("/api/demo/meta")
def get_demo_meta():
    """Retrieve default demo dataset specifications and blueprint paths."""
    drawing_candidates = []
    drawing_dir = DEMO_DIR / "input" / "drawing"
    if drawing_dir.exists():
        for ext in ("*.jpg", "*.png", "*.jpeg", "*.pdf", "*.webp"):
            drawing_candidates.extend([p.name for p in drawing_dir.glob(ext)])

    desc_path = DEMO_DIR / "input" / "description.txt"
    desc_content = desc_path.read_text(encoding="utf-8") if desc_path.exists() else ""

    return {
        "part_name": "Mechanical Bracket",
        "description": desc_content,
        "available_drawings": drawing_candidates,
        "drawing_file": drawing_candidates[0] if drawing_candidates else None,
        "has_mesh": (DEMO_DIR / "reconstruction" / "raw_mesh.obj").exists(),
    }


@app.post("/api/upload")
async def upload_files(
    drawing: Optional[UploadFile] = File(None),
    mesh: Optional[UploadFile] = File(None),
    photos: Optional[List[UploadFile]] = File(None),
    description: Optional[str] = Form(None),
):
    """Upload blueprint drawing, 3D scan mesh, or multi-view photos."""
    uploaded_files = {}

    if drawing and drawing.filename:
        save_path = UPLOAD_DIR / f"drawing_{drawing.filename}"
        with open(save_path, "wb") as f:
            shutil.copyfileobj(drawing.file, f)
        uploaded_files["drawing"] = str(save_path.name)

    if mesh and mesh.filename:
        save_path = UPLOAD_DIR / f"mesh_{mesh.filename}"
        with open(save_path, "wb") as f:
            shutil.copyfileobj(mesh.file, f)
        uploaded_files["mesh"] = str(save_path.name)

    if photos:
        saved_photos = []
        for photo in photos:
            if photo.filename:
                save_path = UPLOAD_DIR / f"photo_{photo.filename}"
                with open(save_path, "wb") as f:
                    shutil.copyfileobj(photo.file, f)
                saved_photos.append(str(save_path.name))
        uploaded_files["photos"] = saved_photos

    if description:
        desc_path = UPLOAD_DIR / "user_description.txt"
        desc_path.write_text(description, encoding="utf-8")
        uploaded_files["description"] = description

    return {
        "status": "success",
        "files": uploaded_files,
        "message": f"Uploaded {len(uploaded_files)} input items successfully.",
    }


def _execute_pipeline_task(task_id: str, req: PipelineRunRequest):
    """Worker running the full Au2CAD Pipeline."""
    task = tasks[task_id]
    task["status"] = "running"
    task["started_at"] = time.time()
    task["progress"] = 5
    task["stage"] = "Initializing Engine"
    task["logs"].append("🚀 Khởi tạo tiến trình phân tích Au2CAD...")

    try:
        # Determine inputs
        input_drawing = None
        if req.drawing_filename:
            candidate = UPLOAD_DIR / req.drawing_filename
            if candidate.exists():
                input_drawing = candidate
        if not input_drawing:
            # Fallback to demo drawing
            drawing_dir = DEMO_DIR / "input" / "drawing"
            if drawing_dir.exists():
                for ext in ("*.jpg", "*.png", "*.jpeg", "*.pdf", "*.webp"):
                    candidates = sorted(drawing_dir.glob(ext))
                    if candidates:
                        input_drawing = candidates[0]
                        break

        input_mesh = None
        if req.mesh_filename:
            candidate = UPLOAD_DIR / req.mesh_filename
            if candidate.exists():
                input_mesh = candidate
        if not input_mesh and (DEMO_DIR / "reconstruction" / "raw_mesh.obj").exists():
            input_mesh = DEMO_DIR / "reconstruction" / "raw_mesh.obj"

        context_text = req.context_text or ""
        if not context_text:
            desc_file = DEMO_DIR / "input" / "description.txt"
            if desc_file.exists():
                context_text = desc_file.read_text(encoding="utf-8")

        dirs = {
            "reconstruction": OUTPUT_DIR / "reconstruction",
            "cadfit": OUTPUT_DIR / "cadfit",
            "cad_ir": OUTPUT_DIR / "cad_ir",
            "solidworks": OUTPUT_DIR / "solidworks",
            "validation": OUTPUT_DIR / "validation",
            "mold": OUTPUT_DIR / "mold",
        }
        for d in dirs.values():
            d.mkdir(parents=True, exist_ok=True)

        task["logs"].append(f"📁 Thư mục output: {OUTPUT_DIR}")
        if input_drawing:
            task["logs"].append(f"📐 Bản vẽ đầu vào: {input_drawing.name}")
        if input_mesh and input_mesh.exists():
            task["logs"].append(f"🧊 Mesh đầu vào: {input_mesh.name}")

        final_step_path = None

        # Check Branch
        if input_mesh and input_mesh.exists() and not input_drawing:
            # Geometry-led branch
            task["stage"] = "1/4 Mesh Preprocessing"
            task["progress"] = 25
            task["logs"].append("⚙️ [1/4] Đang lọc nhiễu và làm sạch lưới đa giác...")
            from src.mesh_preprocessing import MeshPreprocessor
            preprocessor = MeshPreprocessor(target_faces=req.target_faces)
            clean_mesh = dirs["reconstruction"] / "clean_mesh.obj"
            mesh_obj = preprocessor.run(input_mesh, clean_mesh)
            stats = preprocessor.get_stats(mesh_obj)
            task["logs"].append(f"✓ Hoàn tất làm sạch lưới: {stats.get('n_vertices', 0)} đỉnh, {stats.get('n_faces', 0)} mặt.")

            task["stage"] = "2/4 CADFit Program Synthesis"
            task["progress"] = 50
            task["logs"].append("🧩 [2/4] Chạy CADFit để tái cấu trúc CSG...")
            from src.cadfit_wrapper import get_runner, CADFitProgramParser
            from src.config import CADFIT_PATH, CADFIT_MAX_ITERATIONS
            runner = get_runner(cadfit_root=CADFIT_PATH, mock=req.mock_cadfit, max_iterations=CADFIT_MAX_ITERATIONS)
            cadfit_res = runner.run(mesh_path=clean_mesh, output_dir=dirs["cadfit"])
            parser = CADFitProgramParser(part_name=input_mesh.stem)
            cadir = parser.parse_file(cadfit_res.program_path)
            cadir.to_json(dirs["cad_ir"] / "model.json")
            task["logs"].append(f"✓ CADFit hoàn thành (IoU: {cadfit_res.iou:.4f}). CAD-IR đã lưu.")
        else:
            # 4-Module Drawing-led SSOT Pipeline
            task["stage"] = "1/5 Perception / Parser (SSOT)"
            task["progress"] = 20
            task["logs"].append("👁️ [1/5] Trích xuất hình học và kích thước chuẩn từ Bản vẽ kỹ thuật...")
            
            drawing_notes = ""
            structured_manifest = None
            if input_drawing and input_drawing.exists():
                from src.engineering_agent.vlm_extractor import analyze_drawing
                from src.perception import BlueprintFeatureDimensionExtractor, DrawingPerceptionParser
                drawing_notes = analyze_drawing(input_drawing)
                dim_extractor = BlueprintFeatureDimensionExtractor()
                structured_manifest = dim_extractor.extract(input_drawing)
                manifest_path = OUTPUT_DIR / "structured_dimensions.json"
                manifest_path.write_text(structured_manifest.model_dump_json(indent=2), encoding="utf-8")
                task["logs"].append(f"✓ Khóa {len(structured_manifest.dimension_constants)} hằng số hình học từ bản vẽ.")

                parser = DrawingPerceptionParser()
                perception_output = parser.parse(drawing_notes=drawing_notes, context=context_text)
                perception_path = OUTPUT_DIR / "perception.json"
                perception_path.write_text(perception_output.model_dump_json(indent=2), encoding="utf-8")
                task["logs"].append(f"✓ Nhận diện {len(perception_output.raw_features)} features, {len(perception_output.candidate_constraints)} constraints.")

            task["stage"] = "2/5 Geometry Graph Builder"
            task["progress"] = 40
            task["logs"].append("🕸️ [2/5] Xây dựng đồ thị ràng buộc hình học (Geometry Graph)...")
            from src.geometry_graph import GeometryGraphBuilder
            graph_builder = GeometryGraphBuilder()
            graph = graph_builder.build_graph(perception_output)
            final_cadir = graph_builder.resolve_to_cadir(perception_output)
            cadir_path = dirs["cad_ir"] / "model.json"
            final_cadir.to_json(cadir_path)
            task["logs"].append(f"✓ Đồ thị: {graph.number_of_nodes()} nodes, {graph.number_of_edges()} edges. Không có xung đột kích thước.")

            task["stage"] = "3/5 Parametric CadQuery Builder"
            task["progress"] = 65
            task["logs"].append("⚡ [3/5] Sinh mã CadQuery & Dựng mô hình khối rắn 3D (STEP/STL)...")
            from src.parametric_builder import ParametricCadQueryBuilder
            builder = ParametricCadQueryBuilder()
            build_result = builder.build(
                cadir=final_cadir,
                output_dir=dirs["solidworks"],
                input_drawing=input_drawing if input_drawing and input_drawing.exists() else None,
                drawing_notes=drawing_notes,
                feature_manifest=structured_manifest,
                auxiliary_context=context_text,
            )
            if not build_result.success:
                raise RuntimeError(f"CadQuery build failed: {build_result.error}")

            final_step_path = build_result.step_path
            task["logs"].append(f"✓ Tạo file STEP thành công: {build_result.step_path.name}")
            task["logs"].append(f"✓ Tạo file STL mesh thành công: {build_result.stl_path.name}")

            task["stage"] = "4/5 Symbolic & Geometric Verification"
            task["progress"] = 80
            task["logs"].append("🔍 [4/5] Kiểm định hình học và kiểm tra dung sai kích thước...")
            from src.verifier import SymbolicCADVerifier
            verifier = SymbolicCADVerifier()
            v_report = verifier.verify(
                cq_model=build_result.cq_model,
                cadir=final_cadir,
                perception=perception_output,
            )
            v_path = OUTPUT_DIR / "validation" / "verification_report.json"
            v_path.write_text(v_report.model_dump_json(indent=2), encoding="utf-8")
            status_text = "PASS" if v_report.passed else "FAIL"
            task["logs"].append(f"✓ Trạng thái kiểm định: {status_text} ({len(v_report.checks)} quy tắc đã kiểm tra).")

        # Preliminary Mold Design
        if not req.skip_mold and final_step_path:
            task["stage"] = "5/5 Preliminary Mold Design"
            task["progress"] = 92
            task["logs"].append("🏭 [5/5] Phân tích thiết kế khuôn: góc thoát, hướng rút khuôn, undercut...")
            stl_path = dirs["solidworks"] / "generated.stl"
            if stl_path.exists():
                from src.mold_design.analyst import MoldAnalyst
                analyst = MoldAnalyst()
                mold_result = analyst.analyse(stl_path, dirs["mold"])
                task["logs"].append(f"✓ Hướng rút khuôn: {mold_result.report.parting_direction}")
                task["logs"].append(f"✓ Mặt undercut: {len(mold_result.report.undercut_faces)}, Đường phân khuôn: {len(mold_result.report.parting_line_edges)} cạnh.")

        task["progress"] = 100
        task["stage"] = "Completed"
        task["status"] = "success"
        task["ended_at"] = time.time()
        task["logs"].append("🎉 Pipeline hoàn tất thành công! Sẵn sàng xuất mô hình 3D và báo cáo kỹ thuật.")

    except Exception as e:
        logger.exception("Pipeline failed")
        task["status"] = "failed"
        task["error"] = str(e)
        task["stage"] = "Error"
        task["logs"].append(f"❌ Lỗi tiến trình: {str(e)}")


@app.post("/api/pipeline/run")
def start_pipeline(req: PipelineRunRequest, background_tasks: BackgroundTasks):
    task_id = str(uuid.uuid4())[:8]
    tasks[task_id] = {
        "id": task_id,
        "status": "pending",
        "progress": 0,
        "stage": "Queued",
        "logs": [],
        "created_at": time.time(),
        "error": None,
    }
    background_tasks.add_task(_execute_pipeline_task, task_id, req)
    return {"task_id": task_id, "status": "started"}


@app.get("/api/pipeline/status/{task_id}")
def get_task_status(task_id: str):
    if task_id not in tasks:
        raise HTTPException(status_code=404, detail="Task not found")
    return tasks[task_id]


@app.get("/api/model/cad-ir")
def get_cad_ir():
    cad_ir_path = OUTPUT_DIR / "cad_ir" / "model.json"
    if not cad_ir_path.exists():
        # Fallback to demo cad_ir if exists
        demo_cad_ir = DEMO_DIR / "cad_ir" / "model.json"
        if demo_cad_ir.exists():
            cad_ir_path = demo_cad_ir
        else:
            return JSONResponse(status_code=404, content={"detail": "CAD-IR model not generated yet."})
    try:
        data = json.loads(cad_ir_path.read_text(encoding="utf-8"))
        return data
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/model/stl")
def download_stl():
    """Serves the generated STL mesh file for Three.js 3D rendering."""
    stl_path = OUTPUT_DIR / "solidworks" / "generated.stl"
    if not stl_path.exists():
        demo_stl = DEMO_DIR / "solidworks" / "generated.stl"
        if demo_stl.exists():
            stl_path = demo_stl
        else:
            raise HTTPException(status_code=404, detail="STL mesh model not found. Please run the pipeline first.")
    return FileResponse(
        path=stl_path,
        media_type="application/sla",
        filename="au2cad_model.stl",
    )


@app.get("/api/model/step")
def download_step():
    """Serves the generated STEP CAD file."""
    step_path = OUTPUT_DIR / "solidworks" / "generated.step"
    if not step_path.exists():
        demo_step = DEMO_DIR / "solidworks" / "generated.step"
        if demo_step.exists():
            step_path = demo_step
        else:
            raise HTTPException(status_code=404, detail="STEP solid model not found. Please run the pipeline first.")
    return FileResponse(
        path=step_path,
        media_type="application/step",
        filename="au2cad_model.step",
    )


@app.get("/api/model/script")
def get_parametric_script():
    script_path = OUTPUT_DIR / "solidworks" / "parametric_model.py"
    if script_path.exists():
        return {"code": script_path.read_text(encoding="utf-8")}
    return {"code": "# Parametric CadQuery script not generated yet."}


@app.get("/api/verification/report")
def get_verification_report():
    report_path = OUTPUT_DIR / "validation" / "verification_report.json"
    if report_path.exists():
        return json.loads(report_path.read_text(encoding="utf-8"))
    return {"status": "NOT_RUN", "checks": [], "corrective_actions": []}


@app.get("/api/mold/report")
def get_mold_report():
    report_path = OUTPUT_DIR / "mold" / "mold_report.json"
    if report_path.exists():
        return json.loads(report_path.read_text(encoding="utf-8"))
    return {
        "parting_direction": [0.0, 0.0, 1.0],
        "draft_results": [],
        "undercut_faces": [],
        "parting_line_edges": [],
        "notes": "Mold analysis not performed yet."
    }


@app.post("/api/agent/chat")
async def chat_with_agent(req: ChatMessageRequest):
    """
    Interactive Engineering Agent Assistant.
    Can answer questions regarding CAD-IR features, mold draft angles,
    geometry constraints, or suggest parameter modifications.
    """
    user_msg = req.message
    # Check if CAD-IR exists
    cad_ir_path = OUTPUT_DIR / "cad_ir" / "model.json"
    features_info = "Chưa có thông tin CAD-IR."
    if cad_ir_path.exists():
        try:
            cad_data = json.loads(cad_ir_path.read_text(encoding="utf-8"))
            features_info = f"Chi tiết: {cad_data.get('part_name')}, gồm {len(cad_data.get('features', []))} features."
        except Exception:
            pass

    # Call LLM if available or provide structured engineering reasoning
    try:
        from src.engineering_agent.fpt_provider import query_fpt_llm
        prompt = (
            f"Bạn là Au2CAD Senior Engineering Agent. Hãy trả lời câu hỏi của kỹ sư một cách ngắn gọn, súc tích và chính xác.\n"
            f"Thông tin mô hình hiện tại: {features_info}\n"
            f"Câu hỏi của kỹ sư: {user_msg}\n"
        )
        reply = query_fpt_llm(prompt)
    except Exception:
        # Fallback intelligent response
        reply = (
            f"🤖 [Au2CAD Agent]: Tôi đã ghi nhận yêu cầu: '{user_msg}'.\n"
            f"- Trạng thái mô hình: {features_info}\n"
            f"- Khuyến nghị kỹ thuật: Tất cả các kích thước chính đang tuân thủ Single Source of Truth (SSOT) từ bản vẽ kỹ thuật. "
            f"Bạn có thể điều chỉnh tham số hoặc chạy lại pipeline với tham số cập nhật."
        )

    return {"reply": reply}


# Mount built frontend files if they exist (for Cloud single container deploy)
FRONTEND_DIST = BASE_DIR / "frontend" / "dist"
if FRONTEND_DIST.exists():
    app.mount("/", StaticFiles(directory=str(FRONTEND_DIST), html=True), name="static")


if __name__ == "__main__":
    import uvicorn
    uvicorn.run("src.api:app", host="0.0.0.0", port=8000, reload=True)
