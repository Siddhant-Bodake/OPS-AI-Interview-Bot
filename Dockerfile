FROM python:3.12-slim

WORKDIR /app

# Install system dependencies
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    && rm -rf /var/lib/apt/lists/*

# Install uv package manager
RUN pip install --no-cache-dir uv

# Copy dependency lock files
COPY pyproject.toml uv.lock ./

# Install dependencies using uv
RUN uv sync --frozen --no-dev

# Copy the rest of the application code
COPY . .

# Expose virtual environment binaries to PATH
ENV PATH="/app/.venv/bin:$PATH"

# Expose ports for both FastAPI and Streamlit
EXPOSE 8000 8501

# The default command will be overridden by docker-compose for each service
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
