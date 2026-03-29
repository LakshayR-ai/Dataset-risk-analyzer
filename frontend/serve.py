import http.server, socketserver, os, sys, threading

PORT = 3000
os.chdir(os.path.dirname(os.path.abspath(__file__)))

Handler = http.server.SimpleHTTPRequestHandler
Handler.extensions_map.update({'.jsx': 'application/javascript'})
Handler.log_message = lambda *a: None

httpd = socketserver.TCPServer(("", PORT), Handler)
httpd.allow_reuse_address = True
threading.Thread(target=httpd.serve_forever, daemon=True).start()

print(f"✅ Frontend → http://localhost:{PORT}  |  Ctrl+C to stop")
try:
    while True: pass
except KeyboardInterrupt:
    print("\n🛑 Stopped.")
    os._exit(0)
