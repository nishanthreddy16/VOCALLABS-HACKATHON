FROM python:3.11-slim
WORKDIR /app
COPY services/reconcile/requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY services/reconcile/ .
COPY eval/ ./eval/
