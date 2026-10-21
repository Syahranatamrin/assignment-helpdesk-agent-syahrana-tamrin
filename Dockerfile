FROM python:3.11-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

WORKDIR /app

# Copy requirements dulu agar layer instalasi dependency ter-cache
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy source code dan data
COPY app/ ./app/
COPY data/ ./data/

EXPOSE 8000

# API key TIDAK dimasukkan ke image; diberikan saat runtime:
#   docker run -p 8000:8000 --env-file .env it-helpdesk-assistant
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
