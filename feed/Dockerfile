FROM python:3.12.3-slim

WORKDIR /app

# curl: used by the container healthcheck.
RUN apt-get update && apt-get install -y --no-install-recommends curl \
  && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

EXPOSE 5000

# IMPORTANT: ONE SINGLE PROCESS/WORKER. The feed's coordination state
# (refresh lock, rate-limit, double-purchase guard, 2FA state, watchdog ticket)
# lives in memory within the process: with multiple workers it would break silently.
# Do not set --workers > 1 nor scale to multiple replicas without moving that
# state to Redis. See SECURITY_AUDIT (N-1, VLF-03/04/05) and session_refresh.py.
CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "5000", "--workers", "1"]
