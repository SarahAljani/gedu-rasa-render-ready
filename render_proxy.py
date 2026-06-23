#!/usr/bin/env python3
import argparse
import http.client
import json
from http.server import ThreadingHTTPServer, BaseHTTPRequestHandler
from urllib.parse import urlsplit

class ProxyHandler(BaseHTTPRequestHandler):
    target_host = "127.0.0.1"
    target_port = 5005

    def _cors(self):
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "GET, POST, PUT, PATCH, DELETE, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type, Authorization, X-Requested-With")

    def do_OPTIONS(self):
        self.send_response(204)
        self._cors()
        self.end_headers()

    def do_GET(self):
        if self.path == "/" or self.path == "/healthz":
            self.send_response(200)
            self._cors()
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            self.wfile.write(json.dumps({"status": "proxy-running", "service": "gedu-rasa"}).encode())
            return
        self._forward()

    def do_POST(self):
        self._forward()

    def do_PUT(self):
        self._forward()

    def do_PATCH(self):
        self._forward()

    def do_DELETE(self):
        self._forward()

    def _forward(self):
        length = int(self.headers.get("Content-Length", "0") or 0)
        body = self.rfile.read(length) if length else None
        headers = {k: v for k, v in self.headers.items() if k.lower() not in {"host", "content-length", "connection"}}
        try:
            conn = http.client.HTTPConnection(self.target_host, self.target_port, timeout=30)
            conn.request(self.command, self.path, body=body, headers=headers)
            resp = conn.getresponse()
            data = resp.read()
            self.send_response(resp.status)
            self._cors()
            for key, value in resp.getheaders():
                if key.lower() not in {"transfer-encoding", "connection", "content-length", "access-control-allow-origin"}:
                    self.send_header(key, value)
            self.send_header("Content-Length", str(len(data)))
            self.end_headers()
            self.wfile.write(data)
        except Exception as exc:
            message = {"status": "rasa-starting", "detail": str(exc)}
            data = json.dumps(message).encode()
            self.send_response(503)
            self._cors()
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(data)))
            self.end_headers()
            self.wfile.write(data)
        finally:
            try:
                conn.close()
            except Exception:
                pass

if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--listen-port", type=int, required=True)
    parser.add_argument("--target-port", type=int, default=5005)
    args = parser.parse_args()
    ProxyHandler.target_port = args.target_port
    server = ThreadingHTTPServer(("0.0.0.0", args.listen_port), ProxyHandler)
    print(f"Render proxy listening on 0.0.0.0:{args.listen_port}, forwarding to 127.0.0.1:{args.target_port}", flush=True)
    server.serve_forever()
