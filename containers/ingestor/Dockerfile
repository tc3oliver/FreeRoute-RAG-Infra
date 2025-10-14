FROM python:3.11-slim

WORKDIR /app

# 安裝相依
COPY services/ingestor/requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# 複製應用程式
COPY services/ingestor/app.py .
COPY services/ingestor/cli.py .

# 執行
CMD ["uvicorn", "app:app", "--host", "0.0.0.0", "--port", "8000"]
