# Stage 1: build
FROM python:3.12-slim AS builder
WORKDIR /build
COPY pyproject.toml README.md ./
COPY analyzer/ analyzer/
RUN pip install --no-cache-dir build && python -m build --wheel

# Stage 2: runtime
FROM python:3.12-slim
LABEL org.opencontainers.image.source="https://github.com/aks-builds/ai-test-failure-analyzer"
LABEL org.opencontainers.image.description="AI-powered test failure analyzer"
WORKDIR /workspace
COPY --from=builder /build/dist/*.whl /tmp/
RUN pip install --no-cache-dir /tmp/*.whl && rm /tmp/*.whl
ENTRYPOINT ["ai-analyze"]
CMD ["--help"]
