FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1
ENV TIMELINE_FOR_CHATGPT_DOCKER=1

WORKDIR /app

COPY worker/ /app/worker/
COPY settings.example.json /app/settings.example.json

RUN pip install --no-cache-dir /app/worker

HEALTHCHECK --interval=30s --timeout=10s --start-period=10s --retries=3 CMD ["python", "-c", "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8080/health', timeout=5).read()"]

ENTRYPOINT ["python", "-m", "timeline_for_chatgpt_worker.api_server"]
