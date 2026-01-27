FROM python:3.12-slim

WORKDIR /app

# Install dependencies
COPY pyproject.toml README.md ./
COPY src/ src/

RUN pip install --no-cache-dir .

# Run the server
EXPOSE 8080
CMD ["python", "-m", "contextcore_rabbit.cli", "--port", "8080", "--host", "0.0.0.0"]
