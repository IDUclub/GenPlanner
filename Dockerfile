FROM python:3.11

LABEL authors="LeonDeTur"

EXPOSE 80

ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1
ENV APP_ENV=development
ENV POETRY_VERSION=1.8.3
ENV POETRY_VIRTUALENVS_CREATE=false
ENV PIP_DEFAULT_TIMEOUT=120
ENV PIP_DISABLE_PIP_VERSION_CHECK=1
ENV POETRY_NO_INTERACTION=1

RUN apt-get update && apt-get install -y --no-install-recommends \
    ca-certificates \
    curl \
    && update-ca-certificates \
    && rm -rf /var/lib/apt/lists/*

RUN python -m pip install --no-cache-dir --upgrade pip setuptools wheel

RUN for i in 1 2 3; do \
      pip install --no-cache-dir \
        --index-url https://pypi.org/simple \
        --retries 10 \
        "poetry==${POETRY_VERSION}" && break; \
      echo "Poetry install failed, retrying..."; \
      sleep 10; \
    done

RUN poetry --version

WORKDIR /app

COPY pyproject.toml poetry.lock* /app/

RUN for i in 1 2 3; do \
      poetry install --only main --no-ansi && break; \
      echo "Poetry dependencies install failed, retrying..."; \
      sleep 10; \
    done

COPY . /app

CMD ["gunicorn", "--bind", "0.0.0.0:80", "--timeout", "1000", "-k", "uvicorn.workers.UvicornWorker", "app.main:app"]