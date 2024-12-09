FROM ubuntu:latest
LABEL authors="Ddonnyy & LeonDeTur"

EXPOSE 80

# Keeps Python from generating .pyc files in the container
ENV PYTHONDONTWRITEBYTECODE=1

# Turns off buffering for easier container logging
ENV PYTHONUNBUFFERED=1

# Enables env file
ENV APP_ENV=development

RUN apt-get update && apt-get install -y \
    python3 \
    python3-pip \
    curl \
    build-essential \
    && rm -rf /var/lib/apt/lists/*

RUN curl --proto '=https' --tlsv1.2 -sSf https://sh.rustup.rs | sh -s -- -y

ENV PATH="/root/.local/bin:$PATH"

RUN curl -sSL https://install.python-poetry.org | python3 -

COPY pyproject.toml poetry.lock ./

RUN poetry install
RUN poetry add maturin

COPY . .

RUN cd app/gen_planner/rust && poetry run maturin develop

CMD ["gunicorn", "--bind", "0.0.0.0:80", "-k", "uvicorn.workers.UvicornWorker", "app.main:app"]
