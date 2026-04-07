FROM python:3.11

LABEL authors="LeonDeTur"

EXPOSE 80

ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1
ENV APP_ENV=development
ENV POETRY_VERSION=1.8.3
ENV POETRY_VIRTUALENVS_CREATE=false

RUN apt-get update && apt-get install -y --no-install-recommends \
    ca-certificates \
    curl \
    && update-ca-certificates \
    && rm -rf /var/lib/apt/lists/*

RUN pip install --no-cache-dir --upgrade pip setuptools wheel
RUN pip install --no-cache-dir "poetry==$POETRY_VERSION"

RUN poetry --version

WORKDIR /app

COPY pyproject.toml poetry.lock* /app/

RUN poetry install --only main --no-interaction --no-ansi

COPY . /app

CMD ["gunicorn", "--bind", "0.0.0.0:80", "--timeout", "1000", "-k", "uvicorn.workers.UvicornWorker", "app.main:app"]