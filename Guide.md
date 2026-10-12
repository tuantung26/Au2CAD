# Au2CAD — Developer Guide

> **Agentic AI System for Automated Reverse Engineering and Preliminary Mold Design from Multi-View Images**

---

## 1. Mục tiêu dự án

| | |
|---|---|
| **Đầu vào** | 20–30 ảnh chụp vật thể vật lý từ nhiều góc. Có thể kèm theo: bản vẽ kỹ thuật, mô tả kỹ sư, yêu cầu vật liệu / sản xuất. |
| **Đầu ra** | 3D reconstruction · Parametric CAD model · CAD construction sequence · `.SLDPRT` (hoặc `.STEP` cho demo) · Báo cáo sai lệch Mesh vs CAD · Phân tích Draft / Parting Direction / Parting Line / Core / Cavity · Engineer review report |

> **Nguyên tắc cốt lõi:** AI không "đoán" file CAD — nó xây dựng một **chuỗi quyết định có thể kiểm chứng** qua mỗi bước.

---

## 2. Kiến trúc tổng thể

```
Multi-view Images (20-30 ảnh)
          │
          ▼
┌─────────────────────┐
│  3D Reconstruction  │  Hunyuan3D (API / local)
│  Image → PointCloud │
│        → Mesh       │
└──────────┬──────────┘
           │
           ▼
┌─────────────────────┐
│  Mesh Preprocessing │  trimesh
│  - Remove noise     │
│  - Fill holes       │
│  - Watertight       │
│  - Taubin smoothing │
│  - Decimation       │
│  - Scale alignment  │
└──────────┬──────────┘
           │
           ▼
┌─────────────────────┐
│      CADFit         │  Geometry Engine (subprocess)
│  Mesh → CAD Program │
│  EXTRUDE / REVOLVE  │
│  FILLET / CHAMFER   │
│  UNION / CUT        │
└──────────┬──────────┘
           │
           ▼
┌─────────────────────┐
│      CAD-IR         │  JSON Intermediate Representation
│  Feature Graph      │
│  Dimensions         │
│  References         │
│  Constraints        │
└──────────┬──────────┘
           │
    ┌──────┴──────┐
    ▼             ▼
Engineering    Geometry
  Agent        Validator
  (LLM)       (trimesh)
    │             │
    └──────┬──────┘
           │
           ▼
┌─────────────────────┐
│  CadQuery Adapter   │  (SolidWorks Adapter khi có licence)
│  CAD-IR → STEP      │
└──────────┬──────────┘
           │
           ▼
     .STEP / .SLDPRT
           │
           ▼
┌─────────────────────┐
│  CAD Validation     │  IoU · Chamfer · Dimension Error
│  + Agent Loop       │
└──────────┬──────────┘
           │
        PASS / FAIL
           │
      ┌────┴────┐
    FAIL       PASS
      │          │
      ▼          ▼
  Agent Repair  Mold Design
                    │
         ┌──────────┼──────────┐
         ▼          ▼          ▼
      Draft      Parting    Core /
     Analysis    Line/Dir   Cavity
                    │
                    ▼
           Engineer Review
```

---

## 3. Pipeline chi tiết — từng bước

### Bước 1 — Multi-view Image Acquisition
- Chụp vật thể từ **10 hướng chuẩn**: Front, Front-Left, Left, Back-Left, Back, Back-Right, Right, Front-Right, Top, Bottom.
- Thực tế nên có **20–30 ảnh** để coverage tốt.
- Kèm theo nếu có: `technical_drawing.pdf`, `description.txt`, yêu cầu sản xuất.

### Bước 2 — 3D Reconstruction
- **Công cụ:** Hunyuan3D (API hoặc local inference).
- **Input:** Nhiều ảnh 2D.
- **Output:** Point Cloud → Surface Reconstruction → **Mesh** (`.obj`, `.stl`, `.ply`).
- Tại sao multi-view tốt hơn 1 ảnh? Paper CADFit demo `1 image → Hunyuan3D → Mesh → CADFit`. Dự án này mở rộng thành `N images → multi-view recon → 3D geometry` — phù hợp hơn cho reverse engineering vật thể thật.

### Bước 3 — Mesh Preprocessing
Pipeline xử lý mesh thô trước khi đưa vào CADFit:

```
Raw Mesh
   ↓  Remove duplicate / degenerate faces
   ↓  Fill holes → Watertight
   ↓  Taubin smoothing  (λ=0.5, ν=−0.53)
   ↓  Decimation  (target: 50,000 faces)
   ↓  Scale alignment
Clean Mesh
```

> **Tại sao quan trọng?** Số liệu từ paper CADFit:
>
> | Input | IoU | Runtime |
> |---|---|---|
> | Noisy mesh | 0.876 | 1255 s |
> | Smoothed + decimated | **0.914** | **456 s** |
>
> Preprocessing không chỉ tăng accuracy mà còn giảm runtime gần **3×**.

### Bước 4 — CADFit (Geometry Engine)
- **CADFit** nhận watertight mesh và tìm CAD program tối ưu hoá IoU giữa solid tạo ra và mesh mục tiêu.
- **Residual Reconstruction:** Nếu CAD ban đầu chưa khớp với mesh:
  - Phần thiếu → thêm bằng `UNION`
  - Phần thừa → bớt bằng `CUT`
  - Lặp cho đến khi residual đủ nhỏ.
- **Output:** `program.py` (CadQuery script) + `result.step` + `metrics.json`

> **Giới hạn cần biết:** CADFit hiện hỗ trợ `EXTRUDE, REVOLVE, FILLET, CHAMFER, UNION, CUT`. Chưa hỗ trợ tốt `LOFT, SWEEP, PATTERN` và geometry có bề mặt cong phức tạp.

### Bước 5 — CAD-IR (Intermediate Representation)
CADFit xuất ra CadQuery/OpenCascade representation. Vì target là SolidWorks API, cần một **lớp trung gian** làm contract giữa hai thế giới.

**Schema CAD-IR (JSON):**
```json
{
  "part_name": "bracket",
  "units": "mm",
  "features": [
    {
      "id": "F1",
      "type": "EXTRUDE",
      "depth": 50,
      "parameters": [{"name": "depth", "value": 50, "unit": "mm"}]
    },
    {
      "id": "F2",
      "type": "HOLE",
      "diameter": 10,
      "through_all": true
    },
    {
      "id": "F3",
      "type": "FILLET",
      "radius": 3
    }
  ]
}
```

**5 nhóm thông tin trong CAD-IR:**

| Nhóm | Nội dung |
|---|---|
| **Geometry** | Plane, Axis, Point, Line, Circle, Arc, Profile, Face, Edge, Vertex |
| **Features** | Extrude, Revolve, Cut, Union, Fillet, Chamfer, Hole, Shell, Draft, Pattern |
| **Parameters** | length, width, height, diameter, radius, angle, thickness, depth |
| **References** | Liên kết giữa các feature (e.g. Hole1 → Face3 → Sketch2) |
| **Constraints** | parallel, perpendicular, coincident, concentric, symmetric, distance, angle |

### Bước 6 — Engineering Agent (LangGraph + LLM)
**LLM không làm:** "Tự nhìn mesh và viết 2.000 dòng SolidWorks API."

**LLM làm:** Đọc CAD-IR → Reasoning → Propose → Execute → Validate.

**Graph topology:**
```
[START]
   │
   ▼
 REASON       ← LLM đọc CAD-IR + context + validation errors
   │
   ▼
 BUILD_CAD    ← CadQuery Adapter dựng STEP từ CAD-IR
   │
   ▼
 VALIDATE     ← Geometry Validator tính IoU, Chamfer, Dimension error
   │
 ┌─┴─┐
FAIL PASS
 │     │
 ▼     ▼
DIAGNOSE  [END]
 │
 ▼
REASON (loop, tối đa 5 lần)
```

**Ví dụ Agent reasoning:**
```
CADFit:            Hole diameter = 9.87 mm
Technical drawing: Hole diameter = 10 mm
Agent phát hiện:   difference = 0.13 mm
Agent đề xuất:     Normalize Hole1.diameter: 9.87 → 10.00 mm
→ Thay đổi này đi qua Validation trước khi apply.
```

### Bước 7 — CadQuery Adapter (→ SolidWorks Adapter)
- **Demo:** CadQuery/OpenCascade → export `.STEP` (không cần SolidWorks licence).
- **Production:** Swap sang `SolidWorksAdapter` cùng interface, gọi Win32 COM API tạo `.SLDPRT`.

### Bước 8 — Geometry Validator

| Metric | Ngưỡng mặc định |
|---|---|
| Volumetric IoU (voxel) | ≥ 0.90 |
| Chamfer Distance | Càng thấp càng tốt |
| Dimension MAE per feature | ≤ 0.5 mm |
| Topology (watertight, volume) | PASS |

**Status logic:**
- `PASS` → IoU ≥ threshold, không có topology error
- `WARNING` → IoU OK nhưng có dimension error nhỏ
- `FAIL` → IoU < threshold hoặc có topology error → quay lại Agent

### Bước 9 — Preliminary Mold Design
Chỉ bắt đầu sau khi CAD đã PASS validation. Không thiết kế khuôn từ mesh thô.

**Draft Analysis:**
```
Mỗi face → tính góc giữa face normal và mold direction
  ≥ 1°      → PASS    (green)
  0° – 1°   → WARNING (yellow — low draft)
  < −0.5°   → FAIL    (red = undercut)
```

**Parting Direction:**
- Đánh giá 6 hướng ứng viên (+X, −X, +Y, −Y, +Z, −Z).
- Score = fraction of faces with positive draft angle.
- Chọn direction có score tốt nhất.

**Parting Line:**
- Tìm các cạnh (edges) nằm trên ranh giới giữa face nhìn thấy từ cavity và face nhìn thấy từ core.

**Core / Cavity:**
- Phân loại từng face là cavity-side hoặc core-side dựa trên dot product với parting direction.

---

## 4. Tech Stack

| Tầng | Công nghệ |
|---|---|
| 3D Reconstruction | **Hunyuan3D** (API hoặc local) |
| Mesh Processing | **trimesh** |
| Geometry ops / Validation | **Open3D + trimesh + scipy** |
| CAD Reconstruction | **CADFit** (subprocess wrapper) |
| CAD Intermediate Repr. | **Pydantic** JSON schema (tự build) |
| CAD Execution (demo) | **CadQuery + OpenCascade** |
| CAD Execution (prod) | SolidWorks COM API (`pywin32`) |
| Agent Framework | **LangGraph** |
| LLM | *(provider-agnostic — xem mục 5)* |
| CLI / Console | **Typer + Rich** |
| Package manager | **pip + requirements.txt** |

---

## 5. Cấu hình LLM Provider

Mở file `.env` (tạo từ `.env.example`) và điền thông tin:

```bash
# Chọn một trong các provider sau:
LLM_PROVIDER=openai          # hoặc: anthropic | google | azure_openai

# Model name
LLM_MODEL=gpt-4o             # gpt-4o | claude-3-5-sonnet | gemini-2.0-flash | ...

# API Key tương ứng với provider đã chọn:
OPENAI_API_KEY=sk-...
# ANTHROPIC_API_KEY=sk-ant-...
# GOOGLE_API_KEY=...
```

> Nếu chưa điền LLM provider, pipeline vẫn chạy được với flag `--skip-agent`.

---

## 6. Cấu trúc thư mục

```
Au2CAD/
│
├── .env                              ← Cấu hình thực tế (KHÔNG commit lên git)
├── .env.example                      ← Template cấu hình
├── requirements.txt
├── README.md
├── Guide.md                          ← File này
│
├── src/
│   ├── config.py                     ← Đọc tất cả config từ .env
│   ├── models.py                     ← Pydantic shared models
│   ├── main.py                       ← CLI entry point (Typer)
│   │
│   ├── reconstruction/               ← (placeholder) Hunyuan3D integration
│   │
│   ├── mesh_preprocessing/
│   │   └── preprocessor.py           ← MeshPreprocessor
│   │
│   ├── cadfit_wrapper/
│   │   ├── runner.py                 ← CADFitRunner + MockCADFitRunner
│   │   └── parser.py                 ← AST parser: CadQuery script → CADIR
│   │
│   ├── engineering_agent/
│   │   └── agent.py                  ← LangGraph agent loop
│   │
│   ├── solidworks_adapter/
│   │   └── cadquery_adapter.py       ← CADIR → CadQuery → STEP
│   │
│   ├── validation/
│   │   └── geometry_validator.py     ← IoU, Chamfer, Dimension, Topology
│   │
│   └── mold_design/
│       └── analyst.py                ← Draft analysis, Parting, Core/Cavity
│
├── demo_part/
│   ├── input/
│   │   ├── images/                   ← Ảnh đầu vào (front.jpg, left.jpg, …)
│   │   ├── scan/                     ← Scan mesh nếu có
│   │   ├── drawing/                  ← technical_drawing.pdf
│   │   └── description.txt
│   ├── reconstruction/               ← raw_mesh.obj, clean_mesh.obj
│   ├── cadfit/                       ← program.py, result.step, metrics.json
│   ├── cad_ir/                       ← model.json
│   ├── solidworks/                   ← generated.STEP, generated.stl
│   ├── validation/                   ← report.json
│   └── mold/
│       ├── draft_analysis/
│       ├── parting_line/
│       ├── core/
│       └── cavity/
│
└── ground_truth/
    ├── original.SLDPRT
    ├── original.STEP
    └── specification.json            ← Kích thước chuẩn để đo lường sai số
```

---

## 7. Cách chạy

```bash
# Cài đặt dependencies
pip install -r requirements.txt

# Demo nhanh (không cần CADFit, không cần LLM)
python src/main.py \
  --input demo_part/reconstruction/raw_mesh.obj \
  --mock-cadfit \
  --skip-agent

# Chạy với Mock CADFit + LLM Agent (cần điền .env)
python src/main.py \
  --input demo_part/reconstruction/raw_mesh.obj \
  --mock-cadfit \
  --context "Mechanical bracket with 2 mounting holes, 5mm thickness"

# Chạy đầy đủ (cần CADFit cài đặt trong third_party/CADFit)
python src/main.py \
  --input demo_part/reconstruction/raw_mesh.obj \
  --output output/bracket_run1

# Xem tất cả options
python src/main.py --help
```

---

## 8. Phân chia trách nhiệm

| Component | Nhiệm vụ | Ghi chú |
|---|---|---|
| Multi-view reconstruction | Ảnh → 3D | Hunyuan3D |
| Mesh preprocessing | Làm sạch mesh | `mesh_preprocessing/preprocessor.py` |
| **CADFit** | Mesh → CAD program | *Adopted from paper — không phải contribution của dự án* |
| CAD-IR parser | CadQuery → JSON schema | `cadfit_wrapper/parser.py` |
| Engineering Agent | Reasoning / planning / patching | `engineering_agent/agent.py` |
| CadQuery Adapter | CAD-IR → STEP | `solidworks_adapter/cadquery_adapter.py` |
| Geometry Validator | IoU / Chamfer / Dimensions | `validation/geometry_validator.py` |
| Mold Analyst | Draft / Parting / Core-Cavity | `mold_design/analyst.py` |
| Engineer | Final approval | Con người |

> **Contribution của dự án** nằm ở: multi-view physical input pipeline, CAD-IR layer, Engineering Agent reasoning loop, SolidWorks/CadQuery integration, validation-repair loop, và preliminary mold design module.

---

## 9. Phân giai đoạn MVP

| Phase | Mục tiêu | Status |
|---|---|---|
| **Phase 1** — Foundation | Config, Pydantic models, requirements | ✅ Done |
| **Phase 2** — Mesh Preprocessing | Watertight, smooth, decimate | ✅ Done |
| **Phase 3** — CADFit Wrapper | subprocess runner + mock + parser | ✅ Done |
| **Phase 4** — CadQuery Adapter | CADIR → STEP | ✅ Done |
| **Phase 5** — Validation | IoU, Chamfer, Dimension, Topology | ✅ Done |
| **Phase 6** — Engineering Agent | LangGraph loop, provider-agnostic | ✅ Done |
| **Phase 7** — Mold Design | Draft, Parting, Core/Cavity | ✅ Done |
| **Phase 8** — 3D Reconstruction | Hunyuan3D integration | ⏳ Pending |
| **Phase 9** — SolidWorks Adapter | Win32 COM API → `.SLDPRT` | ⏳ Pending |
| **Phase 10** — End-to-end test | Chạy với bracket thật | ⏳ Pending |

---

## 10. Bộ metric báo cáo cuối

| Tầng | Metric |
|---|---|
| 3D Reconstruction | Chamfer Distance, Mesh completeness |
| CAD Reconstruction | IoU, Chamfer Distance, Invalid Ratio |
| Engineering Accuracy | Dimension MAE (mm), Feature accuracy, Hole error, Fillet error |
| Agent Performance | Task success rate, Iterations to converge, Validation pass rate |
| Mold Design | Draft violation count, Undercut count, Parting-line quality, Core/Cavity validity |

---

## 11. Object demo được khuyến nghị

**Mechanical Bracket** — phù hợp nhất với operator set hiện tại của CADFit:

```
       ┌───────────┐
       │     ○     │
       │           │
       └─────┬─────┘
             │
       ○     │     ○
    ┌───────────────┐
    │               │
    └───────────────┘
```

| ✅ Nên dùng | ❌ Tránh (cho demo đầu tiên) |
|---|---|
| Planar faces | Bottle / Spoon |
| Extrusion, Cut, Hole | Car body |
| Fillet, Chamfer | Human figure |
| Rectangular base | Highly curved surface |

---

*Guide này được tạo từ cuộc hội thoại thiết kế kiến trúc — cập nhật khi có thay đổi.*
