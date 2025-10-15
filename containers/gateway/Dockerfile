FROM python:3.11.12-slim
WORKDIR /app

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

COPY services/gateway/requirements.txt /app/requirements.txt
RUN pip install --no-cache-dir --upgrade pip \
 && pip install --no-cache-dir -r /app/requirements.txt

# 複製整個 gateway 套件（包含 __init__.py 與模組）
COPY services/gateway /app/services/gateway

# 也允許從 /app/app.py 入口（與既有 compose 相容）
RUN ln -s /app/services/gateway/app.py /app/app.py

EXPOSE 8000

RUN useradd -m -u 10001 appuser
USER 10001

ENV PYTHONPATH=/app
CMD ["uvicorn", "services.gateway.app:app", "--host", "0.0.0.0", "--port", "8000"]
