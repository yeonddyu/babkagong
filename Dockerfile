FROM node:22-bookworm-slim AS frontend
WORKDIR /build/frontend
COPY frontend/package.json frontend/package-lock.json ./
RUN npm ci
COPY frontend/index.html frontend/tsconfig*.json frontend/vite.config.ts ./
COPY frontend/src ./src
ARG VITE_KAKAO_MAP_KEY
ARG VITE_BABKAGONG_PUBLIC_DEMO=1
RUN npm run build

FROM python:3.12-slim-bookworm
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    BABKAGONG_FRONTEND_DIR=/srv/frontend \
    BABKAGONG_PUBLIC_DEMO=1 \
    BABKAGONG_WARMUP=0 \
    BABKAGONG_CACHE_DIR=/data/cache \
    DATABASE_URL=sqlite:////data/babkagong.db

WORKDIR /srv/backend
COPY backend/requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt
COPY backend/app ./app
COPY --from=frontend /build/frontend/dist /srv/frontend
EXPOSE 8000
CMD ["sh", "-c", "exec uvicorn app.main:app --host 0.0.0.0 --port \"${PORT:-8000}\""]
