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
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy the rest of your backend code
COPY . .

# Set environment variables
ENV SERPAPI_API_KEY="3757554d02872ebf5aa117d04584f92d6f6020b1dd46ab840f005ba4aa1f0aa2" \
    OPEN_ROUTER="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" \
    GOOGLE_API_KEY="AIzaSyA23-6UhmTE4XZR_bdVKbF0BgT9p_ro2A0" \
    GROQ_API_KEY="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" \
    TNS_BASE_URL="https://www.tenderned.nl/papi/tenderned-rs-tns/v2/publicaties" \
    API_BASE_URL="https://www.tenderned.nl/papi/tenderned-rs-tns/v2" \
    API_USERNAME="TNXML08248" \
    API_PASSWORD="aapVqSgKB" \
    DATABASE_URL="postgresql://postgres:voetbal123@localhost:5432/supabase_subset" \
    GOOGLE_CSE_API_KEY="AIzaSyAhm0u-wtyH1fQIn8Zc60GVBYw9ZZ8TGDs" \
    GOOGLE_CSE_CX="921c64bea8b8b4805" \
    SALESFORCE_LOGIN_URL="https://login.salesforce.com" \
    SALESFORCE_USERNAME="joshikabel@gmail.com" \
    SALESFORCE_PASSWORD="Joshitachu17k_123" \
    SALESFORCE_SECURITY_TOKEN="rvca2GFpWrR3yNAloUbRIno9"

# Expose the port FastAPI/uvicorn will run on
EXPOSE 8000

# Start the FastAPI app - CHANGED TO LOCALHOST ONLY
CMD ["uvicorn", "server:app", "--host", "127.0.0.1", "--port", "8000"]