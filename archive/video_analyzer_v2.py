"""TELOS-powered video analyzer — perception-aware ball tracking.

Uses the TELOS Pipeline's perception layer (PerceptionQuality + ResolutionGate)
to decide whether direct detection is viable. Falls back to proxy tracking
(motion hotspots, field center) when resolution is too low for reliable
ball detection.
"""
import cv2
import numpy as np
from fastapi import FastAPI, Query
from fastapi.responses import HTMLResponse, FileResponse
import uvicorn
import os

from telos.core.knowledge.graph import KnowledgeGraph
from telos.core.knowledge.recommender import KnowledgeRecommender
from telos.core.knowledge.recorder import OutcomeRecorder

from telos.core.runtime import TelosV14Pipeline, PipelineConfig
from telos.core.perception.proxy import compute_motion_hotspots
from telos.adapters.video_adapter import VideoDomainSimulator, VideoDomainAdapter

app = FastAPI()
VIDEO_PATH = "/tmp/telos_video/z0iMc4wTBqM.mp4"
KNOWLEDGE_PATH = "/tmp/telos_knowledge.json"
DOMAIN = "video_analysis"
BALL_DATA = None

STRATEGIES = {}

_TELOS_PIPELINE: TelosV14Pipeline = None


def _ensure_pipeline():
    global _TELOS_PIPELINE
    if _TELOS_PIPELINE is not None:
        return _TELOS_PIPELINE
    sim = VideoDomainSimulator()
    config = PipelineConfig(
        adapter=VideoDomainAdapter(), simulator=sim,
        compute_budget_ms=10.0, state_dim=3, n_worlds=3, horizon=2,
    )
    pipeline = TelosV14Pipeline(config)
    _TELOS_PIPELINE = pipeline
    return pipeline


def register(name):
    def wrap(fn):
        STRATEGIES[name] = {"fn": fn, "name": name}
        return fn
    return wrap


def _load_knowledge():
    kg = KnowledgeGraph()
    kg.load(KNOWLEDGE_PATH)
    return kg, KnowledgeRecommender(kg), OutcomeRecorder(kg)


def _hsv_white_mask(hsv_frame):
    return cv2.inRange(hsv_frame, (0, 0, 180), (180, 60, 255))


@register("field_tracker")
def detect_field_tracker(cap):
    h = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
    positions = []
    kf = cv2.KalmanFilter(4, 2)
    kf.measurementMatrix = np.array([[1, 0, 0, 0], [0, 1, 0, 0]], dtype=np.float32)
    kf.transitionMatrix = np.array([
        [1, 0, 1, 0], [0, 1, 0, 1],
        [0, 0, 1, 0], [0, 0, 0, 1],
    ], dtype=np.float32)
    kf.processNoiseCov = np.eye(4, dtype=np.float32) * 0.05
    kf.measurementNoiseCov = np.eye(2, dtype=np.float32) * 10
    kf.errorCovPost = np.eye(4, dtype=np.float32)
    init = False
    no_det = 0
    cap.set(cv2.CAP_PROP_POS_FRAMES, 0)
    while True:
        ret, frame = cap.read()
        if not ret:
            break
        hsv = cv2.cvtColor(frame, cv2.COLOR_BGR2HSV)
        green = cv2.inRange(hsv, (35, 40, 40), (85, 255, 255))
        green = cv2.erode(green, None, iterations=1)
        white = cv2.inRange(hsv, (0, 0, 180), (180, 60, 255))
        candidates = cv2.bitwise_and(white, cv2.bitwise_not(green))
        candidates[:int(0.15 * h), :] = 0
        candidates[int(0.85 * h):, :] = 0
        candidates = cv2.morphologyEx(
            candidates, cv2.MORPH_CLOSE,
            cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (3, 3)),
        )
        cnts, _ = cv2.findContours(
            candidates, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE
        )
        dets = []
        for cnt in cnts:
            area = cv2.contourArea(cnt)
            if area < 5 or area > 300:
                continue
            peri = cv2.arcLength(cnt, True)
            circ = 4 * np.pi * area / (peri * peri) if peri > 0 else 0
            if circ < 0.3:
                continue
            (cx, cy), cr = cv2.minEnclosingCircle(cnt)
            if cr < 2 or cr > 14:
                continue
            dets.append((int(cx), int(cy), max(int(cr), 2), area))
        dets.sort(key=lambda x: x[3])
        ball = None
        if init:
            pred = kf.predict()
            px, py = int(pred[0]), int(pred[1])
            best, best_d = None, 999
            for cx, cy, cr, area in dets:
                d = np.hypot(cx - px, cy - py)
                if d < 100 and d < best_d:
                    best = (cx, cy, cr)
                    best_d = d
            ball = best
        if ball is None and dets:
            cx, cy, cr, area = dets[0]
            if not init or no_det > 5:
                ball = (cx, cy, cr)
            else:
                d = np.hypot(cx - px, cy - py)
                if d < 150:
                    ball = (cx, cy, cr)
        if ball:
            cx, cy, cr = ball
            if init:
                kf.correct(np.array([[cx], [cy]], dtype=np.float32))
            else:
                kf.statePost = np.array([[cx], [cy], [0], [0]], dtype=np.float32)
                init = True
            no_det = 0
            positions.append({"x": cx, "y": cy, "r": cr, "detected": True})
        else:
            no_det += 1
            positions.append({"x": None, "y": None, "r": None, "detected": False})
    return positions


@register("tracker")
def detect_tracker(cap):
    h = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
    w = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
    positions = []
    tracker = None
    acquired = 0
    cx_s, cy_s, cr_s = None, None, None
    cap.set(cv2.CAP_PROP_POS_FRAMES, 0)
    while True:
        ret, frame = cap.read()
        if not ret:
            break
        hsv = cv2.cvtColor(frame, cv2.COLOR_BGR2HSV)
        green = cv2.inRange(hsv, (35, 40, 40), (85, 255, 255))
        green = cv2.erode(green, None, iterations=1)
        white = cv2.inRange(hsv, (0, 0, 180), (180, 60, 255))
        candidates = cv2.bitwise_and(white, cv2.bitwise_not(green))
        candidates[:int(0.15 * h), :] = 0
        candidates[int(0.85 * h):, :] = 0
        candidates = cv2.morphologyEx(
            candidates, cv2.MORPH_CLOSE,
            cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (3, 3)),
        )
        cnts, _ = cv2.findContours(
            candidates, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE
        )
        dets = []
        for cnt in cnts:
            area = cv2.contourArea(cnt)
            if area < 5 or area > 300:
                continue
            peri = cv2.arcLength(cnt, True)
            circ = 4 * np.pi * area / (peri * peri) if peri > 0 else 0
            if circ < 0.3:
                continue
            (cx, cy), cr = cv2.minEnclosingCircle(cnt)
            if cr < 2 or cr > 14:
                continue
            dets.append((int(cx), int(cy), max(int(cr), 2), area))
        dets.sort(key=lambda x: x[3])

        ball = None
        if tracker is not None:
            ok, bbox = tracker.update(frame)
            if ok:
                tx, ty, tw, th = [int(v) for v in bbox]
                ball = (tx + tw // 2, ty + th // 2, max(tw, th) // 2)
        if ball is None and dets:
            cx, cy, cr, area = dets[0]
            if acquired < 5:
                ball = (cx, cy, cr)
                acquired += 1
                if acquired == 3:
                    x = max(0, cx - cr - 4)
                    y = max(0, cy - cr - 4)
                    tw = min(w - x, 2 * cr + 8)
                    th = min(h - y, 2 * cr + 8)
                    if tw > 4 and th > 4:
                        tracker = cv2.TrackerMIL_create()
                        tracker.init(frame, (x, y, tw, th))
            else:
                if cx_s is not None:
                    d = np.hypot(cx - cx_s, cy - cy_s)
                    if d < 150:
                        ball = (cx, cy, cr)
                else:
                    ball = (cx, cy, cr)
        if ball:
            cx, cy, cr = ball
            cx_s, cy_s = cx, cy
            positions.append({"x": cx, "y": cy, "r": cr, "detected": True})
        else:
            positions.append({"x": None, "y": None, "r": None, "detected": False})
    return positions


@register("mog2_hsv")
def detect_mog2_hsv(cap):
    h = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
    positions = []
    sx, sy = None, None
    vx, vy = 0, 0
    bgs = cv2.createBackgroundSubtractorMOG2(
        history=500, varThreshold=32, detectShadows=False
    )
    cap.set(cv2.CAP_PROP_POS_FRAMES, 0)
    while True:
        ret, frame = cap.read()
        if not ret:
            break
        fg = bgs.apply(frame)
        fg = cv2.medianBlur(fg, 5)
        hsv = cv2.cvtColor(frame, cv2.COLOR_BGR2HSV)
        white = _hsv_white_mask(hsv)
        combined = cv2.bitwise_and(fg, white)
        combined[:int(0.25 * h), :] = 0
        combined[int(0.75 * h):, :] = 0
        cnts, _ = cv2.findContours(
            combined, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE
        )
        best_c, best_score = None, 0
        for cnt in cnts:
            area = cv2.contourArea(cnt)
            if area < 5:
                continue
            peri = cv2.arcLength(cnt, True)
            circ = 4 * np.pi * area / (peri * peri) if peri > 0 else 0
            (cx, cy), cr = cv2.minEnclosingCircle(cnt)
            score = (
                max(0, circ - 0.2) * 20
                + max(0, 1.0 - abs(area - 50) / 150) * 15
                + max(0, 10 - abs(cr - 6)) * 3
                + max(0, 50 - abs(cy - h * 0.5)) * 0.3
            )
            if sx is not None:
                px = sx + vx
                py = sy + vy
                d = np.hypot(cx - px, cy - py)
                if d > 80:
                    score = score * 80 / max(d, 1)
                else:
                    score += (80 - d) * 1.0
            if score > best_score:
                best_score = score
                best_c = (int(cx), int(cy), int(cr))
        if best_c and best_score > 5:
            cx, cy, cr = best_c
            if sx is not None:
                vx = int(vx * 0.3 + (cx - sx) * 0.7)
                vy = int(vy * 0.3 + (cy - sy) * 0.7)
            sx, sy = cx, cy
            positions.append({
                "x": sx, "y": sy, "r": max(cr, 4), "detected": True
            })
        else:
            positions.append({
                "x": None, "y": None, "r": None, "detected": False
            })
    return positions


def _proxy_track(cap, prev_gray=None):
    h = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
    w = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
    positions = []
    prev = None
    frame_idx = 0
    cap.set(cv2.CAP_PROP_POS_FRAMES, 0)
    while True:
        ret, frame = cap.read()
        if not ret:
            break
        gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
        gray = cv2.GaussianBlur(gray, (5, 5), 0)
        hotspots = []
        field_center = np.array([w / 2, h / 2])
        if prev is not None:
            flow = cv2.calcOpticalFlowFarneback(
                prev, gray, None, 0.5, 3, 15, 3, 5, 1.2, 0
            )
            mag, _ = cv2.cartToPolar(flow[..., 0], flow[..., 1])
            threshold = np.percentile(mag, 85) if mag.size > 0 else 15
            mag_copy = mag.copy()
            for _ in range(5):
                idx = np.argmax(mag_copy)
                if mag_copy.flat[idx] < threshold:
                    break
                y, x = np.unravel_index(idx, mag_copy.shape)
                hotspots.append({"x": int(x), "y": int(y), "magnitude": float(mag[y, x])})
                y0, y1 = max(0, y - 8), min(mag.shape[0], y + 8)
                x0, x1 = max(0, x - 8), min(mag.shape[1], x + 8)
                mag_copy[y0:y1, x0:x1] = 0
        prev = gray
        if hotspots:
            avg_x = np.mean([h["x"] for h in hotspots])
            avg_y = np.mean([h["y"] for h in hotspots])
            positions.append({
                "x": int(avg_x), "y": int(avg_y),
                "r": 6, "detected": True,
                "hotspots": hotspots[:3],
                "proxy": True,
            })
        else:
            positions.append({
                "x": int(field_center[0]), "y": int(field_center[1]),
                "r": 6, "detected": True,
                "hotspots": [],
                "proxy": True,
            })
        frame_idx += 1
    return positions


def _proxy_track(cap):
    h = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
    w = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
    positions = []
    prev = None
    cap.set(cv2.CAP_PROP_POS_FRAMES, 0)
    while True:
        ret, frame = cap.read()
        if not ret:
            break
        gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
        gray = cv2.GaussianBlur(gray, (5, 5), 0)
        hotspots = []
        if prev is not None:
            hotspots = compute_motion_hotspots(prev, gray)
        prev = gray
        if hotspots:
            avg_x = np.mean([h["x"] for h in hotspots])
            avg_y = np.mean([h["y"] for h in hotspots])
            positions.append({
                "x": int(avg_x), "y": int(avg_y),
                "r": 6, "detected": True,
                "hotspots": hotspots[:3],
                "proxy": True,
            })
        else:
            positions.append({
                "x": int(w / 2), "y": int(h / 2),
                "r": 6, "detected": True,
                "hotspots": [],
                "proxy": True,
            })
    return positions


@register("hough_circles")
def detect_hough_circles(cap):
    h = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
    w = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
    positions = []
    cap.set(cv2.CAP_PROP_POS_FRAMES, 0)
    while True:
        ret, frame = cap.read()
        if not ret:
            break
        gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
        gray = cv2.GaussianBlur(gray, (9, 9), 2)
        circles = cv2.HoughCircles(
            gray, cv2.HOUGH_GRADIENT, dp=1.2, minDist=20,
            param1=50, param2=30, minRadius=3, maxRadius=15
        )
        if circles is not None:
            circles = np.round(circles[0, :]).astype("int")
            best = None
            best_score = 0
            for (cx, cy, cr) in circles:
                if cy < h * 0.25 or cy > h * 0.75:
                    continue
                score = cr
                if score > best_score:
                    best_score = score
                    best = (int(cx), int(cy), int(cr))
            if best:
                positions.append({
                    "x": best[0], "y": best[1], "r": best[2],
                    "detected": True
                })
            else:
                positions.append({
                    "x": None, "y": None, "r": None, "detected": False
                })
        else:
            positions.append({
                "x": None, "y": None, "r": None, "detected": False
            })
    return positions


def pick_strategy(rec):
    """Auto-switch: pick the best non-failed strategy for this domain."""
    failures = {f["approach"] for f in rec.failures(DOMAIN)}

    if failures:
        print(f"[Knowledge] Known failures to skip: {failures}")

    best = rec.recommend(DOMAIN)
    if best and best not in failures and best in STRATEGIES:
        print(f"[Knowledge] Using proven approach: {best}")
        return best

    candidates = [s for s in STRATEGIES if s not in failures]
    if not candidates:
        print("[Knowledge] All strategies are known failures — trying first anyway")
        return list(STRATEGIES.keys())[0]

    chosen = candidates[0]
    print(f"[Knowledge] No proven approach — trying: {chosen}")
    return chosen


def process_video():
    global BALL_DATA
    if not os.path.exists(VIDEO_PATH):
        print(f"[Video] File not found: {VIDEO_PATH}")
        return

    cap = cv2.VideoCapture(VIDEO_PATH)
    w = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
    h = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))

    kg, rec, out = _load_knowledge()

    # ── TELOS Perception: Assess quality ──
    pipeline = _ensure_pipeline()
    percept = pipeline.assess_perception(w, h, target_px=6)
    quality_report = percept["quality_report"]
    gate_verdict = percept["gate_verdict"]
    explanation = percept["explanation"]
    capabilities = percept["capabilities"]
    print(f"[Telos] Quality={quality_report['quality_score']:.3f} "
          f"gate={'PASS' if gate_verdict['passed'] else 'BLOCK'} "
          f"proxy={gate_verdict['proxy_activated']}")
    print(f"[Telos] {explanation['summary']}")

    approach = "proxy_track"
    if gate_verdict["proxy_activated"]:
        print(f"[Video] Using proxy tracking (direct detection not viable)")
        positions = _proxy_track(cap)
    else:
        approach = pick_strategy(rec)
        strategy = STRATEGIES[approach]
        print(f"[Video] Running direct strategy: {approach}")
        positions = strategy["fn"](cap)

    proxy = gate_verdict["proxy_activated"]
    cap.release()
    BALL_DATA = {"pos": positions, "fps": 30, "w": w, "h": h, "proxy": proxy}

    detected = sum(1 for p in positions if p.get("detected"))
    total = len(positions)
    pct = detected / max(total, 1)
    mode = "proxy" if proxy else "direct"
    print(f"[Knowledge] {mode}: {detected}/{total} ({pct:.0%})")

    out.record(DOMAIN, approach, pct,
               params={
                   "detected": detected, "total": total,
                   "quality_score": round(quality_report["quality_score"], 3),
                   "resolution": f"{w}x{h}",
                   "proxy_mode": proxy,
               })
    kg.save(KNOWLEDGE_PATH)


@app.get('/')
async def root():
    return HTMLResponse("""<html><body style="margin:0;background:#111;font-family:monospace;color:#fff">
<div style="position:relative;width:500px;margin:20px auto">
<video id="v" src="/video" controls style="width:100%;display:block"></video>
<canvas id="c" style="position:absolute;top:0;left:0;width:100%;height:100%;pointer-events:none"></canvas>
<div id="h" style="position:absolute;top:10px;left:10px;color:#ff0;font-size:14px;background:rgba(0,0,0,0.7);padding:4px 10px;border-radius:4px;pointer-events:none"></div>
<div id="s" style="position:absolute;bottom:10px;left:10px;color:#0f0;font-size:12px;background:rgba(0,0,0,0.7);padding:4px 10px;border-radius:4px;pointer-events:none"></div>
<div id="m" style="position:absolute;top:10px;right:10px;color:#aaa;font-size:11px;background:rgba(0,0,0,0.6);padding:3px 8px;border-radius:4px;pointer-events:none">...</div>
<div id="wb" style="position:absolute;bottom:50px;right:10px;max-width:280px;background:rgba(0,0,0,0.88);padding:10px 14px;border-radius:8px;font-size:11px;line-height:1.5;pointer-events:none;display:none"></div>
</div>
<div style="width:500px;margin:0 auto;text-align:center;display:flex;gap:8px;justify-content:center">
<button id="b" style="background:#ff0;color:#000;border:none;padding:8px 24px;font-size:14px;border-radius:4px;cursor:pointer">Mark Ball</button>
<button id="r" style="background:#555;color:#fff;border:none;padding:8px 16px;font-size:14px;border-radius:4px;cursor:pointer">⏮ Frame 0</button>
<button id="wi" style="background:#666;color:#fff;border:none;padding:8px 14px;font-size:13px;border-radius:4px;cursor:pointer">Why?</button>
</div>
<div id="pv" style="width:500px;margin:10px auto;display:none">
<img id="pi" src="/preview" style="width:100%;border-radius:4px">
<p style="font-size:12px;color:#aaa;text-align:center;margin:4px 0">Yellow dots = ball candidates. Click a yellow dot in the video above.</p>
</div>
<script>
var d=null,w=1,h=1,tracking=false,marking=false,fr=0;
var v=document.getElementById('v'),c=document.getElementById('c'),cx=c.getContext('2d');
var hd=document.getElementById('h'),st=document.getElementById('s'),b=document.getElementById('b');
var md=document.getElementById('m');
fetch('/data').then(function(r){return r.json()}).then(function(x){d=x;w=x.w;h=x.h;
  var det=d.pos.filter(function(p){return p.detected}).length;
  st.textContent=(det/d.pos.length*100).toFixed(0)+'% '+(d.proxy?'proxy':'direct');
  md.textContent=d.proxy?'PROXY':'DIRECT';
  md.style.color=d.proxy?'#f80':'#0f0';
  draw();
});
v.addEventListener('timeupdate',function(){fr=Math.round(v.currentTime*30);});
document.getElementById('wi').addEventListener('click',function(){
  if(wbx.style.display!='block'){
    fetch('/info').then(function(r){return r.json()}).then(function(p){
      var e=p.explanation||{};
      var sug=(e.suggestions||[]).map(function(s){return '• '+s.label;}).join('<br>');
      var caps=(p.capabilities||[]).filter(function(c){return c.feasible;}).map(function(c){return '✓ '+c.name;}).join('<br>');
      wbx.innerHTML='<b style="color:#ff0">Why '+md.textContent+'</b><br>'+
        (e.summary||'')+'<br><br>'+
        '<b style="color:#8af">Quality:</b> '+(e.quality_score*100).toFixed(0)+'%<br>'+
        '<b style="color:#8af">Suggestions:</b><br>'+sug+'<br>'+
        '<b style="color:#8af">Feasible capabilities:</b><br>'+(caps||'none');
      wbx.style.display='block';
    });
  }else{wbx.style.display='none';}
});
document.getElementById('r').addEventListener('click',function(){v.currentTime=0;v.pause();});
b.addEventListener('click',function(){
  marking=!marking;
  c.style.pointerEvents=marking?'auto':'none';
  c.style.cursor=marking?'crosshair':'default';
  b.textContent=marking?'Click video to mark':'Mark Ball';
  hd.textContent=marking?'Pause, click a yellow dot in the video':'';
  document.getElementById('pv').style.display=marking?'block':'none';
});
c.addEventListener('click',function(e){
  if(!marking)return;
  var r=c.getBoundingClientRect();
  var bx=(e.clientX-r.left)*w/r.width;
  var by=(e.clientY-r.top)*h/r.height;
  hd.textContent='Tracking...';marking=false;
  c.style.pointerEvents='none';c.style.cursor='default';
  b.textContent='Mark Ball';
  fetch('/mark?x='+Math.round(bx)+'&y='+Math.round(by)+'&f='+fr).then(function(r){return r.json()}).then(function(x){
    tracking=true;
    hd.textContent='Tracked from frame '+fr;
    st.textContent=x.detected;
    fetch('/data').then(function(r){return r.json()}).then(function(x){d=x;w=x.w;h=x.h;v.currentTime=0;});
  });
});
function draw(){
  if(!d){requestAnimationFrame(draw);return;}
  c.width=w;c.height=h;
  cx.clearRect(0,0,c.width,c.height);
  var f=Math.round(v.currentTime*30);
  var p=d.pos[f];
  if(p&&p.detected){
    if(p.proxy){
      // Proxy mode: draw motion zone glow + hotspot dots
      var grd=cx.createRadialGradient(p.x,p.y,2,p.x,p.y,40);
      grd.addColorStop(0,'rgba(255,136,0,0.4)');
      grd.addColorStop(1,'rgba(255,136,0,0)');
      cx.fillStyle=grd;cx.beginPath();cx.arc(p.x,p.y,40,0,2*Math.PI);cx.fill();
      cx.strokeStyle='#f80';cx.lineWidth=2;cx.setLineDash([4,4]);
      cx.beginPath();cx.arc(p.x,p.y,18,0,2*Math.PI);cx.stroke();cx.setLineDash([]);
      // Hotspot dots
      if(p.hotspots){p.hotspots.forEach(function(h){
        cx.beginPath();cx.arc(h.x,h.y,3,0,2*Math.PI);
        cx.fillStyle='rgba(255,136,0,0.6)';cx.fill();
      });}
      cx.fillStyle='#f80';cx.font='11px monospace';
      cx.fillText('PROXY ZONE',p.x-30,p.y-24);
    }else{
      // Direct mode: show ball circle
      cx.beginPath();cx.arc(p.x,p.y,18,0,2*Math.PI);
      cx.strokeStyle='#ff0';cx.lineWidth=6;cx.stroke();
      cx.beginPath();cx.arc(p.x,p.y,6,0,2*Math.PI);
      cx.fillStyle='#f00';cx.fill();
      cx.fillStyle='#fff';cx.font='bold 16px monospace';
      cx.fillText('BALL',p.x+24,p.y+8);
    }
  }
  requestAnimationFrame(draw);
}
</script>
</body></html>""")


@app.get('/video')
def video():
    return FileResponse(VIDEO_PATH)


@app.get('/data')
def data():
    if not BALL_DATA:
        process_video()
    return BALL_DATA


@app.get('/info')
def info():
    if not BALL_DATA:
        process_video()
    w = BALL_DATA["w"]
    h = BALL_DATA["h"]
    percept = _ensure_pipeline().assess_perception(w, h, target_px=6)
    return percept


@app.get('/preview')
def preview():
    cap = cv2.VideoCapture(VIDEO_PATH)
    ret, frame = cap.read()
    cap.release()
    if not ret:
        return Response("", media_type="image/jpeg")
    h, w = frame.shape[:2]
    hsv = cv2.cvtColor(frame, cv2.COLOR_BGR2HSV)
    green = cv2.inRange(hsv, (35, 40, 40), (85, 255, 255))
    green = cv2.erode(green, None, iterations=1)
    white = cv2.inRange(hsv, (0, 0, 180), (180, 60, 255))
    cand = cv2.bitwise_and(white, cv2.bitwise_not(green))
    cand = cv2.morphologyEx(cand, cv2.MORPH_CLOSE,
                            cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (3, 3)))
    cnts, _ = cv2.findContours(cand, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    for cnt in cnts:
        area = cv2.contourArea(cnt)
        if area < 5 or area > 300:
            continue
        peri = cv2.arcLength(cnt, True)
        circ = 4 * np.pi * area / (peri * peri) if peri > 0 else 0
        if circ < 0.3:
            continue
        (cx, cy), cr = cv2.minEnclosingCircle(cnt)
        if cr < 2 or cr > 14:
            continue
        cv2.circle(frame, (int(cx), int(cy)), max(int(cr) + 4, 8), (0, 255, 255), 2)
        cv2.circle(frame, (int(cx), int(cy)), 2, (0, 255, 255), -1)
    ret2, buf = cv2.imencode('.jpg', frame)
    from fastapi.responses import Response
    return Response(buf.tobytes(), media_type="image/jpeg")


@app.get('/feedback')
def feedback(wrong: str = Query(""), approach: str = Query("unknown")):
    kg, rec, out = _load_knowledge()
    percept = _ensure_pipeline().assess_perception(360, 640)
    out.from_user(DOMAIN, approach, wrong or "circle not on ball",
                  tags=["video_analyzer"])
    kg.save(KNOWLEDGE_PATH)
    print(f"[Feedback] User reported: {approach} — {wrong}")
    return {
        "recorded": True, "domain": DOMAIN, "approach": approach,
        "feedback": wrong or "circle not on ball"
    }


@app.get('/recommend')
def recommend(domain: str = Query(DOMAIN)):
    kg, rec, out = _load_knowledge()
    return rec.summarize(domain)


def _track_one_direction(cap, sx, sy, start_frame, forward):
    h = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
    w = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
    total = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
    positions = {}
    px, py = sx, sy
    no_det = 0

    frames = list(range(start_frame, total)) if forward else list(range(start_frame - 1, -1, -1))
    if not frames:
        return positions, w, h

    for fidx in frames:
        cap.set(cv2.CAP_PROP_POS_FRAMES, fidx)
        ret, frame = cap.read()
        if not ret:
            break
        hsv = cv2.cvtColor(frame, cv2.COLOR_BGR2HSV)
        green = cv2.inRange(hsv, (35, 40, 40), (85, 255, 255))
        green = cv2.erode(green, None, iterations=1)
        white = cv2.inRange(hsv, (0, 0, 180), (180, 60, 255))
        cand = cv2.bitwise_and(white, cv2.bitwise_not(green))
        cand[:int(0.15 * h), :] = 0
        cand[int(0.85 * h):, :] = 0
        cand = cv2.morphologyEx(
            cand, cv2.MORPH_CLOSE,
            cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (3, 3)),
        )
        cnts, _ = cv2.findContours(
            cand, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE
        )
        dets = []
        for cnt in cnts:
            area = cv2.contourArea(cnt)
            if area < 5 or area > 300:
                continue
            peri = cv2.arcLength(cnt, True)
            circ = 4 * np.pi * area / (peri * peri) if peri > 0 else 0
            if circ < 0.3:
                continue
            (cx, cy), cr = cv2.minEnclosingCircle(cnt)
            if cr < 2 or cr > 14:
                continue
            dets.append((int(cx), int(cy), max(int(cr), 2), area))
        best, best_d = None, 999
        gate = 60 if no_det == 0 else (100 if no_det < 5 else 250)
        for cx, cy, cr, area in dets:
            d = np.hypot(cx - px, cy - py)
            if d < gate and d < best_d:
                best = (cx, cy, cr)
                best_d = d
        if best is None and dets and no_det >= 5:
            cx, cy, cr, area = dets[0]
            if np.hypot(cx - px, cy - py) < 300:
                best = (cx, cy, cr)
        if best:
            cx, cy, cr = best
            px = int(px * 0.3 + cx * 0.7)
            py = int(py * 0.3 + cy * 0.7)
            no_det = 0
            positions[fidx] = {"x": cx, "y": cy, "r": cr, "detected": True}
        else:
            no_det += 1
            positions[fidx] = {"x": None, "y": None, "r": None, "detected": False}
    return positions, w, h


@app.get('/mark')
def mark_ball(x: int = Query(...), y: int = Query(...), f: int = Query(0)):
    global BALL_DATA
    cap = cv2.VideoCapture(VIDEO_PATH)
    total = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
    w = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
    h = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))

    fwd, _, _ = _track_one_direction(cap, x, y, f + 1, True)
    bwd, _, _ = _track_one_direction(cap, x, y, f, False)

    positions = []
    for i in range(total):
        if i == f:
            positions.append({"x": x, "y": y, "r": 6, "detected": True})
        elif i in bwd:
            positions.append(bwd[i])
        elif i in fwd:
            positions.append(fwd[i])
        else:
            positions.append({"x": None, "y": None, "r": None, "detected": False})

    cap.release()
    BALL_DATA = {"pos": positions, "fps": 30, "w": w, "h": h, "proxy": False}
    detected = sum(1 for p in positions if p["detected"])
    print(f"[Mark] Seeded at frame {f} ({x},{y}): {detected}/{total} ({100*detected/total:.0f}%)")
    kg, rec, out = _load_knowledge()
    percept = _ensure_pipeline().assess_perception(w, h)
    out.record(DOMAIN, "user_seeded_tracker", detected / max(total, 1),
               params={
                   "seed_x": x, "seed_y": y, "seed_frame": f,
                   "detected": detected, "total": total,
                   "quality_score": round(percept["quality_report"]["quality_score"], 3),
               })
    kg.save(KNOWLEDGE_PATH)
    return {"marked": True, "detected": f"{detected}/{total} ({100*detected/total:.0f}%)"}


if __name__ == '__main__':
    uvicorn.run(app, host='0.0.0.0', port=8001)
