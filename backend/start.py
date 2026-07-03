import os
import subprocess
import sys
import time
import urllib.request
import urllib.error

port = os.environ.get("PORT", "8000")
api_key = os.environ.get("PROJECT_API_KEY", "e20d66e6ce20c0ac1ed0fa8b93555c08a55eca8da663d69f")

print(f"Starting FastAPI server on port {port}...")
server_process = subprocess.Popen([
    "uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", port
])

# Poll localhost until Uvicorn responds and finishes table creation
print("Waiting for FastAPI server to finish database initialization and open port...")
server_ready = False
for attempt in range(30):
    if server_process.poll() is not None:
        print("❌ ERROR: FastAPI server crashed during startup! Check your DATABASE_URL environment variable.", file=sys.stderr)
        sys.exit(server_process.returncode or 1)
    try:
        with urllib.request.urlopen(f"http://127.0.0.1:{port}/docs", timeout=2) as response:
            if response.status == 200:
                server_ready = True
                break
    except (urllib.error.URLError, TimeoutError, ConnectionRefusedError):
        time.sleep(1)

if not server_ready:
    print("❌ ERROR: FastAPI server did not respond within 30 seconds.", file=sys.stderr)
    server_process.terminate()
    sys.exit(1)

print("✅ FastAPI server started and ready! Starting background worker process...")
worker_process = subprocess.Popen([
    "python", "-m", "app.worker.runner",
    "--api-base", f"http://127.0.0.1:{port}",
    "--api-key", api_key,
    "--name", "render-free-worker",
    "--concurrency", "10"
])

try:
    while True:
        if server_process.poll() is not None:
            print("FastAPI server stopped.", file=sys.stderr)
            worker_process.terminate()
            sys.exit(server_process.returncode or 1)
        if worker_process.poll() is not None:
            print("Worker stopped.", file=sys.stderr)
            server_process.terminate()
            sys.exit(worker_process.returncode or 1)
        time.sleep(1)
except KeyboardInterrupt:
    server_process.terminate()
    worker_process.terminate()
