# Check public/audit/bench.py against a fake streaming server with known speeds.
# Usage: python3 -I scripts/test_audit_bench.py
import importlib.util, json, pathlib, sys, threading, time
sys.dont_write_bytecode = True  # keep __pycache__ out of public/
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

PREFILL_S, TOKEN_S, N_IN = 0.05, 0.01, 100  # fake server: 2000 tok/s prefill, 100 tok/s decode


class Fake(BaseHTTPRequestHandler):
    def log_message(self, *a): pass

    def do_GET(self):
        body = json.dumps({"data": [{"id": "fake-model"}]} if self.path == "/v1/models" else {}).encode()
        self.send_response(200 if self.path == "/v1/models" else 404); self.end_headers(); self.wfile.write(body)

    def do_POST(self):
        n = json.loads(self.rfile.read(int(self.headers["Content-Length"])))["max_tokens"]
        self.send_response(200); self.send_header("Content-Type", "text/event-stream"); self.end_headers()
        time.sleep(PREFILL_S)
        for i in range(n):
            if i: time.sleep(TOKEN_S)
            self.wfile.write(b"data: " + json.dumps({"choices": [{"delta": {"content": "x"}}]}).encode() + b"\n\n"); self.wfile.flush()
        usage = {"prompt_tokens": N_IN, "completion_tokens": n}
        self.wfile.write(b"data: " + json.dumps({"choices": [], "usage": usage}).encode() + b"\n\ndata: [DONE]\n\n")


spec = importlib.util.spec_from_file_location("bench", pathlib.Path(__file__).parent.parent / "public/audit/bench.py")
bench = importlib.util.module_from_spec(spec); spec.loader.exec_module(bench)
srv = ThreadingHTTPServer(("127.0.0.1", 0), Fake)
threading.Thread(target=srv.serve_forever, daemon=True).start()
url = f"http://127.0.0.1:{srv.server_port}"

assert bench.server_info(url)["models"] == ["fake-model"]
r = bench.bench(url, "fake-model", [128], 30, 2, [1, 3], 30, log=lambda *_: None)
s = r["single"][0]
assert 70 < s["decode_tok_s"]["median"] <= 105, s["decode_tok_s"]
assert 1000 < s["prefill_tok_s"]["median"] <= 2000, s["prefill_tok_s"]
assert s["runs"][0]["completion_tokens"] == 30
p = r["parallel"][0]
assert p["requests"] == 3 and p["total_out_tok_s"] > 1.5 * s["decode_tok_s"]["median"], p  # threaded server overlaps requests
print("ok", s["decode_tok_s"], s["prefill_tok_s"], p["total_out_tok_s"])
