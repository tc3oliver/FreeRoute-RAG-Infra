FROM python:3.11-slim
WORKDIR /app

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

# 安裝依賴
COPY requirements.txt .
RUN pip install --no-cache-dir --upgrade pip \
 && pip install --no-cache-dir -r requirements.txt

# 放入應用
COPY app.py graph_schema.json ./

EXPOSE 8000

# 安全性：建立非 root 使用者
RUN useradd -m -u 10001 appuser
USER 10001

CMD ["uvicorn", "app:app", "--host", "0.0.0.0", "--port", "8000"]
