"""The face + evidence panel (spec section 8, Point 6).

A tiny stdlib http.server page. The face is driven ONLY by the recorded
state machine: write_panel_state() reads the focus lesson's actual state
from the store and maps it through the spec 2.3 table. The face
illustrates the gate; it never decides anything, and it is never set by
hand -- if the face disagrees with the record, the record wins and the
face is a bug.

Run:  python -m second_draft.panel [--port 8765] [--state <path>]
Then open http://127.0.0.1:8765 -- the page polls the state JSON and
re-renders the face, label, current lesson, last gate decision, and the
event ledger tail.
"""

from __future__ import annotations

import argparse
import json
import os
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Optional

from .models import Lesson, face_for, label_for
from .retrieval import context_summary
from .store import Store

DEFAULT_STATE_PATH = os.path.join("data", "panel_state.json")

PAGE = """<!DOCTYPE html>
<html lang="en"><head><meta charset="utf-8">
<title>Second Draft -- gate panel</title>
<style>
 body { font-family: system-ui, sans-serif; margin: 2rem; background:#111; color:#eee; }
 #face { font-size: 4rem; text-align:center; margin: 1rem 0 0.2rem; }
 #label { text-align:center; font-size:1.4rem; letter-spacing: .08em; }
 #state { text-align:center; color:#9ad; font-family: monospace; }
 .card { background:#1b1b1b; border:1px solid #333; border-radius:10px;
         padding:1rem 1.2rem; margin:1rem auto; max-width:760px; }
 h2 { font-size:1rem; color:#bbb; margin:.2rem 0 .6rem; text-transform:uppercase;
      letter-spacing:.06em; }
 pre, li { font-family: ui-monospace, monospace; font-size:.85rem; }
 ul { margin:.2rem 0; padding-left:1.2rem; }
 .dim { color:#999; }
</style></head><body>
<div id="face">...</div>
<div id="label">loading</div>
<div id="state"></div>
<div class="card"><h2>Current lesson</h2><div id="lesson">--</div></div>
<div class="card"><h2>Last gate decision</h2><pre id="decision">--</pre></div>
<div class="card"><h2>Retrieval context (code-enforced)</h2>
 <div>In context: <span id="inctx">--</span></div>
 <div class="dim">Shut out: <span id="shutout">--</span></div></div>
<div class="card"><h2>Event ledger (append-only)</h2><ul id="ledger"></ul></div>
<script>
async function tick() {
  try {
    const s = await (await fetch('/state.json')).json();
    document.getElementById('face').textContent = s.face;
    document.getElementById('label').textContent = s.label;
    document.getElementById('state').textContent = s.state + ' -- ' + (s.focus || '');
    document.getElementById('lesson').textContent = s.lesson_text || '--';
    document.getElementById('decision').textContent =
      JSON.stringify(s.last_decision, null, 2) || '--';
    document.getElementById('inctx').textContent =
      (s.context.in_context.join(', ') || '(none)');
    document.getElementById('shutout').textContent =
      (s.context.shut_out.join(', ') || '(none)');
    document.getElementById('ledger').innerHTML =
      s.ledger_tail.map(e => '<li>#' + e.seq + ' [' + e.type + '] ' +
        e.detail.replace(/</g,'&lt;') + '</li>').join('');
  } catch (e) { /* state file not written yet */ }
}
setInterval(tick, 1000); tick();
</script></body></html>
"""


def write_panel_state(
    state_path: str,
    store: Store,
    focus_lesson: Optional[Lesson],
    last_decision: Optional[dict] = None,
) -> dict:
    """Derive the panel state from the store's records. The face/label come
    from the focus lesson's machine state via the spec 2.3 mapping -- never
    from a caller-supplied string."""
    if focus_lesson is not None:
        state = focus_lesson.state
        face, label = face_for(state), label_for(state)
        focus = f"{focus_lesson.family} v{focus_lesson.version}"
        lesson_text = focus_lesson.claim_text
    else:
        face, label, focus, lesson_text = "( •̀ ω •́ )✧", "Candidate", "", ""
        state = None
    payload = {
        "face": face,
        "label": label,
        "state": state.value if state else "NO_FOCUS",
        "focus": focus,
        "lesson_text": lesson_text,
        "last_decision": last_decision,
        "context": context_summary(store),
        "ledger_tail": store.events()[-12:],
    }
    os.makedirs(os.path.dirname(os.path.abspath(state_path)), exist_ok=True)
    tmp = state_path + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(payload, f, indent=2, ensure_ascii=False)
    os.replace(tmp, state_path)
    return payload


def serve(port: int = 8765, state_path: str = DEFAULT_STATE_PATH) -> None:
    class Handler(BaseHTTPRequestHandler):
        def do_GET(self):  # noqa: N802 (stdlib naming)
            if self.path == "/state.json":
                try:
                    with open(state_path, "rb") as f:
                        body = f.read()
                except FileNotFoundError:
                    body = b"{}"
                self.send_response(200)
                self.send_header("Content-Type", "application/json")
                self.end_headers()
                self.wfile.write(body)
            else:
                body = PAGE.encode("utf-8")
                self.send_response(200)
                self.send_header("Content-Type", "text/html; charset=utf-8")
                self.end_headers()
                self.wfile.write(body)

        def log_message(self, *args):  # keep the terminal quiet
            pass

    print(f"Second Draft panel on http://127.0.0.1:{port} (state: {state_path})")
    ThreadingHTTPServer(("127.0.0.1", port), Handler).serve_forever()


def main() -> None:
    ap = argparse.ArgumentParser(description="Second Draft face/evidence panel")
    ap.add_argument("--port", type=int, default=8765)
    ap.add_argument("--state", default=DEFAULT_STATE_PATH)
    args = ap.parse_args()
    serve(args.port, args.state)


if __name__ == "__main__":
    main()
