FROM python:3.12-slim

WORKDIR /app

# Install system dependencies
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    && rm -rf /var/lib/apt/lists/*

# Copy requirements file first to leverage Docker cache
COPY requirements.txt .

# Install dependencies
RUN pip install --no-cache-dir -r requirements.txt

# Copy the rest of the application code
COPY . .

# Expose ports for both FastAPI and Streamlit
EXPOSE 8000 8501

# The default command will be overridden by docker-compose for each service
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
