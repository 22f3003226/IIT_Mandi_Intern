FROM node:20-alpine AS frontend-build
WORKDIR /frontend
COPY frontend/package.json frontend/package-lock.json ./
RUN npm ci
COPY frontend/ .
RUN npm run build

FROM python:3.11-slim
WORKDIR /app
RUN pip install --no-cache-dir uv
COPY pyproject.toml uv.lock ./
RUN uv sync --frozen --no-dev
COPY app/ ./app/
COPY --from=frontend-build /frontend/dist ./frontend/dist
ENV STORAGE_DIR=/app/storage/files
ENV DB_PATH=/app/storage/app.db
RUN useradd -m -u 1000 user && mkdir -p /app/storage/files && chown -R user:user /app
USER user
EXPOSE 7860
CMD ["uv", "run", "uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "7860"]
