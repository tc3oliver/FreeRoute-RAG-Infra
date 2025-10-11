FROM python:3.11-slim
WORKDIR /app

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

COPY services/gateway/requirements.txt /app/requirements.txt
RUN pip install --no-cache-dir --upgrade pip \
 && pip install --no-cache-dir -r /app/requirements.txt

# 僅放入應用程式檔案（schema 由 volume 掛載）
COPY services/gateway/app.py /app/app.py

EXPOSE 8000

RUN useradd -m -u 10001 appuser
USER 10001

CMD ["uvicorn", "app:app", "--host", "0.0.0.0", "--port", "8000"]
