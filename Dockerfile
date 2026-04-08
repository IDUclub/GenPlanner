FROM python:3.11-slim

LABEL authors="LeonDeTur"

ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1
ENV APP_ENV=development
ENV POETRY_VERSION=1.8.3
ENV POETRY_VIRTUALENVS_CREATE=false
ENV POETRY_NO_INTERACTION=1

RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    curl \
    ca-certificates \
    && update-ca-certificates \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

COPY pip.conf /etc/pip.conf

RUN python -m pip install --no-cache-dir --upgrade pip setuptools wheel
RUN python -m pip install --no-cache-dir "poetry==${POETRY_VERSION}"

COPY pyproject.toml poetry.lock* /app/

# если зеркало полностью проксирует PyPI:
# RUN poetry source add --priority=primary corp-mirror http://your-mirror/simple

RUN poetry install --only main --no-ansi

COPY . /app

EXPOSE 80

CMD ["gunicorn", "--bind", "0.0.0.0:80", "--timeout", "1000", "-k", "uvicorn.workers.UvicornWorker", "app.main:app"]