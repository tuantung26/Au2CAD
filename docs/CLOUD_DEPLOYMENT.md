# ☁️ Hướng dẫn Host Au2CAD lên Cloud

Hệ thống Au2CAD đã được đóng gói thành mô hình **Full-Stack Single Container** (Frontend React/Three.js build tĩnh và được FastAPI Backend phục vụ trực tiếp tại port `8000`).

---

## 🚀 1. Chạy thử nghiệm Local (Không cần cài Docker)

### Bước 1: Khởi động FastAPI Backend
```bash
python -m uvicorn src.api:app --host 0.0.0.0 --port 8000 --reload
```

### Bước 2: Truy cập ứng dụng
- Mở trình duyệt tại: **`http://localhost:8000`** (Giao diện React Dashboard + 3D Viewer đã sẵn sàng).
- Swagger API Docs: **`http://localhost:8000/docs`**.

---

## 🐳 2. Triển khai bằng Docker / Docker Compose

### Cách 1: Docker Compose (Khuyên dùng cho VPS / Render / DigitalOcean)
```bash
# Build và chạy container ngầm
docker compose up -d --build

# Xem logs hoạt động
docker compose logs -f
```

### Cách 2: Docker CLI đơn
```bash
docker build -t au2cad-cloud:latest .
docker run -d -p 8000:8000 --name au2cad au2cad-cloud:latest
```

---

## 🌐 3. Hướng dẫn Deploy lên các Cloud Providers phổ biến

### A. Render.com (Web Service - Miễn phí / Tiết kiệm)
1. Đăng ký/đăng nhập [Render.com](https://render.com).
2. Chọn **New +** -> **Web Service** -> Kết nối GitHub repo `Au2CAD`.
3. Chọn **Environment**: `Docker`.
4. Thiết lập:
   - **Branch**: `main`
   - **Port**: `8000`
5. Nhập các biến môi trường trong tab **Environment Variables**:
   - `LLM_PROVIDER`: `fpt` (hoặc `gemini`, `openai`)
   - `FPT_API_KEY`: *(Key của bạn)*
6. Bấm **Deploy Web Service**. Render sẽ tự động build frontend & backend và cấp URL public HTTPS (ví dụ: `https://au2cad.onrender.com`).

---

### B. Railway.app
1. Truy cập [Railway.app](https://railway.app), chọn **New Project** -> **Deploy from GitHub repo**.
2. Railway sẽ tự động nhận diện `Dockerfile`.
3. Trong tab **Settings** -> **Networking**, nhấn **Generate Domain**.
4. Ứng dụng sẽ hoạt động tại link public được cấp.

---

### C. Hugging Face Spaces (Docker Space)
1. Tạo Space mới trên [Hugging Face Spaces](https://huggingface.co/spaces).
2. Chọn **Space SDK**: `Docker` (Blank).
3. Đẩy source code lên repo Space. Hugging Face sẽ chạy `Dockerfile` và publish ứng dụng tại port 8000.

---

### D. Google Cloud Run / AWS App Runner / Fly.io
Với bất kỳ nền tảng nào hỗ trợ Container, chỉ cần build image và deploy với cấu hình:
- **Port:** `8000`
- **CPU:** Tối thiểu 1 vCPU (khuyến nghị 2 vCPU cho xử lý mesh 3D)
- **RAM:** Tối thiểu 2GB (khuyến nghị 4GB khi tính toán CadQuery)
