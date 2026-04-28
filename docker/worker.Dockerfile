FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1

WORKDIR /app

COPY worker/ /app/worker/
COPY configs/ /app/config/
COPY settings.example.json /app/settings.example.json

RUN pip install --no-cache-dir /app/worker

ENTRYPOINT ["python", "-m", "timeline_for_chatgpt_worker", "daemon", "--poll-interval", "5"]
