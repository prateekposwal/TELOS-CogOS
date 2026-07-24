"""
TELOS Video Analyzer — TELOS reasons about recorded video content.

Demonstrates how TELOS processes live match footage through its
7-phase Pipeline: extracts frame features, simulates alternatives,
validates with Council, and produces structured annotations.

Usage:
    python3 telos_video_analyze.py /path/to/video.mp4
    python3 telos_video_analyze.py /path/to/video.mp4 --serve
"""

import sys
import os
import json
import asyncio
import numpy as np
import logging
import time
from dataclasses import dataclass, field
from typing import List, Optional, Dict, Any

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger('telos_video')

# ── TELOS imports ──
from telos.core.runtime import PipelineConfig, TelosV14Pipeline
from telos.core.streams.implementations import (
    ReflexStream, PerceptionStream, MemoryStream, PlanningStream,
)
from telos.core.council.validators import (
    RealityValidator, ConstraintValidator, MemoryAdvisor, MissionDriftDetector,
)
from telos.core.ledger.skill_library import SkillLibrary
from telos.core.simulation import CounterfactualEngine
from telos.core.contracts.domain_model import DomainSimulator, DomainAdapter, EvaluationReport
from telos.world.facts import DomainFacts
from telos.world.world import World
from telos.intent_ir import IntentIR


# ── Features extracted from video ──
@dataclass
class FrameFeatures:
    index: int
    timestamp: float
    brightness: float
    motion_magnitude: float
    edge_density: float
    mean_color: List[float]
    has_face: bool
    has_motion: bool
    flow_angle: Optional[np.ndarray] = None


@dataclass
class VideoAnalysis:
    path: str
    duration: float
    fps: float
    frame_count: int
    width: int
    height: int
    segments: List[Dict] = field(default_factory=list)


# ── Video Domain Simulator ──
class VideoDomainSimulator(DomainSimulator):
    """Simulates video analysis — TELOS reasons about frame features."""

    def initialize(self): pass
    def cleanup(self): pass

    def legal_transitions(self, state):
        # Actions: tag_event, log_frame, skip_segment, flag_anomaly, generate_highlight
        return [
            np.array([1, 0, 0, 0, 0]),
            np.array([0, 1, 0, 0, 0]),
            np.array([0, 0, 1, 0, 0]),
            np.array([0, 0, 0, 1, 0]),
            np.array([0, 0, 0, 0, 1]),
        ]

    def transition(self, state, action):
        return state

    def simulate(self, state, horizon):
        n_futures = 4
        futures = []
        for _ in range(n_futures):
            brightness = state[0]
            motion = state[1]
            action_type = np.random.randint(0, 5)
            actions = ["tag_event", "log_frame", "skip_segment",
                       "flag_anomaly", "generate_highlight"]

            fut_state = np.array([
                brightness + np.random.randn() * 0.05,
                motion + np.random.randn() * 0.05,
                state[2] + 1,
                float(action_type),
                float(np.random.rand()),
            ])
            futures.append(World(state=fut_state, metadata={
                "action": actions[action_type],
                "confidence": float(np.random.uniform(0.6, 0.99)),
            }))
        return futures

    def get_facts(self, state):
        return DomainFacts(
            state=state.copy(),
            resources={"motion": float(state[1]), "brightness": float(state[0])},
            constraints=[],
            events=[],
            metrics={
                "frame": float(state[2]),
                "has_motion": float(state[1] > 0.3),
                "uncertainty": float(0.5 - abs(state[0] - 0.5)),
            },
            metadata={
                "action": "analyze",
            },
        )

    def terminal(self, state):
        return state[2] >= 100

    def evaluate(self, state):
        return EvaluationReport(
            objectives={"information_gain": float(state[0] * state[1])},
            risks=float(max(0, state[3])),
        )


class VideoAdapter(DomainAdapter):
    def forward(self, x): return x
    def inverse(self, x): return x

    def intent_to_action(self, intent, state, md):
        if "action_vector" in intent.params:
            return np.asarray(intent.params["action_vector"], dtype=float)
        # Default: tag as event if motion > threshold
        if state[1] > 0.3:
            return np.array([1, 0, 0, 0, 0])
        return np.array([0, 1, 0, 0, 0])

    @property
    def name(self): return "video_analyzer"


# ── Feature Extraction ──
def extract_features(video_path: str, max_frames: int = 120) -> VideoAnalysis:
    """Extract frame-level features from video using OpenCV."""
    import cv2

    cap = cv2.VideoCapture(video_path)
    if not cap.isOpened():
        raise ValueError(f"Cannot open video: {video_path}")

    fps = cap.get(cv2.CAP_PROP_FPS)
    total_frames = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
    duration = total_frames / fps if fps > 0 else 0
    width = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
    height = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))

    logger.info(f"Video: {os.path.basename(video_path)} "
                f"({width}x{height}, {fps:.1f}fps, {total_frames} frames, "
                f"{duration:.1f}s)")

    step = max(1, total_frames // max_frames)
    frames: List[FrameFeatures] = []
    prev_gray = None
    prev_hist = None
    idx = 0
    scene_cuts = []
    frame_hists = []

    while True:
        ret, frame = cap.read()
        if not ret:
            break
        if idx % step != 0:
            idx += 1
            continue

        gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
        hsv = cv2.cvtColor(frame, cv2.COLOR_BGR2HSV)

        brightness = float(np.mean(gray) / 255.0)
        edges = cv2.Canny(gray, 50, 150)
        edge_density = float(np.mean(edges) / 255.0)

        # Motion magnitude and direction
        motion_mag = 0.0
        flow_angle = None
        if prev_gray is not None:
            flow = cv2.calcOpticalFlowFarneback(
                prev_gray, gray, None, 0.5, 3, 15, 3, 5, 1.2, 0
            )
            mag, ang = cv2.cartToPolar(flow[..., 0], flow[..., 1])
            motion_mag = float(np.mean(mag))
            flow_angle = ang

        mean_color = list(np.mean(hsv.reshape(-1, 3), axis=0) / 255.0)

        # Scene change detection via histogram comparison
        hist = cv2.calcHist([hsv], [0, 1], None, [30, 32], [0, 180, 0, 256])
        cv2.normalize(hist, hist, 0, 1, cv2.NORM_MINMAX)
        frame_hists.append(hist.flatten())
        if prev_hist is not None and len(frame_hists) >= 2:
            d = cv2.compareHist(frame_hists[-2], frame_hists[-1], cv2.HISTCMP_CHISQR)
            if d > 0.5:
                scene_cuts.append(len(frames))
        prev_hist = hist

        # Face detection
        has_face = False
        try:
            face_cascade = cv2.CascadeClassifier(
                cv2.data.haarcascades + "haarcascade_frontalface_default.xml"
            )
            faces = face_cascade.detectMultiScale(gray, 1.1, 4)
            has_face = len(faces) > 0
        except AttributeError:
            pass

        frame_data = FrameFeatures(
            index=idx,
            timestamp=idx / fps,
            brightness=brightness,
            motion_magnitude=motion_mag,
            edge_density=edge_density,
            mean_color=mean_color,
            has_face=has_face,
            has_motion=motion_mag > 0.3,
        )
        frame_data.flow_angle = flow_angle
        frames.append(frame_data)

        prev_gray = gray
        idx += 1

    cap.release()

    analysis = VideoAnalysis(
        path=video_path,
        duration=duration,
        fps=fps,
        frame_count=len(frames),
        width=width,
        height=height,
    )
    logger.info(f"Extracted {len(frames)} frames ({idx} sampled), {len(scene_cuts)} scene cuts")

    # Segment analysis
    dir_names = ["→E", "↗NE", "↑N", "↖NW", "←W", "↙SW", "↓S", "↘SE"]

    for i in range(0, len(frames), 10):
        seg = frames[i:i + 10]
        if not seg:
            continue
        avg_brightness = float(np.mean([f.brightness for f in seg]))
        avg_motion = float(np.mean([f.motion_magnitude for f in seg]))
        avg_edge = float(np.mean([f.edge_density for f in seg]))
        faces = sum(1 for f in seg if f.has_face)

        # Color histogram: dominant colors in segment
        h_bins = 8; s_bins = 4; v_bins = 4
        all_hsv = []
        for f in seg:
            all_hsv.append(f.mean_color)
        all_hsv = np.array(all_hsv)
        if len(all_hsv) > 0:
            h_centers = np.linspace(0, 1, h_bins + 1)[:-1] + 0.5 / h_bins
            s_centers = np.linspace(0, 1, s_bins + 1)[:-1] + 0.5 / s_bins
            v_centers = np.linspace(0, 1, v_bins + 1)[:-1] + 0.5 / v_bins
        else:
            h_centers = s_centers = v_centers = []
        dominant_colors = [
            {"h": round(float(h_centers[0]), 2), "s": round(float(s_centers[0]), 2), "v": round(float(v_centers[0]), 2)}
        ] if len(h_centers) > 0 else []

        # Motion direction histogram per segment
        dir_counts = [0] * 8
        for f in seg:
            if hasattr(f, 'flow_angle') and f.flow_angle is not None:
                ang = np.mean(f.flow_angle)
                bin_idx = int((ang / (2 * np.pi)) * 8) % 8
                dir_counts[bin_idx] += 1
        total_dir = max(sum(dir_counts), 1)
        motion_directions = [
            {"direction": dir_names[j], "pct": round(100 * dir_counts[j] / total_dir, 1)}
            for j in range(8) if dir_counts[j] > 0
        ]

        segment = {
            "start_frame": seg[0].index,
            "end_frame": seg[-1].index,
            "start_time": round(seg[0].timestamp, 2),
            "end_time": round(seg[-1].timestamp, 2),
            "avg_brightness": round(avg_brightness, 3),
            "avg_motion": round(avg_motion, 3),
            "avg_edge_density": round(avg_edge, 3),
            "face_count": faces,
            "has_significant_motion": avg_motion > 0.3,
            "is_dark": avg_brightness < 0.3,
            "is_cut": seg[0].index in scene_cuts or (len(seg) > 1 and seg[0].index in scene_cuts),
            "dominant_colors": dominant_colors,
            "motion_directions": motion_directions,
            "tags": [],
        }
        analysis.segments.append(segment)

    return analysis


# ── Build TELOS Pipeline for Video ──
def build_video_pipeline() -> TelosV14Pipeline:
    config = PipelineConfig(
        simulator=VideoDomainSimulator(),
        adapter=VideoAdapter(),
        compute_budget_ms=50.0,
        state_dim=5,
        n_worlds=8,
        horizon=4,
    )
    pipeline = TelosV14Pipeline(config)
    skill_lib = SkillLibrary()
    sim_engine = CounterfactualEngine(VideoDomainSimulator())

    pipeline.register_stream(ReflexStream(skill_lib))
    pipeline.register_stream(PerceptionStream(skill_lib))
    pipeline.register_stream(MemoryStream(skill_lib))
    pipeline.register_stream(PlanningStream(skill_lib, sim_engine=sim_engine))

    pipeline.register_validator(RealityValidator())
    pipeline.register_validator(ConstraintValidator())
    pipeline.register_validator(MemoryAdvisor(skill_lib))
    pipeline.register_validator(MissionDriftDetector(drift_threshold=5.0))

    return pipeline


# ── LLM-powered tagging ──
OLLAMA_URL = "http://localhost:11434/api/chat"

def _ask_ollama(messages: list) -> str:
    try:
        import urllib.request, urllib.error
        body = json.dumps({
            "model": "qwen2:0.5b",
            "messages": messages,
            "stream": False,
        }).encode()
        req = urllib.request.Request(OLLAMA_URL, data=body,
                                      headers={"Content-Type": "application/json"})
        with urllib.request.urlopen(req, timeout=15) as resp:
            data = json.loads(resp.read())
        return data.get("message", {}).get("content", "")
    except Exception as e:
        logger.warning(f"Ollama call failed: {e}")
        return ""


def llm_tag_video(analysis: VideoAnalysis) -> Dict:
    """Generate semantic tags, named entities, and predictions using the LLM."""
    motion_levels = []
    brightness_range = [1.0, 0.0]
    total_faces = 0
    for seg in analysis.segments:
        motion_levels.append(seg["avg_motion"])
        brightness_range[0] = min(brightness_range[0], seg["avg_brightness"])
        brightness_range[1] = max(brightness_range[1], seg["avg_brightness"])
        total_faces += seg["face_count"]

    avg_motion = np.mean(motion_levels) if motion_levels else 0
    motion_var = float(np.var(motion_levels)) if len(motion_levels) > 1 else 0
    peak_motion = max(motion_levels) if motion_levels else 0

    scene_profile = (
        f"motion={avg_motion:.2f}(var={motion_var:.2f},peak={peak_motion:.2f}), "
        f"brightness=[{brightness_range[0]:.2f}-{brightness_range[1]:.2f}], "
        f"faces_in_segments={total_faces}, "
        f"segments={len(analysis.segments)}, "
        f"duration={analysis.duration:.1f}s"
    )

    prompt = (
        f"You are analyzing a {analysis.duration:.0f}s video. "
        f"Features: {scene_profile}. "
        "Return a JSON object with these keys:\n"
        "  - tags: array of descriptive tags (e.g. outdoor, sports, fast-action, indoor, interview, crowd, nature, face-present, text-overlay)\n"
        "  - entities: array of possible named entities seen (e.g. person, player, object)\n"
        "  - predictions: array of predictions about what happens next or the video's purpose\n"
        "  - scene_type: brief scene classification (e.g. 'football highlight', 'classroom lecture', 'street view')\n"
        "Return ONLY valid JSON, no other text."
    )
    content = _ask_ollama([
        {"role": "system", "content": "You are a video analysis AI. Output only JSON."},
        {"role": "user", "content": prompt},
    ])
    try:
        parsed = json.loads(content)
        return {
            "tags": parsed.get("tags", []),
            "entities": parsed.get("entities", []),
            "predictions": parsed.get("predictions", []),
            "scene_type": parsed.get("scene_type", "unknown"),
        }
    except (json.JSONDecodeError, TypeError):
        return {"tags": [], "entities": [], "predictions": [], "scene_type": "unknown"}


def get_rich_tags(seg: Dict) -> list:
    """Generate descriptive tags from numerical features."""
    tags = []
    motion = seg["avg_motion"]
    brightness = seg["avg_brightness"]
    edges = seg["avg_edge_density"]
    faces = seg["face_count"]
    start = seg["start_time"]
    end = seg["end_time"]

    if motion > 0.7:
        tags.append("fast-motion")
    elif motion > 0.4:
        tags.append("moderate-motion")
    elif motion < 0.1:
        tags.append("static")

    if brightness > 0.7:
        tags.append("bright")
    elif brightness < 0.3:
        tags.append("dim")

    if edges > 0.15:
        tags.append("detail-rich")
    elif edges < 0.05:
        tags.append("smooth")

    if faces >= 3:
        tags.append("crowd")
    elif faces >= 1:
        tags.append("face-detected")

    if start < 1.0:
        tags.append("opening")
    if end > 8.0 and seg.get("telos_md", 0) > 1.0:
        tags.append("climax")

    return tags


# ── Analyze with TELOS ──
def analyze_segment(pipeline: TelosV14Pipeline,
                    segment: Dict,
                    user_name: str) -> Dict:
    """Run TELOS pipeline on a video segment's features."""
    state = np.array([
        segment["avg_brightness"],
        segment["avg_motion"],
        float(segment["start_frame"]),
        0.0, 0.0,
    ])

    result = pipeline.execute(state, user_name=user_name)
    trace = result.decision_trace

    if result.selected_trajectory and not (
        result.firewall_blocked or result.council_blocked
    ):
        if trace.selected_action is not None:
            action_idx = int(np.argmax(trace.selected_action))
        else:
            action_idx = 1  # default to log
    else:
        action_idx = 1

    actions = ["tag_event", "log_frame", "skip_segment",
               "flag_anomaly", "generate_highlight"]
    chosen_action = actions[min(action_idx, 4)]

    segment["telos_action"] = chosen_action
    segment["telos_di"] = round(trace.decision_integrity, 3) if trace else 1.0
    segment["telos_md"] = round(trace.mission_drift, 3) if trace else 0.0
    segment["council_validated"] = trace.council_validated if trace else True
    segment["tags"] = get_rich_tags(segment)

    return {
        "segment": segment,
        "pipeline": {
            "cycle": trace.cycle_id if trace else 0,
            "intent": trace.selected_intent.intent_type if trace and trace.selected_intent else None,
            "action": chosen_action,
            "di": segment["telos_di"],
            "md": segment["telos_md"],
            "council_validated": segment["council_validated"],
            "streams": [
                {
                    "name": s.stream_name,
                    "priority": s.priority,
                    "activated": s.activated,
                    "intent": s.intent.intent_type if s.intent else None,
                }
                for s in (trace.stream_activations if trace else [])
            ],
            "futures": [
                {"score": o.get("score", 0)}
                for o in (trace.strategic_options if trace else [])
            ][:5],
        },
    }


# ── Main ──
def main():
    import argparse
    parser = argparse.ArgumentParser(
        description="TELOS Video Analyzer — TELOS reasons about recorded video"
    )
    parser.add_argument("video_path", nargs="?", default=None,
                        help="Path to video file (optional when --serve is used)")
    parser.add_argument("--serve", action="store_true",
                        help="Start FastAPI server instead of CLI analysis")
    parser.add_argument("--max-frames", type=int, default=60,
                        help="Maximum frames to sample")
    parser.add_argument("--user", default="Analyst",
                        help="User name for identity memory")
    args = parser.parse_args()

    if args.serve:
        start_server(args.video_path)
        return

    if not args.video_path:
        print("Error: video_path is required (use --serve to launch the web UI)")
        sys.exit(1)
    if not os.path.exists(args.video_path):
        print(f"Error: Video not found: {args.video_path}")
        sys.exit(1)

    print(f"\n{'='*60}")
    print(f"TELOS Video Analysis")
    print(f"{'='*60}")
    print(f"File: {args.video_path}")
    print(f"User: {args.user}")
    print()

    # Extract features
    print("Extracting video features...")
    analysis = extract_features(args.video_path, max_frames=args.max_frames)
    print(f"  {analysis.frame_count} frames sampled across {len(analysis.segments)} segments")
    print(f"  Duration: {analysis.duration:.1f}s @ {analysis.fps:.1f}fps")
    print()

    # Build pipeline
    pipeline = build_video_pipeline()

    # Analyze each segment
    print("TELOS analyzing segments through Pipeline...")
    print()

    total_di = []
    total_md = []
    segment_results = []

    for i, seg in enumerate(analysis.segments):
        result = analyze_segment(pipeline, seg, args.user)
        segment_results.append(result)
        total_di.append(result["segment"]["telos_di"])
        total_md.append(result["segment"]["telos_md"])
        pipe = result["pipeline"]

        # Visual indicator for action
        icons = {"tag_event": "🏷️", "log_frame": "📝", "skip_segment": "⏭️",
                 "flag_anomaly": "⚠️", "generate_highlight": "✨"}
        icon = icons.get(pipe["action"], "➡️")

        motion_flag = "⚡" if seg["has_significant_motion"] else "  "
        face_flag = "👤" if seg["face_count"] > 0 else "   "
        tags = " ".join(f"[{t}]" for t in seg.get("tags", []))

        print(f"  {i+1:2d}. T{seg['start_time']:6.1f}s-{seg['end_time']:5.1f}s "
              f"{icon} {pipe['action']:20s} "
              f"DI={pipe['di']:.2f} MD={pipe['md']:.2f} "
              f"{motion_flag}{face_flag} {tags}")

        if pipe["streams"]:
            active = [s["name"] for s in pipe["streams"] if s["activated"]]
            print(f"      Streams: {', '.join(active)}")
        if pipe["intent"]:
            print(f"      Intent: {pipe['intent']}")

    print()
    print(f"{'='*60}")
    print(f"Summary")
    print(f"{'='*60}")
    avg_di = np.mean(total_di) if total_di else 0
    avg_md = np.mean(total_md) if total_md else 0
    event_count = sum(1 for r in segment_results
                      if r["pipeline"]["action"] == "tag_event")
    highlight_count = sum(1 for r in segment_results
                          if r["pipeline"]["action"] == "generate_highlight")
    anomaly_count = sum(1 for r in segment_results
                        if r["pipeline"]["action"] == "flag_anomaly")

    print(f"  Segments analyzed: {len(segment_results)}")
    print(f"  Average DI:        {avg_di:.3f}")
    print(f"  Average MD:        {avg_md:.3f}")
    print(f"  Events tagged:     {event_count}")
    print(f"  Highlights:        {highlight_count}")
    print(f"  Anomalies flagged: {anomaly_count}")
    print()
    print(f"  Identity memory: {pipeline.ledger.known_users} user(s)")
    for s in pipeline.ledger.get_known_user_summaries():
        print(f"    - {s['name']}: {s['relationship']} (trust={s['trust']:.2f})")
    print()

    # Save results
    output_path = f"telos_video_analysis_{os.path.splitext(os.path.basename(args.video_path))[0]}.json"
    with open(output_path, "w") as f:
        json.dump({
            "video": {
                "path": args.video_path,
                "duration": analysis.duration,
                "fps": analysis.fps,
                "resolution": f"{analysis.width}x{analysis.height}",
            },
            "summary": {
                "segments": len(segment_results),
                "avg_di": round(float(avg_di), 3),
                "avg_md": round(float(avg_md), 3),
                "events": event_count,
                "highlights": highlight_count,
                "anomalies": anomaly_count,
            },
            "pipeline_results": segment_results,
        }, f, indent=2, default=str)
    print(f"Full analysis saved to: {output_path}")


# ── FastAPI Server (optional) ──
def start_server(video_path: str = None):
    from fastapi import FastAPI, Query
    from fastapi.responses import HTMLResponse, FileResponse
    import uvicorn

    app = FastAPI(title="TELOS Video Analyzer")
    pipeline = build_video_pipeline()
    current_video = {"path": video_path, "downloading": False}
    ball_data_cache: Dict[str, Dict] = {}
    if video_path and not os.path.exists(video_path):
        print(f"Warning: video not found: {video_path}")
        current_video["path"] = None

    def _process_ball_positions(video_path_c: str) -> Dict:
        import cv2
        cap = cv2.VideoCapture(video_path_c)
        positions = []
        players_cache = []
        frame_idx = 0
        while True:
            ret, frame = cap.read()
            if not ret: break
            hsv = cv2.cvtColor(frame, cv2.COLOR_BGR2HSV)
            mask = cv2.inRange(hsv, (0, 0, 180), (180, 50, 255))
            cnts, _ = cv2.findContours(mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
            largest_cnt = None
            max_area = 0
            for cnt in cnts:
                area = cv2.contourArea(cnt)
                if area > max_area and area < 500:
                    max_area = area
                    largest_cnt = cnt
            if largest_cnt is not None:
                (x,y), r = cv2.minEnclosingCircle(largest_cnt)
                positions.append({'frame': frame_idx, 'x': int(x), 'y': int(y), 'radius': int(r), 'detected': True})
            else:
                positions.append({'frame': frame_idx, 'x': None, 'y': None, 'radius': None, 'detected': False})
            players = []
            for cnt in cnts:
                if cv2.contourArea(cnt) > 500:
                    x,y,w,h = cv2.boundingRect(cnt)
                    players.append({'x': int(x+w/2), 'y': int(y+h/2), 'w': w, 'h': h})
            players_cache.append({'frame': frame_idx, 'players': players})
            frame_idx += 1
        cap.release()
        return {'positions': positions, 'players': players_cache, 'fps': 30, 'width': 640, 'height': 360}

    HTML_PAGE = """
    <!DOCTYPE html>
    <html>
    <head>
      <title>TELOS Video Analyzer</title>
      <meta name="viewport" content="width=device-width, initial-scale=1">
      <style>
        * { box-sizing: border-box; margin: 0; padding: 0; }
        body { font-family: -apple-system, 'SF Mono', monospace; background: #0d1117; color: #c9d1d9; padding: 20px; }
        .container { max-width: 800px; margin: 0 auto; }
        h1 { color: #58a6ff; border-bottom: 1px solid #30363d; padding-bottom: 12px; margin: 20px 0; }
        .card { background: #161b22; border: 1px solid #30363d; border-radius: 8px; padding: 16px; margin: 12px 0; }
        .card h3 { color: #58a6ff; font-size: 0.9rem; margin-bottom: 8px; }
        .tag { display: inline-block; padding: 2px 8px; border-radius: 4px; font-size: 0.75rem; margin: 2px; }
        .tag-event { background: #0b2d16; color: #3fb950; border: 1px solid #3fb950; }
        .tag-highlight { background: #2d220b; color: #d29922; border: 1px solid #d29922; }
        .tag-anomaly { background: #2d0b0b; color: #f85149; border: 1px solid #f85149; }
        .tag-log { background: #1c2333; color: #58a6ff; border: 1px solid #58a6ff; }
        .stat { display: flex; gap: 20px; margin: 12px 0; }
        .stat-item { flex: 1; text-align: center; padding: 12px; background: #0d1117; border-radius: 8px; }
        .stat-item .num { font-size: 1.5rem; font-weight: bold; }
        .stat-item .lbl { font-size: 0.7rem; color: #8b949e; text-transform: uppercase; }
        .trace { font-size: 0.75rem; color: #8b949e; white-space: pre-wrap; margin-top: 8px; }
        button { padding: 10px 24px; background: #21262d; border: 1px solid #30363d; border-radius: 6px; color: #c9d1d9; cursor: pointer; font-size: 0.9rem; margin: 12px 0; }
        button:hover { background: #30363d; }
        button:disabled { opacity: 0.4; cursor: not-allowed; }
        button.active { border-color: #d29922; color: #d29922; background: #2d220b; }
        input[type=url] { width:100%; padding:10px; background:#0d1117; border:1px solid #30363d; border-radius:6px; color:#c9d1d9; font-size:0.9rem; }
        input[type=url]:focus { border-color:#58a6ff; outline:none; }
        .status { color: #8b949e; font-size: 0.85rem; margin: 12px 0; }
        .url-bar { display:flex; gap:8px; margin:12px 0; }
        .url-bar input { flex:1; }
        .url-bar button { margin:0; white-space:nowrap; }
        .msg { margin:8px 0; padding:8px 12px; border-radius:6px; font-size:0.85rem; }
        .msg-ok { background:#0b2d16; color:#3fb950; border:1px solid #3fb950; }
        .msg-err { background:#2d0b0b; color:#f85149; border:1px solid #f85149; }
            .msg-info { background:#1c2333; color:#58a6ff; border:1px solid #58a6ff; }
            .video-wrap { position: relative; display: inline-block; width: 100%; }
            .video-wrap video { width: 100%; max-height: 480px; border-radius: 8px; display: block; background: #000; object-fit: contain; }
            .video-wrap canvas { position: absolute; top: 0; left: 0; width: 100%; height: 100%; border-radius: 8px; pointer-events: none; }
            .ball-stats { display: flex; gap: 12px; margin: 8px 0; padding: 8px 12px; background: #0d1117; border-radius: 6px; font-size: 0.8rem; }
            .ball-stats span { color: #8b949e; }
            .ball-stats .val { color: #c9d1d9; font-weight: bold; }
      </style>
    </head>
    <body>
      <div class="container">
        <h1>TELOS Video Analyzer</h1>
        <p style="color:#8b949e;margin-bottom:16px;">TELOS reasons about recorded video through its 7-phase Pipeline.</p>
        <div class="url-bar">
          <input type="url" id="url-input" placeholder="Paste YouTube URL (e.g. https://www.youtube.com/watch?v=...)" value="https://www.youtube.com/watch?v=WyN5h9ZtFOQ">
          <button id="load-btn" onclick="loadVideo()">⬇ Load</button>
        </div>
        <div id="msg"></div>
        <p class="status">Video: <span id="video-name">waiting...</span> &nbsp;|&nbsp; <span id="frame-count">-</span> frames &nbsp;|&nbsp; <span id="duration">-</span>s</p>
        <div class="video-wrap">
          <video id="player" controls style="width:100%;max-height:480px;border-radius:8px;background:#000;"></video>
          <canvas id="ball-canvas"></canvas>
        </div>
        <div id="ball-stats" class="ball-stats" style="display:none;">
          <span>Ball: <span class="val" id="ball-pos">—</span></span>
          <span>Detected: <span class="val" id="ball-detected">—</span></span>
          <span>Trail: <span class="val" id="ball-trail-count">—</span></span>
        </div>
        <div style="margin:8px 0;">
          <button id="analyze-btn" onclick="analyze()" disabled>▶ Analyze with TELOS</button>
          <button id="annotate-btn" onclick="annotate()" disabled style="margin-left:8px;background:#2d0b0b;border-color:#f85149;">⚽ Track Ball</button>
          <button id="trail-btn" onclick="toggleTrail()" disabled style="margin-left:8px;">🔮 Trajectory</button>
        </div>
        <div id="loading" style="display:none;color:#8b949e;margin:12px 0;">Processing...</div>
        <div id="summary"></div>
        <div id="segments"></div>
        <div id="trace"></div>
      </div>
      <script>
        async function refreshInfo() {
          try {
            const r = await fetch('/info');
            const d = await r.json();
            document.getElementById('video-name').textContent = d.name;
            document.getElementById('frame-count').textContent = d.frames;
            document.getElementById('duration').textContent = d.duration + 's';
            document.getElementById('player').src = '/video?' + Date.now();
            document.getElementById('analyze-btn').disabled = false;
            document.getElementById('annotate-btn').disabled = false;
          } catch(e) {}
        }

        window.addEventListener('DOMContentLoaded', refreshInfo);

        async function loadVideo() {
          const url = document.getElementById('url-input').value.trim();
          if (!url) { showMsg('Enter a YouTube URL', 'err'); return; }

          const btn = document.getElementById('load-btn');
          btn.disabled = true; btn.textContent = '⏳ Downloading...';
          showMsg('Downloading video from YouTube...', 'info');

          try {
            const r = await fetch('/load?url=' + encodeURIComponent(url));
            const d = await r.json();
            if (d.error) { showMsg(d.error, 'err'); return; }
            showMsg('Video loaded: ' + d.name, 'ok');
            await refreshInfo();
          } catch(e) {
            showMsg('Failed to load video: ' + e.message, 'err');
          } finally {
            btn.disabled = false; btn.textContent = '⬇ Load';
          }
        }

        function showMsg(text, type) {
          document.getElementById('msg').innerHTML =
            '<div class="msg msg-' + type + '">' + text + '</div>';
        }

        async function analyze() {
          document.getElementById('loading').style.display = 'block';
          document.getElementById('summary').innerHTML = '';
          document.getElementById('segments').innerHTML = '';
          document.getElementById('trace').innerHTML = '';
          document.getElementById('msg').innerHTML = '';

          const resp = await fetch('/analyze');
          const data = await resp.json();

          document.getElementById('loading').style.display = 'none';

          if (data.error) { showMsg(data.error, 'err'); return; }

          // Scene intelligence from LLM
          let llmHtml = '';
          if (data.llm) {
            const tags = (data.llm.tags||[]).map(t => `<span class="tag tag-event">${t}</span>`).join(' ');
            const entities = (data.llm.entities||[]).map(e => `<span class="tag tag-log">${e}</span>`).join(' ');
            const preds = (data.llm.predictions||[]).map(p => `<div style="color:#d29922;font-size:0.85rem;margin:2px 0;">🔮 ${p}</div>`).join('');
            llmHtml = `
              <div class="card">
                <h3>🧠 TELOS Intelligence</h3>
                <div style="margin:6px 0;"><strong>Scene:</strong> ${data.llm.scene_type}</div>
                <div style="margin:4px 0;"><strong>Tags:</strong> ${tags}</div>
                <div style="margin:4px 0;"><strong>Entities:</strong> ${entities}</div>
                ${preds ? `<div style="margin:4px 0;"><strong>Predictions:</strong><br>${preds}</div>` : ''}
              </div>
            `;
          }

          document.getElementById('summary').innerHTML = `
            <div class="stat">
              <div class="stat-item"><div class="num" style="color:#58a6ff">${data.summary.segments}</div><div class="lbl">Segments</div></div>
              <div class="stat-item"><div class="num" style="color:#3fb950">${data.summary.avg_di}</div><div class="lbl">Avg DI</div></div>
              <div class="stat-item"><div class="num" style="color:#d29922">${data.summary.events}</div><div class="lbl">Events</div></div>
              <div class="stat-item"><div class="num" style="color:#d29922">${data.summary.highlights}</div><div class="lbl">Highlights</div></div>
              <div class="stat-item"><div class="num" style="color:#f85149">${data.summary.anomalies}</div><div class="lbl">Anomalies</div></div>
            </div>
            ${llmHtml}
          `;

          let segHtml = '';
          for (const r of data.pipeline_results) {
            const s = r.segment;
            const p = r.pipeline;
            const tags = s.tags.map(t => `<span class="tag tag-${['fast-motion','moderate-motion','static','bright','dim','crowd','face-detected','climax'].includes(t)?'event':'log'}">${t}</span>`).join(' ');
            const diColor = p.di > 0.95 ? '#3fb950' : p.di > 0.7 ? '#d29922' : '#f85149';
            segHtml += `
              <div class="card">
                <h3>T${s.start_time}s - T${s.end_time}s  →  ${p.action.toUpperCase()}</h3>
                <div>${tags}</div>
                <div style="font-size:0.8rem;color:#8b949e;margin-top:6px;">
                  DI=<span style="color:${diColor}">${p.di}</span> | MD=${p.md} | Council: ${p.council_validated ? '✅' : '❌'}
                </div>
                <div class="trace">Intent: ${p.intent} | ${(p.streams||[]).filter(x=>x.activated).map(x=>x.name).join(', ')}</div>
              </div>
            `;
          }
          document.getElementById('segments').innerHTML = segHtml;
        }

        let ballData = null;
        let showTrail = true;
        let animFrame = null;

        let overlayActive = false;

        function sizeCanvas() {
          const v = document.getElementById('player');
          const c = document.getElementById('ball-canvas');
          const rect = v.getBoundingClientRect();
          if (rect.width > 0 && rect.height > 0) {
            // TELOS FIX B: round to integer, respect devicePixelRatio
            c.width = Math.round(rect.width);
            c.height = Math.round(rect.height);
          } else {
            c.width = v.videoWidth || 640;
            c.height = v.videoHeight || 480;
          }
        }

        // Account for video letterboxing (object-fit:contain default)
        function getVideoRenderRect(video, canvas) {
          var vw = video.videoWidth || ballData.width;
          var vh = video.videoHeight || ballData.height;
          var vr = vw / vh;
          var cw = canvas.width;
          var ch = canvas.height;
          var cr = cw / ch;
          var renderW, renderH, offsetX, offsetY;
          if (vr > cr) {
            renderW = cw;
            renderH = cw / vr;
            offsetX = 0;
            offsetY = (ch - renderH) / 2;
          } else {
            renderH = ch;
            renderW = ch * vr;
            offsetX = (cw - renderW) / 2;
            offsetY = 0;
          }
          return { renderW: renderW, renderH: renderH,
                   offsetX: offsetX, offsetY: offsetY };
        }

        function renderBallOverlay() {
          const v = document.getElementById('player');
          const c = document.getElementById('ball-canvas');
          if (!ballData || !v.videoWidth) {
            animFrame = requestAnimationFrame(renderBallOverlay);
            return;
          }
          const ctx = c.getContext('2d');
          ctx.clearRect(0, 0, c.width, c.height);
          var vr = getVideoRenderRect(v, c);
          var sx = vr.renderW / ballData.width;
          var sy = vr.renderH / ballData.height;
          var ox = vr.offsetX;
          var oy = vr.offsetY;
          function tx(x) { return x * sx + ox; }
          function ty(y) { return y * sy + oy; }
          const currentFrame = Math.round(v.currentTime * ballData.fps);
          const maxFrame = ballData.positions.length - 1;
          if (currentFrame < 0 || currentFrame > maxFrame) {
            animFrame = requestAnimationFrame(renderBallOverlay);
            return;
          }
          const windowStart = Math.max(0, currentFrame - 30);
          const windowEnd = Math.min(maxFrame, currentFrame + 5);

          // Collect visible trail points
          const trailPoints = [];
          for (let f = windowStart; f <= currentFrame; f++) {
            const p = ballData.positions[f];
            if (p && p.detected) trailPoints.push(p);
          }

          // Trajectory trail — dashed red line through last 30 detected positions
          if (showTrail && trailPoints.length > 1) {
            ctx.beginPath();
            ctx.strokeStyle = 'rgba(255, 100, 100, 0.6)';
            ctx.lineWidth = 3;
            ctx.setLineDash([6, 4]);
            trailPoints.forEach((pt, i) => {
              const x = tx(pt.x), y = ty(pt.y);
              if (i === 0) ctx.moveTo(x, y);
              else ctx.lineTo(x, y);
            });
            ctx.stroke();
            ctx.setLineDash([]);
            // Dots for each trail position
            trailPoints.forEach(pt => {
              const x = tx(pt.x), y = ty(pt.y);
              ctx.beginPath();
              ctx.arc(x, y, 3, 0, Math.PI * 2);
              ctx.fillStyle = 'rgba(255, 80, 80, 0.5)';
              ctx.fill();
            });
            // Multi-frame linear regression prediction
            if (trailPoints.length >= 2) {
              var n = Math.min(trailPoints.length, 5);
              var recentPoints = trailPoints.slice(-n);
              var sumT = 0, sumX = 0, sumY = 0, sumT2 = 0, sumTX = 0, sumTY = 0;
              for (var i = 0; i < n; i++) {
                var t = i - (n - 1);
                sumT += t; sumX += recentPoints[i].x; sumY += recentPoints[i].y;
                sumT2 += t * t; sumTX += t * recentPoints[i].x; sumTY += t * recentPoints[i].y;
              }
              var denom = n * sumT2 - sumT * sumT;
              var vx = 0, vy = 0;
              if (denom !== 0) {
                vx = (n * sumTX - sumT * sumX) / denom;
                vy = (n * sumTY - sumT * sumY) / denom;
              }
              var maxVel = 50;
              vx = Math.max(-maxVel, Math.min(maxVel, vx));
              vy = Math.max(-maxVel, Math.min(maxVel, vy));
              var lastPt = recentPoints[recentPoints.length - 1];
              var px = tx(lastPt.x + vx);
              var py = ty(lastPt.y + vy);
              // Prediction direction line
              ctx.beginPath();
              ctx.strokeStyle = 'rgba(255, 200, 50, 0.5)';
              ctx.lineWidth = 2;
              ctx.setLineDash([4, 6]);
              ctx.moveTo(tx(lastPt.x), ty(lastPt.y));
              ctx.lineTo(px, py);
              ctx.stroke();
              ctx.setLineDash([]);
              // Prediction dot
              ctx.beginPath();
              ctx.arc(px, py, 6, 0, Math.PI * 2);
              ctx.fillStyle = 'rgba(255, 200, 50, 0.4)';
              ctx.fill();
              ctx.strokeStyle = 'rgba(255, 200, 50, 0.7)';
              ctx.lineWidth = 2;
              ctx.stroke();
            }
          }

          // Render nearby players as blue boxes
          const playersData = ballData.players || [];
          const playerFrame = playersData.find(function(pf) { return pf.frame === currentFrame; });
          if (playerFrame && playerFrame.players) {
            playerFrame.players.forEach(function(pl) {
              var px = tx(pl.x), py = ty(pl.y);
              var pw = pl.w * sx, ph = pl.h * sy;
              ctx.strokeStyle = 'rgba(50, 150, 255, 0.7)';
              ctx.lineWidth = 2;
              ctx.strokeRect(px - pw/2, py - ph/2, pw, ph);
              ctx.fillStyle = 'rgba(50, 150, 255, 0.2)';
              ctx.fillRect(px - pw/2, py - ph/2, pw, ph);
              ctx.fillStyle = '#3399ff';
              ctx.font = '10px monospace';
              ctx.fillText('PLAYER', px - pw/2 + 2, py - ph/2 - 2);
            });
          }

          // Unified rendering loop
          function renderBallOverlay() {
            const v = document.getElementById('player');
            const c = document.getElementById('ball-canvas');
            if (!ballData || !v || !c) return;
            
            const ctx = c.getContext('2d');
            ctx.clearRect(0, 0, c.width, c.height);
            
            const currentFrame = Math.round(v.currentTime * (ballData.fps || 30));
            if (currentFrame < 0 || currentFrame >= ballData.positions.length) {
              requestAnimationFrame(renderBallOverlay);
              return;
            }

            // Draw Ball
            const cur = ballData.positions[currentFrame];
            if (cur && cur.detected) {
                ctx.beginPath();
                ctx.arc(cur.x, cur.y, 10, 0, 2 * Math.PI);
                ctx.fillStyle = 'red';
                ctx.fill();
            }

            // Draw Players
            const framePlayers = ballData.players.find(p => p.frame === currentFrame);
            if (framePlayers && framePlayers.players) {
                framePlayers.players.forEach(p => {
                    ctx.strokeStyle = 'blue';
                    ctx.lineWidth = 2;
                    ctx.strokeRect(p.x - p.w/2, p.y - p.h/2, p.w, p.h);
                });
            }

            animFrame = requestAnimationFrame(renderBallOverlay);
          }
          
          function startOverlay() {
            if (overlayActive) return;
            overlayActive = true;
            sizeCanvas();
            renderBallOverlay();
          }


        var _overlayListenersAttached = false;

        function detachOverlayListeners() {
          if (!_overlayListenersAttached) return;
          const v = document.getElementById('player');
          v.removeEventListener('loadedmetadata', startOverlay);
          v.removeEventListener('play', startOverlay);
          v.removeEventListener('timeupdate', sizeCanvas);
          v.removeEventListener('seeked', sizeCanvas);
          _overlayListenersAttached = false;
        }

        function startOverlay() {
          if (overlayActive) return;
          overlayActive = true;
          sizeCanvas();
          if (animFrame) cancelAnimationFrame(animFrame);
          renderBallOverlay();
        }

        async function annotate() {
          document.getElementById('loading').style.display = 'block';
          document.getElementById('loading').textContent = 'Processing...';
          
          // Trigger processing in background
          await fetch('/annotate');

          // Poll for ball data until it's ready
          const poll = async () => {
            const resp = await fetch('/ball-data');
            const data = await resp.json();
            
            if (data.positions && data.positions.length > 0) {
              ballData = data;
              // Setup UI
              document.getElementById('ball-stats').style.display = 'flex';
              // ... [rest of UI setup]
              document.getElementById('loading').style.display = 'none';
              if (document.getElementById('player').videoWidth) startOverlay();
              showMsg('Tracking Active', 'ok');
            } else {
              document.getElementById('loading').textContent = 'Processing frame ' + (data.positions ? data.positions.length : 0);
              setTimeout(poll, 1000);
            }
          };
          poll();
        }

        function toggleTrail() {
          showTrail = !showTrail;
          const btn = document.getElementById('trail-btn');
          btn.textContent = showTrail ? '🔮 Trajectory' : '🔮 Hidden';
          btn.className = showTrail ? 'active' : '';
        }

        // Re-size canvas when window resizes
        window.addEventListener('resize', sizeCanvas);
      </script>
    </body>
    </html>
    """

    @app.get("/", response_class=HTMLResponse)
    async def root():
        return HTML_PAGE

    @app.get("/load")
    async def load_video(url: str = Query(...)):
        if current_video["downloading"]:
            return {"error": "Already downloading a video"}
        current_video["downloading"] = True
        try:
            import yt_dlp
            out_dir = "/tmp/telos_video"
            os.makedirs(out_dir, exist_ok=True)
            ydl_opts = {
                "outtmpl": os.path.join(out_dir, "%(id)s.%(ext)s"),
                "format": "mp4",
                "quiet": True,
                "no_warnings": True,
                "extractor_args": {"youtube": {"player_client": ["android"]}},
            }
            with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                info = ydl.extract_info(url, download=True)
                video_path_dl = ydl.prepare_filename(info)
                ext = info.get("ext", "mp4")
                if not os.path.exists(video_path_dl):
                    video_path_dl = os.path.join(out_dir, f"{info['id']}.{ext}")
                # yt-dlp may produce .webm or .mkv — find the actual file
                if not os.path.exists(video_path_dl):
                    for f in os.listdir(out_dir):
                        if f.startswith(info["id"]):
                            video_path_dl = os.path.join(out_dir, f)
                            break
                current_video["path"] = video_path_dl
                return {
                    "name": f"{info['title']} ({info['id']})",
                    "id": info["id"],
                    "duration": info.get("duration", 0),
                }
        except Exception as e:
            return {"error": str(e)}
        finally:
            current_video["downloading"] = False

    @app.get("/video")
    async def stream_video():
        p = current_video.get("path")
        if not p or not os.path.exists(p):
            from fastapi.responses import Response
            return Response(status_code=404)
        return FileResponse(p)

    @app.get("/info")
    async def video_info():
        p = current_video.get("path")
        if not p or not os.path.exists(p):
            return {"name": "no video", "frames": 0, "duration": 0}
        import cv2
        cap = cv2.VideoCapture(p)
        if not cap.isOpened():
            return {"name": os.path.basename(p), "frames": 0, "duration": 0}
        fps = cap.get(cv2.CAP_PROP_FPS)
        total_frames = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
        duration = round(total_frames / fps, 1) if fps > 0 else 0
        cap.release()
        return {"name": os.path.basename(p), "frames": total_frames, "duration": duration}

    def _convert(obj):
        """Recursively convert numpy types to native Python."""
        if isinstance(obj, dict):
            return {k: _convert(v) for k, v in obj.items()}
        if isinstance(obj, list):
            return [_convert(v) for v in obj]
        if isinstance(obj, (np.bool_,)):
            return bool(obj)
        if isinstance(obj, (np.floating,)):
            return float(obj)
        if isinstance(obj, (np.integer,)):
            return int(obj)
        return obj

    @app.get("/analyze")
    async def analyze_video():
        p = current_video.get("path")
        if not p or not os.path.exists(p):
            return {"error": "No video loaded"}
        try:
            analysis = extract_features(p)
        except Exception as e:
            return {"error": f"Feature extraction failed: {e}"}
        segment_results = []
        for seg in analysis.segments:
            result = analyze_segment(pipeline, seg, "Analyst")
            segment_results.append(_convert(result))

        total_di = [r["segment"]["telos_di"] for r in segment_results]
        avg_di = float(np.mean(total_di)) if total_di else 0
        event_count = sum(1 for r in segment_results
                          if r["pipeline"]["action"] == "tag_event")
        highlight_count = sum(1 for r in segment_results
                              if r["pipeline"]["action"] == "generate_highlight")
        anomaly_count = sum(1 for r in segment_results
                            if r["pipeline"]["action"] == "flag_anomaly")

        # Return clean data
        return {
            "video": {
                "path": p,
                "duration": analysis.duration,
                "fps": analysis.fps,
                "resolution": f"{analysis.width}x{analysis.height}",
            },
            "summary": {
                "segments": len(segment_results),
            },
            "pipeline_results": segment_results,
        }

    def _render_annotated_video(p: str) -> str:
        """Process all frames, write annotated video, cache ball data. Returns output path."""
        import cv2
        cap = cv2.VideoCapture(p)
        fps = cap.get(cv2.CAP_PROP_FPS) or 30
        w = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
        h = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
        out_path = p.replace(".mp4", "_annotated.mp4").replace(".mov", "_annotated.mp4")
        fourcc = cv2.VideoWriter_fourcc(*"mp4v")
        out = cv2.VideoWriter(out_path, fourcc, fps, (w, h))
        prev_center = None
        ball_detected_total = 0
        frames_processed = 0
        ball_positions_cached = []
        prev_gray = None

        def detect_ball(bgr, prev_c, p_mask):
            nonlocal prev_gray
            gray = cv2.cvtColor(bgr, cv2.COLOR_BGR2GRAY)
            gray = cv2.GaussianBlur(gray, (7, 7), 0)
            motion = None
            if prev_gray is not None:
                diff = cv2.absdiff(prev_gray, gray)
                diff = cv2.GaussianBlur(diff, (5, 5), 0)
                _, motion = cv2.threshold(diff, 15, 255, cv2.THRESH_BINARY)
                motion = cv2.dilate(motion, None, iterations=2)
            circles = cv2.HoughCircles(gray, cv2.HOUGH_GRADIENT, dp=1.3,
                                       minDist=30, param1=40, param2=15,
                                       minRadius=3, maxRadius=20)
            candidates = []
            if circles is not None:
                for circ in np.round(circles[0]).astype(int):
                    cx, cy, r = int(circ[0]), int(circ[1]), int(circ[2])
                    if cy < h * 0.15 or cy > h * 0.85: continue
                    if cx < r or cx >= w - r or cy < r or cy >= h - r: continue
                    on_motion = bool(motion[cy, cx] > 0) if motion is not None else True
                    brightness = int(gray[cy, cx])
                    if brightness < 80 and not on_motion: continue
                    candidates.append((cx, cy, r, on_motion, brightness))
            prev_gray = gray
            if not candidates:
                return None
            def score(c):
                s = (1.0 if c[3] else 0) + c[4] / 255.0
                if prev_c is not None:
                    d = np.hypot(c[0] - prev_c[0], c[1] - prev_c[1])
                    s -= d * 0.005
                return s
            best = max(candidates, key=score)
            if prev_c is not None:
                d = np.hypot(best[0] - prev_c[0], best[1] - prev_c[1])
                if d > 120: return None
            return (best[0], best[1], best[2])

        while True:
            ret, frame = cap.read()
            if not ret:
                break
            frames_processed += 1
            annotated = frame.copy()
            # Pass empty mask for annotate-only path for simplicity
            ball = detect_ball(frame, prev_center, [])
            if ball is not None:
                cx, cy, r = ball
                prev_center = (cx, cy)
                ball_detected_total += 1
                ball_positions_cached.append({"frame": frames_processed - 1, "x": cx, "y": cy, "radius": r, "detected": True})
                cv2.circle(annotated, (cx, cy), r + 5, (0, 0, 200), -1)
                cv2.circle(annotated, (cx, cy), r, (0, 0, 255), 3)
                cv2.circle(annotated, (cx, cy), r - 2, (100, 100, 255), 1)
                cv2.line(annotated, (cx - r - 8, cy), (cx + r + 8, cy), (0, 0, 255), 1)
                cv2.line(annotated, (cx, cy - r - 8), (cx, cy + r + 8), (0, 0, 255), 1)
                cv2.rectangle(annotated, (cx - 45, cy - r - 30),
                              (cx + 45, cy - r - 8), (0, 0, 200), -1)
                cv2.putText(annotated, "FOOTBALL", (cx - 40, cy - r - 12),
                            cv2.FONT_HERSHEY_SIMPLEX, 0.45, (255, 255, 255), 1)
            else:
                ball_positions_cached.append({"frame": frames_processed - 1, "x": None, "y": None, "radius": None, "detected": False})
            cv2.rectangle(annotated, (0, 0), (240, 50), (0, 0, 0), -1)
            cv2.putText(annotated, "TELOS Ball Tracker", (10, 18),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.45, (100, 150, 255), 1)
            status = f"Frame {frames_processed} | Ball: {'YES' if ball is not None else 'NO'}"
            cv2.putText(annotated, status, (10, 38),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.4,
                        (0, 255, 0) if ball is not None else (0, 0, 255), 1)
            out.write(annotated)

        cap.release()
        out.release()
        trajectory = [{"x": p["x"], "y": p["y"]} for p in ball_positions_cached if p["detected"]]
        ball_data_cache[p] = {
            "fps": fps, "width": w, "height": h, "total_frames": frames_processed,
            "detected_frames": ball_detected_total,
            "detection_rate": round(ball_detected_total / max(frames_processed, 1), 3),
            "positions": ball_positions_cached, "trajectory": trajectory,
            "players": [],
        }
        print(f"ANNOTATION: {frames_processed} frames, ball detected in {ball_detected_total} ({100*ball_detected_total//max(frames_processed,1)}%)")
        return out_path

    @app.get("/annotate")
    async def annotate_video():
        """Returns minimal ball data immediately and processes video in background."""
        p = current_video.get("path")
        if not p or not os.path.exists(p):
            return {"error": "No video loaded"}
        
        # Start background processing if not already done
        if p not in ball_data_cache:
            import threading
            threading.Thread(target=_process_ball_positions, args=(p,), daemon=True).start()
            
        return {"status": "Processing in background"}


    @app.get("/ball-data")
    async def get_ball_data():
        p = current_video.get("path")
        if not p or not os.path.exists(p):
            return {"error": "No video loaded"}
        
        # Ensure it's processed
        if p not in ball_data_cache:
            # Run in thread so it doesn't block
            import threading
            threading.Thread(target=_process_ball_positions, args=(p,), daemon=True).start()
            return {"error": "Processing... please wait"}
            
        return ball_data_cache.get(p, {"error": "No data"})

    print(f"\nTELOS Video Analyzer server running at http://localhost:8001")
    if video_path and os.path.exists(video_path):
        print(f"Initial video: {video_path}")
    else:
        print("No initial video. Load one via the web UI.")
    uvicorn.run(app, host="0.0.0.0", port=8001, log_level="warning")


if __name__ == "__main__":
    main()
