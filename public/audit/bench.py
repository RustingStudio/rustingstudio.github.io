#!/usr/bin/env python3
"""RustingStudio LLM performance audit: benchmark script.

Measures an OpenAI-compatible server that is already running on this machine:
llama.cpp (llama-server), Ollama, vLLM, LM Studio, RustingStrata, and others.

    python3 bench.py --url http://127.0.0.1:8080
    python3 bench.py --url http://127.0.0.1:11434 --model qwen3:30b-a3b     # Ollama
    python3 bench.py --url http://127.0.0.1:8080 --parallel 1,2,4           # also test concurrent requests

Needs Python 3.8+ and nothing else. It writes one JSON file: send that file back.

What the file contains: OS, CPU model and core count, RAM size, GPU name / VRAM / driver
(from nvidia-smi or rocm-smi, if installed), the model names the server reports, the server
version where it exposes one, and timings of synthetic prompts. No hostname, user name,
file paths, or any of your own prompts or data.

Close other GPU programs (games, browsers with video) before running: they change the result.
"""
import argparse, concurrent.futures as cf, json, os, platform, random, statistics, subprocess, sys, time, urllib.request

VERSION = 1
WORDS = ("the engine reads each layer from memory then multiplies it with the hidden state and writes the result "
         "back before the next token can start so bandwidth sets the pace more often than compute does").split()


def sh(*cmd):
    try:
        return subprocess.run(cmd, capture_output=True, text=True, timeout=15).stdout.strip() or None
    except Exception:
        return None


def ram_gib():
    try:
        if sys.platform.startswith("linux"):
            kb = next(int(l.split()[1]) for l in open("/proc/meminfo") if l.startswith("MemTotal"))
            return round(kb / 2**20, 1)
        if sys.platform == "darwin":
            return round(int(sh("sysctl", "-n", "hw.memsize")) / 2**30, 1)
        if sys.platform == "win32":
            import ctypes
            class M(ctypes.Structure):
                _fields_ = [("len", ctypes.c_ulong), ("load", ctypes.c_ulong), ("total", ctypes.c_ulonglong), ("rest", ctypes.c_ulonglong * 6)]
            m = M(); m.len = ctypes.sizeof(M)
            ctypes.windll.kernel32.GlobalMemoryStatusEx(ctypes.byref(m))
            return round(m.total / 2**30, 1)
    except Exception:
        return None


def cpu_name():
    try:
        if sys.platform.startswith("linux"):
            return next(l.split(":", 1)[1].strip() for l in open("/proc/cpuinfo") if l.startswith("model name"))
    except Exception:
        pass
    return sh("sysctl", "-n", "machdep.cpu.brand_string") or platform.processor() or None


def gpus():
    q = "name,memory.total,memory.used,driver_version,pcie.link.gen.current,pcie.link.width.current,power.limit"
    nv = sh("nvidia-smi", "--query-gpu=" + q, "--format=csv,noheader")
    return {"nvidia": nv.splitlines() if nv else None,
            "rocm": sh("rocm-smi", "--showproductname", "--showmeminfo", "vram", "--json")}


def get_json(url, timeout=10):
    try:
        with urllib.request.urlopen(url, timeout=timeout) as r:
            return json.load(r)
    except Exception:
        return None


def server_info(url):
    props = get_json(url + "/props") or {}  # llama.cpp
    gen = props.get("default_generation_settings") or {}
    return {"models": [m.get("id") for m in (get_json(url + "/v1/models") or {}).get("data", [])],
            "llama_cpp_build": props.get("build_info"), "llama_cpp_n_ctx": gen.get("n_ctx") or props.get("n_ctx"),
            "llama_cpp_slots": props.get("total_slots"), "ollama_version": (get_json(url + "/api/version") or {}).get("version")}


def make_prompt(tokens):
    # ~1.3 tokens per English word; the server reports the real count. The random tag at the start
    # stops servers from reusing a cached prefix of an earlier run.
    words = [random.choice(WORDS) for _ in range(int(tokens / 1.3))]
    return f"[run {random.getrandbits(64):016x}] Read this text, then write a very long story about GPUs.\n\n" + " ".join(words)


def one_request(url, model, prompt, gen, timeout):
    body = {"model": model, "messages": [{"role": "user", "content": prompt}], "max_tokens": gen, "temperature": 0,
            "stream": True, "stream_options": {"include_usage": True}, "ignore_eos": True}
    req = urllib.request.Request(url + "/v1/chat/completions", json.dumps(body).encode(), {"Content-Type": "application/json"})
    t0 = time.perf_counter(); first = last = None; chunks = 0; usage = timings = None
    with urllib.request.urlopen(req, timeout=timeout) as r:
        for line in r:
            line = line.strip()
            if not line.startswith(b"data:"):
                continue
            data = line[5:].strip()
            if data == b"[DONE]":
                break
            j = json.loads(data)
            usage = j.get("usage") or usage
            timings = j.get("timings") or timings  # llama.cpp's own measurement
            for c in j.get("choices") or []:
                d = c.get("delta") or {}
                if d.get("content") or d.get("reasoning_content") or d.get("reasoning"):
                    now = time.perf_counter(); first = first or now; last = now; chunks += 1
    end = time.perf_counter()
    if first is None:
        raise RuntimeError("the server streamed no text")
    n_out = (usage or {}).get("completion_tokens") or chunks
    n_in = (usage or {}).get("prompt_tokens")
    ttft = first - t0
    return {"prompt_tokens": n_in, "completion_tokens": n_out, "ttft_s": round(ttft, 4), "total_s": round(end - t0, 4),
            "prefill_tok_s": round(n_in / ttft, 1) if n_in else None,
            "decode_tok_s": round((n_out - 1) / (last - first), 1) if n_out > 1 and last > first else None,
            "server_timings": timings}


def med(rows, key):
    v = [r[key] for r in rows if r.get(key) is not None]
    return {"median": round(statistics.median(v), 1), "min": min(v), "max": max(v)} if v else None


def bench(url, model, sizes, gen, runs, parallel, timeout, log=print):
    out = {"single": [], "parallel": []}
    log("warm-up run ...")
    one_request(url, model, make_prompt(sizes[0]), 16, timeout)
    for size in sizes:
        rows = []
        for i in range(runs):
            rows.append(one_request(url, model, make_prompt(size), gen, timeout))
            log(f"prompt ~{size:>6} tok  run {i + 1}/{runs}: prefill {rows[-1]['prefill_tok_s']} tok/s, decode {rows[-1]['decode_tok_s']} tok/s")
        got = rows[0]["prompt_tokens"]
        if got and got < size * 0.5:
            log(f"  WARNING: server saw only {got} prompt tokens for ~{size}: its context size probably truncates the prompt")
        out["single"].append({"target_tokens": size, "runs": rows, "prefill_tok_s": med(rows, "prefill_tok_s"),
                              "decode_tok_s": med(rows, "decode_tok_s"), "ttft_s": med(rows, "ttft_s")})
    for p in parallel:
        if p <= 1:
            continue
        t0 = time.perf_counter()
        with cf.ThreadPoolExecutor(p) as ex:
            rows = list(ex.map(lambda _: one_request(url, model, make_prompt(sizes[0]), gen, timeout), range(p)))
        wall = time.perf_counter() - t0
        total = sum(r["completion_tokens"] for r in rows)
        log(f"{p} parallel requests: {total / wall:.1f} tok/s generated in total, per request median decode {med(rows, 'decode_tok_s')}")
        out["parallel"].append({"requests": p, "wall_s": round(wall, 3), "total_out_tok_s": round(total / wall, 1),
                                "decode_tok_s": med(rows, "decode_tok_s"), "ttft_s": med(rows, "ttft_s"), "runs": rows})
    return out


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--url", default="http://127.0.0.1:8080", help="server base URL, without /v1")
    ap.add_argument("--model", help="model name to request (default: the first one the server lists)")
    ap.add_argument("--prompts", default="128,1024,4096", help="approximate prompt sizes in tokens, comma separated")
    ap.add_argument("--gen", type=int, default=128, help="tokens to generate per request")
    ap.add_argument("--runs", type=int, default=3, help="runs per prompt size")
    ap.add_argument("--parallel", default="1", help="concurrent request counts to test, e.g. 1,2,4")
    ap.add_argument("--timeout", type=float, default=600)
    ap.add_argument("--note", default="", help="free text for the report, e.g. the server command line you used")
    ap.add_argument("--out", help="output file (default: audit-<time>.json)")
    a = ap.parse_args()
    url = a.url.rstrip("/")
    url = url[:-3] if url.endswith("/v1") else url

    info = server_info(url)
    model = a.model or (info["models"] or [None])[0]
    if not model:
        sys.exit(f"No model found at {url}/v1/models. Is the server running? Pass --url and --model.")
    print(f"server {url}, model {model}")
    report = {"script_version": VERSION, "time_utc": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()), "note": a.note,
              "system": {"os": platform.platform(), "python": platform.python_version(), "cpu": cpu_name(),
                         "cpu_threads": os.cpu_count(), "ram_gib": ram_gib(), "gpus_before": gpus()},
              "server": {**info, "model": model},
              "settings": {"prompts": a.prompts, "gen": a.gen, "runs": a.runs, "parallel": a.parallel}}
    try:
        report["results"] = bench(url, model, [int(x) for x in a.prompts.split(",")], a.gen, a.runs,
                                  [int(x) for x in a.parallel.split(",")], a.timeout)
    except Exception as e:
        report["error"] = repr(e)
        print("ERROR:", e)
    report["system"]["gpus_after"] = gpus()  # VRAM used while the model is loaded
    path = a.out or time.strftime("audit-%Y%m%d-%H%M%S.json")
    with open(path, "w") as f:
        json.dump(report, f, indent=1)
    print(f"\nWrote {os.path.abspath(path)}. Send this file back.")


if __name__ == "__main__":
    main()
