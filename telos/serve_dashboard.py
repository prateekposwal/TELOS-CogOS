"""
TELOS Dashboard Server — serves the dashboard HTML + checkpoint data + WebSocket live feed.

Usage:
    python3 serve_dashboard.py
    
Then open http://localhost:8765 in your browser.
"""

import json
import os
import glob
import asyncio
import websockets
import logging
import subprocess
import sys
from http.server import HTTPServer, SimpleHTTPRequestHandler
from urllib.parse import urlparse
from threading import Thread

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger('telos_dashboard')

CHECKPOINT_DIR = "/tmp/telos_checkpoints"
KNOWLEDGE_PATH = "/tmp/telos_knowledge.json"
HTTP_PORT = 8765
WS_PORT = 8766

# Store for live WebSocket clients
websocket_clients = set()
_ws_loop = None  # set when WebSocket server starts; asyncio.AbstractEventLoop

# Store for TELOS conversation context
telos_context = {"cycle": 0, "last_response": ""}

# ─── HTTP Server ───
class DashboardHandler(SimpleHTTPRequestHandler):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, directory=os.path.dirname(os.path.abspath(__file__)), **kwargs)
    
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
        
        if parsed.path == '/api/status':
            self.send_json({
                'clients': len(websocket_clients),
                'checkpoints': len(glob.glob(os.path.join(CHECKPOINT_DIR, 'checkpoint_*.json'))),
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
        self.wfile.write(json.dumps(data).encode())
    
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
        """Load latest benchmark snapshot or return placeholder."""
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
        # Return placeholder with zeros so UI always renders
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
        """Load health score summary from latest benchmark."""
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
        }

    def _load_checkpoints(self):
        checkpoints = []
        for f in sorted(glob.glob(os.path.join(CHECKPOINT_DIR, 'checkpoint_*.json'))):
            try:
                with open(f) as fp:
                    data = json.load(fp)
                    if 'decision_trace' in data:
                        checkpoints.append(data['decision_trace'])
            except (OSError, json.JSONDecodeError):
                pass
        return checkpoints
    
    def _load_knowledge(self):
        """Serve the REAL knowledge graph: serialized nodes AND edges.

        Edges come from the graph's own edge store (typed/weighted), never
        invented. If the graph has no edges yet, the dashboard shows an
        honest empty-set state instead of fabricated links.
        """
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


# ─── WebSocket Server (live trace feed) ───
async def ws_handler(websocket):
    websocket_clients.add(websocket)
    logger.info(f"WebSocket client connected ({len(websocket_clients)} total)")
    try:
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
    """Call this to push live traces to the dashboard. Thread-safe."""
    if not websocket_clients:
        return
    message = json.dumps({"type": "trace", "decision_trace": trace_dict})
    await asyncio.gather(*[client.send(message) for client in websocket_clients], return_exceptions=True)

def broadcast_trace_sync(trace_dict: dict):
    """Synchronous wrapper for broadcast_trace — call from any thread."""
    global _ws_loop
    if not websocket_clients or _ws_loop is None:
        return
    asyncio.run_coroutine_threadsafe(broadcast_trace(trace_dict), _ws_loop)


# ─── Main ───
def run_http():
    try:
        server = HTTPServer(('0.0.0.0', HTTP_PORT), DashboardHandler)
        logger.info(f"📊 TELOS Dashboard → http://localhost:{HTTP_PORT}")
        server.serve_forever()
    except OSError as e:
        logger.warning(f"Port {HTTP_PORT} in use — dashboard may already be running")
        logger.info(f"   Try: http://localhost:{HTTP_PORT}")

async def main():
    global _ws_loop
    _ws_loop = asyncio.get_running_loop()
    http_thread = Thread(target=run_http, daemon=True)
    http_thread.start()
    
    try:
        async with websockets.serve(ws_handler, '0.0.0.0', WS_PORT):
            logger.info(f"   WebSocket → ws://localhost:{WS_PORT}")
            await asyncio.Future()
    except OSError as e:
        logger.warning(f"Port {WS_PORT} in use — WebSocket may already be running")

if __name__ == '__main__':
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        logger.info("Dashboard server stopped")
