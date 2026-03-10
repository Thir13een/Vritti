FROM python:3.12-slim

WORKDIR /app

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

# Default runtime configuration (can be overridden at docker run)
ENV LOCAL_BACKEND=ollama \
    LOCAL_MODEL=qwen3.5:2b \
    OLLAMA_BASE=http://host.docker.internal:11434 \
    LLAMACPP_BASE=http://host.docker.internal:8080 \
    NUM_CTX=1024 \
    FORCE_FALLBACK=false

EXPOSE 8000

CMD ["uvicorn", "server:app", "--host", "0.0.0.0", "--port", "8000"]

