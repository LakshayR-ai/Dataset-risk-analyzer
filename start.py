"""Start frontend + backend together. Ctrl+C stops both."""
import http.server, socketserver, os, sys, threading, subprocess

ROOT = os.path.dirname(os.path.abspath(__file__))

def run_frontend():
    import http.server, socketserver
    os.chdir(os.path.join(ROOT, 'frontend'))
    Handler = http.server.SimpleHTTPRequestHandler
    Handler.extensions_map.update({'.jsx': 'application/javascript'})
    Handler.log_message = lambda *a: None
    s = socketserver.TCPServer(("", 3000), Handler)
    s.allow_reuse_address = True
    s.serve_forever()

def run_backend():
    subprocess.run([sys.executable, os.path.join(ROOT, 'backend', 'app.py')],
                   cwd=os.path.join(ROOT, 'backend'))

threading.Thread(target=run_frontend, daemon=True).start()
threading.Thread(target=run_backend,  daemon=True).start()

print("🚀 DataQA running:")
print("   Frontend → http://localhost:3000")
print("   Backend  → http://localhost:5000")
print("   Ctrl+C to stop both.\n")

try:
    while True: pass
except KeyboardInterrupt:
    print("\n🛑 Shutting down...")
    os._exit(0)
