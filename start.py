"""
start.py — Launch frontend (port 3000) + backend (port 5000) together.
Press Ctrl+C to stop both.
"""
import os
import sys
import time
import threading
import subprocess

ROOT         = os.path.dirname(os.path.abspath(__file__))
FRONTEND_DIR = os.path.join(ROOT, "frontend")
BACKEND_DIR  = os.path.join(ROOT, "backend")
BACKEND_SCRIPT = os.path.join(BACKEND_DIR, "app.py")

FRONTEND_PORT = 3000
BACKEND_PORT  = 5000


# ── Frontend: Python's built-in HTTP server ───────────────────────────────────
def run_frontend():
    import http.server
    import socketserver

    class Handler(http.server.SimpleHTTPRequestHandler):
        # Serve files from frontend/ without changing process cwd
        def __init__(self, *args, **kwargs):
            super().__init__(*args, directory=FRONTEND_DIR, **kwargs)

        def log_message(self, fmt, *args):
            pass  # silence per-request logs; errors still print via log_error

    Handler.extensions_map.update({
        ".jsx": "application/javascript",
        ".js":  "application/javascript",
        ".css": "text/css",
        ".html": "text/html",
    })

    socketserver.TCPServer.allow_reuse_address = True
    try:
        with socketserver.TCPServer(("", FRONTEND_PORT), Handler) as httpd:
            print(f"   ✅ Frontend started → http://localhost:{FRONTEND_PORT}")
            httpd.serve_forever()
    except OSError as e:
        print(f"   ❌ Frontend failed to start on port {FRONTEND_PORT}: {e}")


# ── Backend: Flask via subprocess (keeps its own process space) ───────────────
def run_backend():
    env = os.environ.copy()
    env["FLASK_DEBUG"] = "0"   # disables reloader so no extra fork is spawned
    try:
        subprocess.run(
            [sys.executable, BACKEND_SCRIPT],
            cwd=BACKEND_DIR,
            env=env,
        )
    except Exception as e:
        print(f"   ❌ Backend error: {e}")


# ── Main ──────────────────────────────────────────────────────────────────────
if __name__ == "__main__":
    print("🚀 Starting DataQA...")

    fe = threading.Thread(target=run_frontend, daemon=True, name="frontend")
    be = threading.Thread(target=run_backend,  daemon=True, name="backend")

    fe.start()
    be.start()

    # Give servers a moment to bind before printing URLs
    time.sleep(1.5)

    print("\n" + "─" * 44)
    print(f"   🌐 App      →  http://localhost:{FRONTEND_PORT}")
    print(f"   🔧 API      →  http://localhost:{BACKEND_PORT}/api/health")
    print("   Press Ctrl+C to stop.")
    print("─" * 44 + "\n")

    try:
        # Keep main thread alive
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        print("\n🛑 Shutting down...")
        os._exit(0)
