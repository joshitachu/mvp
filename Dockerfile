# Use a slim Python base image
FROM python:3.12-slim

# Environment settings
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

# Workdir inside the container
WORKDIR /app

# Install system dependencies (for psycopg2, etc.)
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    libpq-dev \
  && rm -rf /var/lib/apt/lists/*

# Install Python dependencies
# Make sure you have a requirements.txt in the project root
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy the rest of your backend code
COPY . .

# Expose the port FastAPI/uvicorn will run on
EXPOSE 8000

# Start the FastAPI app
# 'serve:app' = file 'serve.py' with variable 'app = FastAPI(...)'
CMD ["uvicorn", "serve:app", "--host", "0.0.0.0", "--port", "8000"]
