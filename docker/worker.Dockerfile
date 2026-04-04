FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1

WORKDIR /app

COPY worker/ /app/worker/
COPY configs/ /app/config/

RUN pip install --no-cache-dir /app/worker

ENTRYPOINT ["python", "-m", "chatgpt2timeline_worker", "daemon", "--poll-interval", "5"]
