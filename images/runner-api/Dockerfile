FROM python:3.12-slim

WORKDIR /app

RUN useradd -m -u 10001 appuser

COPY requirements.txt /app/requirements.txt
RUN pip install --no-cache-dir -r /app/requirements.txt

COPY runner_api /app/runner_api

USER appuser

EXPOSE 8088

CMD ["uvicorn", "runner_api.main:app", "--host", "0.0.0.0", "--port", "8088"]
