# -*- coding: utf-8 -*-
"""
server.py - the Nashmi chat UI for the demo (optional: the evaluation only uses main.py).

Run:   python server.py            -> opens http://localhost:8000
       python server.py --port 9000 --no-browser

It uses exactly the same engine as main.py (bot.Chat), and under every answer it shows the RAG steps:
which service and fields were retrieved, and the exact document pieces the model was given.
Standard library only.
"""
import argparse, json, mimetypes, os, threading, time, traceback, webbrowser
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

import bot

ROOT = os.path.dirname(os.path.abspath(__file__))
WEB = os.path.join(ROOT, "ui")
DB = bot.load()
CHATS = {}                      # conversation_id -> bot.Chat (its own memory, like one chat in questions.json)
LOCK = threading.Lock()
STATE = {"model": "loading", "error": None, "name": ""}

FIELD_AR = dict(bot.FIELDS)
SIT_AR = bot.SIT_NAMES
DOC_AR = bot.DOC_NAMES


def warm_up():
    """Load the model once in the background so the first question isn't slow; retry while Ollama is down."""
    while True:
        try:
            STATE["name"] = bot.model_name()
            bot.llm([{"role": "user", "content": "مرحبا"}])
            STATE["model"], STATE["error"] = "ready", None
            return
        except Exception as e:
            STATE["model"], STATE["error"] = "offline", str(e)
            time.sleep(10)


def route_label(r):
    """'🧭 الاسترجاع: جواز السفر - تجديد ← الرسوم، ملاحظات' : what the retriever decided, shown in the UI."""
    if r["action"] == "decline":
        return "🧭 الاسترجاع: السؤال خارج نطاق الوثائق ← اعتذار بدون استدعاء النموذج"
    if r["action"] == "clarify":
        return "🧭 الاسترجاع: معلومات ناقصة ← سؤال توضيحي بدون استدعاء النموذج"
    svc = []
    for k in r.get("services") or []:
        d = next((x for x in DOC_AR if k.startswith(x)), "")
        svc.append(f"{DOC_AR.get(d, k)} - {SIT_AR.get(k[len(d) + 1:], '')}")
    flds = "، ".join(FIELD_AR.get(f, f) for f in (r.get("fields") or [])) or "أفضل الحقول تطابقاً"
    store = "ChromaDB" if bot._EMB.get("chroma") is not None else "JSON"
    how = f" · ترتيب دلالي: bge-m3 + {store}" if r.get("semantic") else ""
    return f"🧭 الاسترجاع: {' + '.join(svc) or 'من سياق المحادثة'} ← {flds}{how}"


class Handler(BaseHTTPRequestHandler):
    server_version = "Nashmi/2.0"

    def log_message(self, fmt, *args):
        if args and "/api/" in str(args[0]):
            print(time.strftime("%H:%M:%S"), fmt % args)

    def send_json(self, obj, status=200):
        body = json.dumps(obj, ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def read_json(self):
        n = int(self.headers.get("Content-Length") or 0)
        return json.loads(self.rfile.read(n) or b"{}")

    def line(self, obj):
        self.wfile.write((json.dumps(obj, ensure_ascii=False) + "\n").encode("utf-8"))
        self.wfile.flush()

    def do_GET(self):
        path = self.path.split("?")[0]
        if path == "/api/status":
            return self.send_json({
                "model": STATE["model"], "model_name": STATE["name"] or bot.PREFERRED, "model_error": STATE["error"],
                "fake": False, "index": True,
                "files": [{"name": f"{k}.txt", "chunks": len(s["fields"])} for k, s in DB.items()],
                "records": sum(len(s["fields"]) for s in DB.values()), "search": "router",
            })
        return self.static(path)

    def do_POST(self):
        path = self.path.split("?")[0]
        if path == "/api/reset":
            cid = str(self.read_json().get("conversation_id", ""))
            with LOCK:
                CHATS.pop(cid, None)
            return self.send_json({"ok": True})
        if path != "/api/chat":
            return self.send_json({"error": "not found"}, 404)
        req = self.read_json()
        q = str(req.get("message", "")).strip()
        cid = str(req.get("conversation_id") or "default")
        with LOCK:
            chat = CHATS.setdefault(cid, bot.Chat(DB))
        self.send_response(200)
        self.send_header("Content-Type", "application/x-ndjson; charset=utf-8")
        self.send_header("Cache-Control", "no-cache")
        self.end_headers()
        t0 = time.time()
        try:
            if not q:
                return self.line({"type": "error", "message": "الرسالة فاضية"})
            answer, contexts, r = chat.ask(q)
            short = []
            for c in contexts:  # "تجديد جواز السفر العادي · الرسوم، ملاحظات"
                title, rest = c.split(" - ", 1) if " - " in c else (c, "")
                field = rest.split(":", 1)[0]
                hit = next((x for x in short if x[0] == title), None)
                (hit[1].append(field) if hit else short.append((title, [field])))
            self.line({
                "type": "meta",
                "contexts": contexts,
                "route_label": route_label(r),
                "sources_short": " | ".join(f"{t} · {'، '.join(f)}" for t, f in short),
                "route": {"action": r["action"], "services": r.get("services") or [], "fields": r.get("fields") or [],
                          "greet": bool(r.get("greet")), "clarified": bool(r.get("clarified")),
                          "missing": "document" if r["action"] == "clarify" else "situation"},
            })
            self.line({"type": "token", "text": answer})
            self.line({"type": "done", "seconds": round(time.time() - t0, 1)})
        except (BrokenPipeError, ConnectionResetError):
            pass
        except Exception as e:
            traceback.print_exc()
            try:
                self.line({"type": "error", "message": f"صار خطأ: {e}"})
            except Exception:
                pass

    def static(self, path):
        rel = path.lstrip("/") or "index.html"
        full = os.path.normpath(os.path.join(WEB, rel))
        if not full.startswith(WEB) or not os.path.isfile(full):
            full = os.path.join(WEB, "index.html")
        ctype = mimetypes.guess_type(full)[0] or "application/octet-stream"
        if ctype.startswith("text/") or ctype in ("application/javascript", "image/svg+xml"):
            ctype += "; charset=utf-8"
        with open(full, "rb") as f:
            body = f.read()
        self.send_response(200)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--port", type=int, default=8000)
    ap.add_argument("--no-browser", action="store_true")
    a = ap.parse_args()
    mimetypes.add_type("application/javascript", ".js")
    mimetypes.add_type("text/css", ".css")
    threading.Thread(target=warm_up, daemon=True).start()
    url = f"http://localhost:{a.port}"
    print(f"\n  Nashmi UI -> {url}   ({len(DB)} services loaded, Ctrl+C to stop)\n")
    if not a.no_browser:
        threading.Timer(1.0, lambda: webbrowser.open(url)).start()
    ThreadingHTTPServer(("127.0.0.1", a.port), Handler).serve_forever()


if __name__ == "__main__":
    main()
