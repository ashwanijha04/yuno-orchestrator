FROM python:3.12-slim

ENV PYTHONUNBUFFERED=1
WORKDIR /app
COPY runner.py .

# Runs as a non-root user; network is disabled at the compose level.
RUN useradd --create-home --uid 10001 sandbox
USER sandbox

CMD ["python", "runner.py"]
