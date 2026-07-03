import os
import subprocess
import time

port = os.environ.get("PORT", "8000")
api_key = os.environ.get("PROJECT_API_KEY", "e20d66e6ce20c0ac1ed0fa8b93555c08a55eca8da663d69f")

print(f"Starting FastAPI server on port {port}...")
server_process = subprocess.Popen([
    "uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", port
])

# Give Uvicorn 3 seconds to bind before starting the background worker
time.sleep(3)

print("Starting built-in background worker...")
worker_process = subprocess.Popen([
    "python", "-m", "app.worker.runner",
    "--api-base", f"http://127.0.0.1:{port}",
    "--api-key", api_key,
    "--name", "render-free-worker",
    "--concurrency", "10"
])

try:
    server_process.wait()
except KeyboardInterrupt:
    server_process.terminate()
    worker_process.terminate()
