"""Gemini through the Antigravity ACP server (the T3 Code provider, Google sign-in, no API key).

Starts the real server directly with a US exit as its proxy, so T3's own proxy.txt (10808, now a German exit
that Google refuses with 403) is left alone. One server, one session per call.
"""
import os, subprocess, sys, threading, time
sys.path.insert(0, r"I:\Ai Software For Me\AgentTools")
sys.path.insert(0, r"I:\Ai Software For Me\SubLLM")
from aitools import net  # noqa: E402
import subllm  # noqa: E402

REAL = subllm.AGY.parent / "agy_acp_server.real.exe"
_srv, _lock = None, threading.Lock()


def _proxy():
    want = os.environ.get("AB_GEMINI_EXIT", "Usa")
    for p in net.pool():
        if want.lower() in p["name"].lower():
            return p["proxy"]
    raise RuntimeError(f"no fallback exit named like {want!r} is up")


class _Server(subllm._Acp):
    def __init__(self):
        px = _proxy()
        env = dict(os.environ, HTTPS_PROXY=px, HTTP_PROXY=px, ALL_PROXY=px, GRPC_PROXY=px,
                   NO_PROXY="localhost,127.0.0.1")
        self.p = subprocess.Popen([str(REAL)], stdin=subprocess.PIPE, stdout=subprocess.PIPE,
                                  stderr=subprocess.DEVNULL, creationflags=subllm.NO_WINDOW,
                                  cwd=str(REAL.parent), env=env)
        self.lock, self.n, self.waiting, self.text = threading.Lock(), 0, {}, {}
        threading.Thread(target=self._read, daemon=True).start()
        subllm._tie_to_this_process(self.p)
        import atexit
        atexit.register(self.close)
        self.call("initialize", {"protocolVersion": 1, "clientCapabilities": {}})
        self.call("authenticate", {"methodId": "oauth-personal"})


def write(model, prompt, timeout=1500):
    global _srv
    with _lock:
        if _srv is None or _srv.p.poll() is not None:
            _srv = _Server()
        srv = _srv
    t = time.time()
    sid = srv.call("session/new", {"cwd": str(REAL.parent), "mcpServers": []})["sessionId"]
    srv.call("session/set_model", {"sessionId": sid, "modelId": model})  # fail rather than fall back to Flash
    srv.call("session/prompt", {"sessionId": sid, "prompt": [{"type": "text", "text": prompt}]}, timeout=timeout)
    text = "".join(srv.text.pop(sid, []))
    if not text.strip():
        raise RuntimeError("gemini: empty answer")
    return {"text": text, "secs": round(time.time() - t, 1), "usage": None, "modelUsage": None, "cost_equiv_usd": None}
