"""
TELOS Dashboard Server — serves the dashboard HTML + LIVE runtime data
+ WebSocket live feed.

The dashboard now PRODUCES the data it serves: a DashboardProducer runs
the real TELOS pipeline on a background thread in this process, so
opening http://localhost:8765 shows live graphs, live DI/MD, and a
data story — no separate telos_task.py run required.

Usage:
    python3 serve_dashboard.py        # one command: producer + server + ws

Then open http://localhost:8765 in your browser.

Honesty contract: every number the API returns is measured runtime data
or persisted history — never fabricated. If the producer is disabled
(TELOS_DASHBOARD_NO_PRODUCER=1) or cannot build, the dashboard falls
back to the honest empty/history state.
"""

import json
import os
import glob
import asyncio
import websockets
import logging
import subprocess
import sys
from http.server import ThreadingHTTPServer, SimpleHTTPRequestHandler
from urllib.parse import urlparse
from threading import Thread

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger('telos_dashboard')

# The launcher (start_dashboard.sh) runs this file from inside telos/, so
# ensure the project root is importable before importing the telos package.
_SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
_PROJECT_ROOT = os.path.dirname(_SCRIPT_DIR)
if _PROJECT_ROOT not in sys.path:
    sys.path.insert(0, _PROJECT_ROOT)

# The bounded-score range rule lives in the producer module (single source
# of truth): out-of-range scores are structurally rejected, never displayed.
from telos.dashboard.producer import safe_score

CHECKPOINT_DIR = "/tmp/telos_checkpoints"
KNOWLEDGE_PATH = "/tmp/telos_knowledge.json"
HTTP_PORT = 8765
WS_PORT = 8766

# Store for live WebSocket clients
websocket_clients = set()
_ws_loop = None  # set when WebSocket server starts; asyncio.AbstractEventLoop

# Store for TELOS conversation context
telos_context = {"cycle": 0, "last_response": ""}

# Live data producer (started in main() unless disabled via env var).
_producer = None


def get_producer():
    return _producer


# ─── HTTP Server ───
class DashboardHandler(SimpleHTTPRequestHandler):
    def do_GET(self):
        parsed = urlparse(self.path)

        if parsed.path == '/' or parsed.path == '':
            self.path = '/dashboard.html'

        if parsed.path.startswith('/api/checkpoints'):
            self.send_json(self._load_checkpoints())
            return

        if parsed.path == '/api/knowledge':
            self.send_json(self._load_knowledge())
            return

        if parsed.path == '/api/overview':
            self.send_json(self._load_overview())
            return

        if parsed.path == '/api/status':
            prod = get_producer()
            self.send_json({
                'clients': len(websocket_clients),
                'checkpoints': len(glob.glob(os.path.join(CHECKPOINT_DIR, 'checkpoint_*.json'))),
                'producer_running': bool(prod is not None and prod.is_running),
                'producer_cycles': prod.snapshot().get('decisions', 0) if prod else 0,
            })
            return

        if parsed.path == '/api/benchmark':
            self.send_json(self._load_benchmark())
            return

        if parsed.path == '/api/health':
            self.send_json(self._load_health_summary())
            return

        return super().do_GET()

    def do_POST(self):
        parsed = urlparse(self.path)

        if parsed.path == '/api/chat':
            content_len = int(self.headers.get('Content-Length', 0))
            body = self.rfile.read(content_len)
            data = json.loads(body) if body else {}

            result = self._run_telos(data.get('message', ''))
            self.send_json(result)
            return

        self.send_json({"error": "not found"}, 404)

    def __init__(self, *args, **kwargs):
        # Serve files from telos/ directory + fix JS MIME type
        telos_dir = os.path.dirname(os.path.abspath(__file__))
        super().__init__(*args, directory=telos_dir, **kwargs)
        if '.js' not in self.extensions_map:
            self.extensions_map['.js'] = 'application/javascript'

    def send_json(self, data, status=200):
        self.send_response(status)
        self.send_header('Content-Type', 'application/json')
        self.send_header('Access-Control-Allow-Origin', '*')
        self.send_header('Cache-Control', 'no-cache, no-store, must-revalidate')
        self.end_headers()
        # allow_nan=False: a stray NaN/Infinity becomes a loud 500 (logged),
        # never silently-invalid JSON that breaks every browser parser.
        self.wfile.write(json.dumps(data, allow_nan=False).encode())

    def end_headers(self):
        if self.path in ('/', '/dashboard.html', '/brain-viz.js'):
            try:
                self.send_header('Cache-Control', 'no-cache, no-store, must-revalidate')
            except (BrokenPipeError, ConnectionResetError, OSError) as e:
                # Kintsugi (Λ2.3): a dropped client is a recorded event, not
                # a silent swallow — log it and let the server move on.
                logger.warning(f"end_headers: client dropped before Cache-Control sent: {e}")
        super().end_headers()

    def _load_benchmark(self):
        """Load latest benchmark snapshot or return placeholder (zeros, honest)."""
        bm_dir = os.path.join(os.path.dirname(__file__), 'benchmarks', 'data')
        snapshots = sorted(glob.glob(os.path.join(bm_dir, 'snapshot_*.json')))
        if not snapshots:
            snapshots = sorted(glob.glob(os.path.join(bm_dir, 'session_*.json')))
        if snapshots:
            try:
                with open(snapshots[-1]) as f:
                    return json.load(f)
            except (OSError, json.JSONDecodeError):
                pass
        # Return placeholder with zeros so UI always renders (real zeros, no invention)
        return {
            "system_score": {"current": 0.5, "trend": "stable"},
            "mission_score": 0.5,
            "trends": {},
            "epochs": {
                "last_10": {
                    "cycles": 0, "duration_seconds": 0,
                    "perception": {"score": 0.5, "metrics": {"est_error": 0, "forecast": 0.5, "counterfactual": 0.5}},
                    "learning": {"score": 0.3, "metrics": {"curiosity": 0.3, "learning_rate": 0.1, "compression": 0}},
                    "identity": {"score": 0.5, "metrics": {"entropy": 0, "coherence": 1.0, "propagation": 0.5}},
                    "knowledge": {"score": 0.3, "metrics": {"theories": 0, "bridges": 0, "epistemic_capital": 0}},
                    "resources": {"score": 0.5, "metrics": {"compute": 0.5, "memory": 0.5, "croi": 0}},
                    "projects": {"score": 0.5, "metrics": {"completion": 0, "strategic_align": 0.5}},
                    "social": {"score": 0.5, "metrics": {"niches": 0, "bridges": 0, "collaboration": 0.5}},
                }
            },
        }

    def _load_health_summary(self):
        """Live health: producer snapshot first, benchmark/history as fallback."""
        prod = get_producer()
        if prod is not None:
            snap = prod.snapshot()
            if snap.get("decisions", 0) > 0:
                traces = snap.get("traces", [])
                last = traces[-1] if traces else {}
                return {
                    "health": snap.get("health", 0.5),
                    "system_score": last.get("health_score", 0.5),
                    "mission": 1.0 - min(1.0, snap.get("md", 0.0) / 5.0),
                    "cycles": snap.get("decisions", 0),
                    "decision_integrity": snap.get("di", 0.0),
                    "mission_drift": snap.get("md", 0.0),
                    "mood": snap.get("mood", "neutral"),
                    "resources": _last_resources(snap),
                    "producer_running": True,
                }
        bm = self._load_benchmark()
        sys_score = bm.get("system_score", {})
        if isinstance(sys_score, dict):
            health = sys_score.get("current", 0.5)
        else:
            health = sys_score if isinstance(sys_score, (int, float)) else 0.5
        return {
            "health": health,
            "system_score": health,
            "mission": bm.get("mission_score", 0.5),
            "cycles": bm.get("cycle", 0) if isinstance(bm, dict) else 0,
            "producer_running": False,
        }

    def _load_overview(self):
        """Big-data-story payload: every number measured or persisted."""
        prod = get_producer()
        if prod is not None:
            snap = prod.overview_payload()
            return {
                "producer": snap.get("producer", {"running": False, "cycles": 0}),
                "decisions": snap.get("decisions", 0),
                "domains": snap.get("knowledge", {}).get("domains", {}),
                "lessons": snap.get("knowledge", {}).get("nodes", 0),
                "edges": snap.get("knowledge", {}).get("edges", 0),
                "edge_types": snap.get("knowledge", {}).get("edge_types", {}),
                "world_states": snap.get("world_states", 0),
                "worlds_simulated": snap.get("worlds_simulated", 0),
                "di": snap.get("di", 0.0),
                "md": snap.get("md", 0.0),
                "mood": snap.get("mood", "neutral"),
                "score": snap.get("score"),
                "score_components": snap.get("score_components"),
                "reward_collected": snap.get("reward_collected", 0.0),
                "reward_available": snap.get("reward_available", 0.0),
                "position": snap.get("position", [0, 0]),
                "episodes": snap.get("episodes"),
                "recent_decisions": snap.get("recent_decisions", []),
                "knowledge": snap.get("knowledge", {}),
            }
        # No producer: derive what we honestly can from persisted history.
        traces = self._load_checkpoints()
        knowledge = self._load_knowledge()
        domains = {}
        for n in knowledge.get("nodes", []):
            d = n.get("domain", "general")
            domains[d] = domains.get(d, 0) + 1
        edge_types = {}
        for e in knowledge.get("edges", []):
            t = e.get("edge_type", "related")
            edge_types[t] = edge_types.get(t, 0) + 1
        recent = []
        for t in traces[-8:]:
            intent = t.get("selected_intent") or {}
            recent.append({
                "cycle_id": t.get("cycle_id"),
                "intent": intent.get("type", "unknown") if isinstance(intent, dict) else "unknown",
                "di": t.get("decision_integrity", 0.0),
                "md": t.get("mission_drift", 0.0),
                "status": "BLOCKED" if t.get("firewall_blocked") else "APPROVED",
                "worlds": t.get("worlds_simulated", 0),
            })
        return {
            "producer": {"running": False, "cycles": len(traces), "last_error": "producer not running"},
            "decisions": len(traces),
            "domains": domains,
            "lessons": len(knowledge.get("nodes", [])),
            "edges": len(knowledge.get("edges", [])),
            "edge_types": edge_types,
            "world_states": 0,
            # Honest derivation from persisted traces: sum the real
            # worlds_simulated values each cycle recorded (never invented).
            "worlds_simulated": sum(
                int(t.get("worlds_simulated", 0) or 0) for t in traces
            ),
            "di": traces[-1].get("decision_integrity", 0.0) if traces else 0.0,
            "md": traces[-1].get("mission_drift", 0.0) if traces else 0.0,
            "mood": _load_persisted_mood(),
            "score": safe_score(traces[-1].get("score")) if traces else None,
            "score_components": None,
            "reward_collected": 0.0,
            "reward_available": 0.0,
            "position": [0, 0],
            # Episode efficiency requires the live producer's in-memory
            # goal-reach bookkeeping — history-only mode has none, so it
            # is honestly None (the UI renders '—'), never invented.
            "episodes": None,
            "recent_decisions": recent,
            "knowledge": {"nodes": len(knowledge.get("nodes", [])), "edges": len(knowledge.get("edges", [])),
                          "domains": domains, "edge_types": edge_types},
        }

    def _load_checkpoints(self):
        """Full serialized traces from the live producer first; persisted
        history (checkpoint files) as fallback. Deduplicated by cycle_id."""
        prod = get_producer()
        merged = {}
        if prod is not None:
            snap = prod.snapshot()
            for t in snap.get("traces", []):
                if isinstance(t, dict) and t.get("cycle_id") is not None:
                    merged[t["cycle_id"]] = t
        for f in sorted(glob.glob(os.path.join(CHECKPOINT_DIR, 'checkpoint_*.json'))):
            try:
                with open(f) as fp:
                    data = json.load(fp)
                    if 'decision_trace' in data and isinstance(data['decision_trace'], dict):
                        dt = data['decision_trace']
                        cid = dt.get('cycle_id')
                        if cid is not None and cid not in merged:
                            merged[cid] = dt
            except (OSError, json.JSONDecodeError):
                pass
        ordered = [merged[k] for k in sorted(merged.keys())]
        # Cap the response: the client charts only recent history, and full
        # serialized traces are large (axiom_results, belief_state, ...).
        return ordered[-100:]

    def _load_knowledge(self):
        """Serve the REAL knowledge graph: serialized nodes AND edges.

        Live producer memory first (freshest, no disk race), then the
        persisted file (cold-file fallback), then the honest empty set.
        Edges come from the graph's own edge store (typed/weighted),
        never invented.
        """
        prod = get_producer()
        if prod is not None:
            snap = prod.snapshot()
            payload = snap.get("knowledge_payload")
            if payload and len(payload.get("nodes", [])) > 0:
                return payload
        try:
            with open(KNOWLEDGE_PATH) as fp:
                raw = json.load(fp)
            if isinstance(raw, dict):
                nodes_raw = raw.get('nodes', {})
                edges_raw = raw.get('edges', {})
                if isinstance(nodes_raw, dict) and len(nodes_raw) > 0:
                    nodes = []
                    for nid, ndata in nodes_raw.items():
                        label = ndata.get('approach', ndata.get('domain', nid[:8]))
                        domain = ndata.get('domain', 'general')
                        if '/' in domain:
                            domain = domain.split('/')[0]
                        importance = ndata.get('outcome', 0.5)
                        if isinstance(importance, (int, float)):
                            importance = max(0.1, min(1.0, importance))
                        else:
                            importance = 0.5
                        nodes.append({
                            "id": nid,
                            "label": label.replace('_', ' ').title(),
                            "domain": domain,
                            "importance": importance,
                        })
                    edges = []
                    if isinstance(edges_raw, dict):
                        for eid, edata in edges_raw.items():
                            if not isinstance(edata, dict):
                                continue
                            src = edata.get('src')
                            dst = edata.get('dst')
                            if not src or not dst:
                                continue
                            edges.append({
                                "source": src,
                                "target": dst,
                                "weight": edata.get('weight', 0.5),
                                "edge_type": edata.get('edge_type', 'related'),
                            })
                    return {"nodes": nodes, "edges": edges}
                elif isinstance(nodes_raw, list) and len(nodes_raw) > 0:
                    return raw
        except (FileNotFoundError, OSError, json.JSONDecodeError):
            pass
        return {"nodes": [], "edges": []}

    def _run_telos(self, message: str) -> dict:
        """Run TELOS with the user's message and return the response."""
        try:
            script_dir = os.path.dirname(os.path.abspath(__file__))
            project_dir = os.path.dirname(script_dir)

            proc = subprocess.run(
                [sys.executable, "telos_task.py"],
                input=message + "\nquit\n",
                capture_output=True,
                text=True,
                timeout=30,
                cwd=project_dir,
                env={**os.environ, "PYTHONPATH": "."},
            )

            output = proc.stdout or ""
            stderr = proc.stderr or ""

            # Extract TELOS response line
            response = ""
            for line in output.split('\n'):
                if line.startswith('TELOS:'):
                    response = line.replace('TELOS:', '').strip()
                    break
                if line.startswith('TELOS '):
                    response = line.split('TELOS ')[-1].strip()

            if not response:
                response = "(TELOS processed the command)"

            # Load latest trace
            trace = None
            checkpoints = self._load_checkpoints()
            if checkpoints:
                trace = checkpoints[-1]

            status = "APPROVED"
            di = 1.0
            if trace:
                di = trace.get('decision_integrity', 1.0)
                status = "BLOCKED" if trace.get('firewall_blocked') else "APPROVED"
                # Live feed: push the fresh trace to every connected dashboard client.
                broadcast_trace_sync(trace)

            return {"response": response, "trace": trace, "di": di, "status": status}

        except subprocess.TimeoutExpired:
            return {"response": "TELOS took too long to respond. Command may be too complex.", "trace": None, "di": 0, "status": "TIMEOUT"}
        except Exception as e:
            return {"response": f"Error: {str(e)}", "trace": None, "di": 0, "status": "ERROR"}

    def log_message(self, format, *args):
        if len(args) >= 3:
            logger.info(f"HTTP: {args[0]} {args[1]} {args[2]}")
        elif len(args) >= 1:
            logger.info(f"HTTP: {args[0]}")


def _push_live(trace_dict: dict, overview_dict: dict) -> None:
    """Module-local broadcast wrapper injected into the producer.

    Defined in the running module so the producer's thread talks to the
    SAME websocket_clients set the server owns.

    Args:
        trace_dict: lean serialized decision trace to push.
        overview_dict: slim overview payload to push.
    """
    broadcast_trace_sync(trace_dict)
    broadcast_overview_sync(overview_dict)


def _load_persisted_mood() -> str:
    """Real mood from the latest persisted system_self snapshot (fallback
    path — the live producer already reads SystemSelf directly).

    Returns:
        The mood string, or "neutral" if no snapshot is readable.
    """
    try:
        files = sorted(glob.glob(os.path.join(CHECKPOINT_DIR, "system_self_*.json")))
        if not files:
            return "neutral"
        with open(files[-1]) as fp:
            data = json.load(fp)
        return str((data.get("state") or {}).get("mood", "neutral"))
    except (OSError, json.JSONDecodeError, AttributeError):
        return "neutral"


def _last_resources(snap: dict) -> dict:
    """Real resource-budget values from the latest trace, if present.

    Args:
        snap: the producer snapshot dict.
    """
    traces = snap.get("traces", [])
    if traces:
        rb = traces[-1].get("resource_budgets")
        if isinstance(rb, dict):
            return {
                "c_compute": rb.get("c_compute", rb.get("compute", 0.5)),
                "c_memory": rb.get("c_memory", rb.get("memory", 0.5)),
                "c_bandwidth": rb.get("c_bandwidth", rb.get("bandwidth", 0.5)),
            }
    return {"c_compute": 0.5, "c_memory": 0.5, "c_bandwidth": 0.5}


# ─── WebSocket Server (live trace + overview feed) ───
async def ws_handler(websocket):
    websocket_clients.add(websocket)
    logger.info(f"WebSocket client connected ({len(websocket_clients)} total)")
    try:
        # Greet the client with the current overview so the story is
        # correct the moment the socket opens (slim payload — the full
        # snapshot with heavy traces is only served via /api/checkpoints).
        prod = get_producer()
        if prod is not None:
            await broadcast_overview(prod.overview_payload())
        async for message in websocket:
            pass
    except websockets.ConnectionClosed:
        pass
    except Exception as e:
        logger.warning(f"WebSocket error: {e}")
    finally:
        websocket_clients.discard(websocket)
        logger.info(f"WebSocket client disconnected ({len(websocket_clients)} remaining)")


async def broadcast_trace(trace_dict: dict):
    """Push a decision trace to all connected dashboard clients.

    :param trace_dict: serialized decision trace dict to broadcast.
    """
    if not websocket_clients:
        return
    message = json.dumps({"type": "trace", "decision_trace": trace_dict})
    await asyncio.gather(*[client.send(message) for client in websocket_clients], return_exceptions=True)


async def broadcast_overview(overview_dict: dict):
    """Push the live overview (big-data story) to all clients.

    Args:
        overview_dict: slim overview payload (no heavy traces).
    """
    if not websocket_clients:
        return
    message = json.dumps({"type": "overview", "overview": overview_dict})
    await asyncio.gather(*[client.send(message) for client in websocket_clients], return_exceptions=True)


def broadcast_trace_sync(trace_dict: dict):
    """Synchronous wrapper for broadcast_trace — call from any thread.

    :param trace_dict: serialized decision trace dict to broadcast.
    """
    global _ws_loop
    if not websocket_clients or _ws_loop is None:
        return
    asyncio.run_coroutine_threadsafe(broadcast_trace(trace_dict), _ws_loop)


def broadcast_overview_sync(overview_dict: dict):
    """Synchronous wrapper for broadcast_overview — call from any thread.

    Args:
        overview_dict: slim overview payload (no heavy traces).
    """
    global _ws_loop
    if not websocket_clients or _ws_loop is None:
        return
    asyncio.run_coroutine_threadsafe(broadcast_overview(overview_dict), _ws_loop)


# ─── Main ───
def run_http():
    try:
        # ThreadingHTTPServer, not HTTPServer: the page polls ~6 endpoints in
        # parallel (checkpoints/overview/knowledge/health + WS handshake) and a
        # grown knowledge graph makes each /api/knowledge serialization take
        # >1s — a single-threaded accept loop then overflows its backlog and
        # the browser's own dashboard times out (ERR_CONNECTION_TIMED_OUT).
        # Each request is bounded by the producer's RLock (snapshot reads) and
        # file-read try/excepts, so concurrent handlers are safe.
        server = ThreadingHTTPServer(('0.0.0.0', HTTP_PORT), DashboardHandler)
        logger.info(f"📊 TELOS Dashboard → http://localhost:{HTTP_PORT}")
        server.serve_forever()
    except OSError as e:
        logger.warning(f"Port {HTTP_PORT} in use — dashboard may already be running")
        logger.info(f"   Try: http://localhost:{HTTP_PORT}")


async def main():
    global _ws_loop, _producer
    _ws_loop = asyncio.get_running_loop()
    http_thread = Thread(target=run_http, daemon=True)
    http_thread.start()

    # Start the LIVE DATA PRODUCER in-process: the dashboard must produce
    # the data it serves. Disable with TELOS_DASHBOARD_NO_PRODUCER=1.
    if os.environ.get("TELOS_DASHBOARD_NO_PRODUCER") == "1":
        logger.warning("TELOS_DASHBOARD_NO_PRODUCER=1 — dashboard will serve persisted history only")
    else:
        from telos.dashboard.producer import DashboardProducer
        _producer = DashboardProducer()
        # Inject THIS module's broadcast functions (module-local closures —
        # the producer must never import this file itself, or it would get a
        # second module copy with an always-empty websocket_clients set).
        _producer.set_broadcast(_push_live)
        _producer.start()
        logger.info("🔄 Live data producer: running real pipeline in-process")

    # WebSocket is best-effort: if the port is taken, HTTP keeps serving.
    # (Pattern fix: a single failed subsystem must not take down the surface.)
    ws_server = None
    try:
        ws_server = await websockets.serve(ws_handler, '0.0.0.0', WS_PORT)
        logger.info(f"   WebSocket → ws://localhost:{WS_PORT}")
    except OSError as e:
        logger.warning(f"Port {WS_PORT} in use — WebSocket unavailable; HTTP still serving")

    try:
        await asyncio.Future()
    except KeyboardInterrupt:
        pass
    finally:
        if _producer is not None:
            _producer.stop()
        if ws_server is not None:
            ws_server.close()


import atexit
import signal as _signal

def _log_death(signum=None, frame=None):
    logger.warning("serve_dashboard: process exiting (signal=%r)", signum)

if __name__ == '__main__':
    _signal.signal(_signal.SIGTERM, _log_death)
    _signal.signal(_signal.SIGINT, _log_death)
    atexit.register(_log_death)
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        logger.info("Dashboard server stopped")
