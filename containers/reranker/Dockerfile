# Reranker service image: CUDA runtime + PyTorch + FastAPI app
# If you don't have NVIDIA GPU, switch to a CPU base image like python:3.11-slim and install torch cpu.
FROM pytorch/pytorch:2.8.0-cuda12.8-cudnn9-runtime

WORKDIR /app

# Avoid writing .pyc and enable unbuffered output
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    TRANSFORMERS_CACHE=/models \
    HUGGINGFACE_HUB_CACHE=/models \
    HF_HUB_DISABLE_TELEMETRY=1

# Install runtime deps for the reranker API
RUN pip install --no-cache-dir -U \
    "transformers>=4.44" "accelerate>=0.33" "sentence-transformers>=3.0" \
    "uvicorn>=0.30" "fastapi>=0.115"

# Copy app code
COPY services/reranker/server.py /app/server.py

# Expose API port
EXPOSE 8080

# Non-root user for safety
RUN useradd -m -u 10002 appuser
USER 10002

# Default envs (overridable by compose)
ENV MODEL_ID=BAAI/bge-reranker-v2-m3 \
    DEVICE=auto \
    DTYPE=bfloat16 \
    TOKEN_MAXLEN=512

CMD ["python", "-u", "/app/server.py"]
