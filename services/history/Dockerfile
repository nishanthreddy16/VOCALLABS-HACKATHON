FROM python:3.11-slim
WORKDIR /app
COPY services/history/requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY services/history/ .
