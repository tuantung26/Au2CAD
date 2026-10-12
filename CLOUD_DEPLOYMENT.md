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

### D. Hướng dẫn chi tiết triển khai lên Amazon Web Services (AWS)

#### 1. Checklist cần chuẩn bị trước khi deploy lên AWS
- **Tài khoản AWS:** Đã kích hoạt thẻ thanh toán và có IAM User quyền phù hợp (hoặc AdministratorAccess).
- **AWS CLI (Tùy chọn):** Đã cài đặt và chạy `aws configure` để cấu hình Access Key / Secret Key.
- **Cấu hình phần cứng tối thiểu (Specs):**
  - **CPU:** Tối thiểu 1 vCPU (khuyên dùng 2 vCPU).
  - **RAM:** Tối thiểu **1 GB – 2 GB RAM** (Hệ thống đã tinh gọn toàn bộ pipeline sang mô hình Drawing-led SSOT, loại bỏ thư viện nặng Open3D/tiền xử lý mesh lớn, giúp container chạy nhẹ nhàng và không lo tràn RAM/OOM).
  - **Ổ cứng (Disk):** 10–20 GB SSD trở lên.
- **Biến môi trường (.env):**
  - `LLM_PROVIDER`: `fpt` (hoặc `gemini`, `openai`)
  - `FPT_API_KEY`: API Key FPT AI
  - `PORT`: `8000`

---

#### 2. Phương án 1: AWS Lightsail (Khuyên dùng — Đơn giản & Tiết kiệm nhất)
*Lightsail là VPS trọn gói của AWS với mức giá cố định ($5–$10/tháng), giao diện quản lý trực quan và cấp sẵn IP tĩnh.*

1. Đăng nhập [AWS Lightsail Console](https://lightsail.aws.amazon.com/).
2. Bấm **Create instance**:
   - Nền tảng: **Linux/Unix** -> Blueprint: **OS Only** -> **Ubuntu 22.04 LTS** (hoặc 24.04).
   - Chọn gói: **$5/tháng** (1 GB RAM, 1 vCPU) hoặc tốt nhất là **$10/tháng** (2 GB RAM, 1 vCPU / 2 vCPU).
3. Cấu hình mạng:
   - Vào tab **Networking** -> Bấm **Attach static IP** để gắn IP cố định.
   - Tại mục **IPv4 Firewall**, bấm **Add rule** -> Mở cổng TCP **`8000`** (Custom) cùng với cổng **`80`** (HTTP) và **`443`** (HTTPS).
4. Kết nối vào máy chủ (qua nút SSH trên web hoặc terminal) và chạy các lệnh:
   ```bash
   # Cập nhật và cài đặt Docker + Docker Compose
   sudo apt-get update
   sudo apt-get install -y docker.io docker-compose-v2 git
   sudo usermod -aG docker $USER
   newgrp docker

   # Clone repo dự án
   git clone https://github.com/tuantung26/Au2CAD.git
   cd Au2CAD

   # Thiết lập file biến môi trường
   cp .env.example .env
   nano .env   # Cập nhật FPT_API_KEY

   # Khởi chạy dịch vụ container
   docker compose up -d --build
   ```
5. Mở trình duyệt và truy cập: `http://<STATIC_IP_CUA_BAN>:8000`.

---

#### 3. Phương án 2: AWS App Runner (Serverless Container — Auto-scaling)
*Chạy trực tiếp Docker container mà không cần quản lý máy chủ Linux, tự động cấp HTTPS miễn phí.*

1. **Đẩy Docker Image lên Amazon ECR (Elastic Container Registry):**
   ```bash
   # Đăng nhập ECR
   aws ecr get-login-password --region ap-southeast-1 | docker login --username AWS --password-stdin <ACCOUNT_ID>.dkr.ecr.ap-southeast-1.amazonaws.com

   # Tạo kho chứa image
   aws ecr create-repository --repository-name au2cad

   # Build và tag image
   docker build -t au2cad:latest .
   docker tag au2cad:latest <ACCOUNT_ID>.dkr.ecr.ap-southeast-1.amazonaws.com/au2cad:latest

   # Đẩy image lên AWS ECR
   docker push <ACCOUNT_ID>.dkr.ecr.ap-southeast-1.amazonaws.com/au2cad:latest
   ```
2. **Khởi tạo dịch vụ trên AWS App Runner:**
   - Vào [AWS App Runner Console](https://console.aws.amazon.com/apprunner) -> Bấm **Create service**.
   - **Source:** Chọn **Container registry** -> **Amazon ECR** -> Chọn repository `au2cad` và tag `latest`.
   - **Service settings:**
     - **Port:** `8000`
     - **vCPU:** 2 vCPU
     - **Memory:** 4 GB
     - **Environment variables:** Điền `FPT_API_KEY` và `LLM_PROVIDER`.
   - Bấm **Create & Deploy**. Sau vài phút, hệ thống sẽ cấp đường dẫn HTTPS công khai tự động (ví dụ: `https://xyz.ap-southeast-1.awsapprunner.com`).

---

#### 4. Cấu hình Tên miền riêng & Chứng chỉ SSL (Domain & HTTPS)
- **Đối với App Runner:** Vào tab **Custom domains**, nhập tên miền của bạn và thêm các bản ghi CNAME được cung cấp vào DNS (Route 53 hoặc Cloudflare).
- **Đối với Lightsail / EC2:** Cài đặt Nginx làm Reverse Proxy và Certbot để lấy chứng chỉ SSL Let's Encrypt miễn phí:
  ```bash
  sudo apt-get install -y nginx certbot python3-certbot-nginx
  ```
  Cấu hình Nginx proxy pass cổng `8000` về domain rồi kích hoạt SSL:
  ```bash
  sudo certbot --nginx -d yourdomain.com
  ```
