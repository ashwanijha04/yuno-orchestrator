FROM python:3.12-slim

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_NO_CACHE_DIR=1

WORKDIR /app

# Hatchling needs the package source present to build the editable install,
# so copy everything before installing. Source is also bind-mounted in compose
# for live reload, and the editable install picks up those changes.
COPY . .

RUN pip install --upgrade pip && pip install -e ".[dev]"

# extremis (long-term agent memory) installed WITHOUT its deps so we don't drag
# in sentence-transformers/torch — we use the OpenAI embedder, whose code path
# never imports sentence-transformers (it's a lazy import). The lean runtime deps
# extremis actually needs (numpy, psycopg2, pgvector, openai) are in pyproject.
RUN pip install --no-deps extremis==0.3.1

EXPOSE 8000

# Default command runs the control plane; the worker service overrides it.
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000", "--reload"]
