# Agentic AI System for Automated Reverse Engineering and Preliminary Mold Design from Multi-View Images

## Mục tiêu của dự án
Hệ thống AI ứng dụng trong việc tự động hóa reverse engineering và thiết kế khuôn sơ bộ từ ảnh nhiều góc của một sản phẩm vật lý (multi-view images). 

## Kiến trúc hệ thống

1. **Tầng 1 — Multi-view Image Acquisition**: 
   - Đầu vào 20-30 ảnh của vật thể từ nhiều góc.
2. **Tầng 2 — 3D Reconstruction**:
   - Tái tạo 3D (Point Cloud -> Surface Reconstruction -> Mesh).
3. **Tầng 3 — Mesh Preprocessing**:
   - Xử lý Mesh thô (Remove noise, hole repairing, watertight, smoothing, decimation) để tạo Clean Mesh.
4. **Tầng 4 — CADFit Geometry Engine**:
   - Sử dụng CADFit làm thuật toán tái tạo Mesh-to-CAD (EXTRUDE, REVOLVE, FILLET, CHAMFER, UNION, CUT).
5. **Tầng 5 — CAD-IR (CAD Intermediate Representation)**:
   - Đại diện trung gian cho Geometry, Features, Parameters, References, và Constraints.
6. **Tầng 6 — Engineering Agent (LLM)**:
   - Suy luận (Reasoning/Planning) dựa trên CAD-IR, mô tả của kỹ sư, và bản vẽ kỹ thuật để đưa ra quyết định kỹ thuật.
7. **Tầng 7 — SolidWorks Adapter & Execution**:
   - Dịch từ CAD-IR sang SolidWorks API để tạo ra file `.SLDPRT` (Parametric CAD).
8. **Tầng 8 — Geometry Validator**:
   - Phân tích sai lệch giữa Mesh ban đầu và CAD được tạo (Metric: IoU, Chamfer Distance, Error). Cung cấp Agent Loop để sửa lỗi (Validation Agent).
9. **Tầng 9 — Preliminary Mold Design Agent**:
   - Thiết kế khuôn sơ bộ: Phân tích góc thoát khuôn (Draft Analysis), hướng mở khuôn (Parting Direction), đường phân khuôn (Parting Line), và Lõi/Khuôn (Core/Cavity).

## Cấu trúc thư mục dự án (Demo)

Dự án này sử dụng Mechanical Bracket làm mẫu demo (hạn chế các vật có bề mặt cong phức tạp cho giai đoạn MVP).

- `demo_part/`: Dataset sample hoàn chỉnh
  - `input/`: Ảnh input, scan mesh, bản vẽ (drawing)
  - `reconstruction/`: Point cloud, mesh thô, và mesh sau tiền xử lý
  - `cadfit/`: CAD program và CAD step sinh ra từ CADFit
  - `cad_ir/`: Mô hình trung gian (JSON format)
  - `solidworks/`: File output (SLDPRT, STEP)
  - `validation/`: Báo cáo validation và biểu đồ
  - `mold/`: Các kết quả phân tích khuôn (draft analysis, parting line, core, cavity)
- `ground_truth/`: Ground truth models và specs để đo lường
- `src/`: Mã nguồn theo từng pipeline
  - `reconstruction/`
  - `mesh_preprocessing/`
  - `cadfit_wrapper/`
  - `cad_ir/`
  - `engineering_agent/`
  - `solidworks_adapter/`
  - `validation/`
  - `mold_design/`
