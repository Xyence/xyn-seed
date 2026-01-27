FROM python:3.12-slim

WORKDIR /app

RUN useradd -m -u 10001 appuser

COPY requirements.txt /app/requirements.txt
RUN pip install --no-cache-dir -r /app/requirements.txt

COPY runner_worker /app/runner_worker

USER appuser

CMD ["python", "-m", "runner_worker.worker"]
