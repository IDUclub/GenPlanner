FROM python:3.11
LABEL authors="Ddonnyy & LeonDeTur"

EXPOSE 80

# Keeps Python from generating .pyc files in the container
ENV PYTHONDONTWRITEBYTECODE=1

# Turns off buffering for easier container logging
ENV PYTHONUNBUFFERED=1

# Enables env file
ENV APP_ENV=production

RUN apt-get update && apt-get install -y \
    python3 \
    python3-pip \
    curl \
    build-essential \
    cargo \
    && rm -rf /var/lib/apt/lists/*

# Install rustup
RUN curl --proto '=https' --tlsv1.2 -sSf https://sh.rustup.rs | sh -s -- -y

# Add rustup and Cargo binaries to PATH
ENV PATH="/root/.cargo/bin:$PATH"

# Install Poetry
RUN curl -sSL https://install.python-poetry.org | python3 -
ENV PATH="/root/.local/bin:$PATH"

# Ensure poetry is working correctly
RUN poetry --version

# Set working directory
WORKDIR /app

# Copy pyproject.toml and poetry.lock files to the container
COPY pyproject.toml /app/

# Install dependencies via Poetry
RUN poetry install --only main

# Copy the rest of the application code
COPY . /app

# Install the latest stable version of Rust
RUN rustup toolchain uninstall stable
RUN rustup toolchain install stable
RUN rustup update
RUN rustup install stable
RUN rustup default stable

# Verify installations
RUN rustc --version && poetry --version

RUN cd app/gen_planner/rust && poetry run maturin build --release
RUN poetry run pip install app/gen_planner/rust/target/wheels/rust_optimizer-*.whl

# Run the app with gunicorn
CMD ["poetry", "run", "gunicorn", "--bind", "0.0.0.0:80", "--timeout", "1000", "-k", "uvicorn.workers.UvicornWorker", "app.main:app"]