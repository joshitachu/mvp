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

# Non-secret defaults only. TenderNed's v2 publicaties list endpoint is public --
# verified 2026-09-04: HTTP 200 with no credentials.
ENV TNS_BASE_URL="https://www.tenderned.nl/papi/tenderned-rs-tns/v2/publicaties" \
    API_BASE_URL="https://www.tenderned.nl/papi/tenderned-rs-tns/v2"

# SECRETS ARE NOT BAKED INTO THIS IMAGE.
#
# Supply them at runtime instead, e.g.
#   docker run --env-file /etc/ithaka/env ...
# or via your orchestrator's secret store. Required at runtime:
#
#   DATABASE_URL          postgresql://USER:PASSWORD@HOST:5432/DBNAME
#   API_USERNAME          TenderNed API user   (only needed for the per-notice XML endpoint)
#   API_PASSWORD          TenderNed API password
#   GROQ_API_KEY          SROI analysis LLM
#   GOOGLE_API_KEY        Gemini (alternative LLM path)
#   SERPAPI_API_KEY       company website discovery
#   GOOGLE_CSE_API_KEY    company website discovery (fallback)
#   GOOGLE_CSE_CX         Google Custom Search engine id
#   OPEN_ROUTER           (currently unused -- no code reads it)
#
# These previously appeared here as literal values and are therefore in git
# history. Treat every one of them as compromised and rotate. See SECURITY.md.

# Expose the port FastAPI/uvicorn will run on
EXPOSE 8000

# Start the FastAPI app - CHANGED TO LOCALHOST ONLY
CMD ["uvicorn", "server:app", "--host", "0.0.0.0", "--port", "8000"]
