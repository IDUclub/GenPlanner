FROM python:3.11
LABEL authors="LeonDeTur"

EXPOSE 80

# Keeps Python from generating .pyc files in the container
ENV PYTHONDONTWRITEBYTECODE=1

# Turns off buffering for easier container logging
ENV PYTHONUNBUFFERED=1

# Enables env file
ENV APP_ENV=development

RUN apt-get update && apt-get install

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

# Run the app with gunicorn
CMD ["poetry", "run", "gunicorn", "--bind", "0.0.0.0:80", "--timeout", "1000", "-k", "uvicorn.workers.UvicornWorker", "app.main:app"]