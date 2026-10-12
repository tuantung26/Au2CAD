# syntax=docker/dockerfile:1
# ─────────────────────────────────────────────────────────────
# Stage 1: Build Frontend (Vite + React + Three.js)
# ─────────────────────────────────────────────────────────────
FROM node:20-slim AS frontend-builder
WORKDIR /app/frontend

COPY frontend/package*.json ./
RUN npm ci

COPY frontend/ ./
RUN npm run build

# ─────────────────────────────────────────────────────────────
# Stage 2: Python Backend & CadQuery Runtime
# ─────────────────────────────────────────────────────────────
FROM python:3.12-slim

# System dependencies for Open3D, Trimesh, CadQuery / OpenCASCADE & OpenCV
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    libgl1 \
    libglib2.0-0 \
    libgomp1 \
    curl \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Install Python requirements
COPY requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt

# Copy source code and demo data
COPY src/ ./src/
COPY demo_part/ ./demo_part/
COPY ground_truth/ ./ground_truth/
COPY .env.example ./.env

# Copy built frontend into container
COPY --from=frontend-builder /app/frontend/dist ./frontend/dist

# Ensure outputs and uploads directory exist
RUN mkdir -p /app/output /app/uploads

EXPOSE 8000

ENV PORT=8000
ENV PYTHONUNBUFFERED=1

# Healthcheck
HEALTHCHECK --interval=30s --timeout=10s --start-period=5s --retries=3 \
  CMD curl -f http://localhost:8000/api/health || exit 1

CMD ["uvicorn", "src.api:app", "--host", "0.0.0.0", "--port", "8000"]
