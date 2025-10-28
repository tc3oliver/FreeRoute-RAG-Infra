FROM python:3.11-slim

WORKDIR /app
COPY services/admin-dashboard/requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt

# 複製 admin-dashboard 與 gateway 目錄
COPY services/admin-dashboard /app/admin_dashboard
COPY services/gateway /app/gateway

# 設定 PYTHONPATH 讓跨目錄 import 可用
ENV PYTHONPATH=/app

EXPOSE 8000
CMD ["uvicorn", "admin_dashboard.app:app", "--host", "0.0.0.0", "--port", "8000"]
