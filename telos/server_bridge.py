"""
TELOS AI Bridge — serves AI feature integrations for MD-App React frontend.
Runs on port 5002, proxies /api/v1/ai/* endpoints for the React frontend.
"""
import sys
import os
from flask import Flask, request, jsonify
from flask_cors import CORS

app = Flask(__name__)
CORS(app)

# ─── /api/v1/ai/suggestions ────────────────────────────────────
@app.route("/api/v1/ai/suggestions", methods=["POST"])
def suggestions():
    data = request.get_json()
    return jsonify({"suggestions": {}})

# ─── /api/v1/ai/score ────────────────────────────────────────
@app.route("/api/v1/ai/score", methods=["POST"])
def score():
    data = request.get_json()
    return jsonify({
        "metrics": [], "issues": ["AI bridge in demo mode"],
        "dietCompatibility": 0.5, "searchQuality": 0.5, "regionDiversity": 0.5
    })

# ─── /api/v1/ai/recommendations ──────────────────────────────
@app.route("/api/v1/ai/recommendations", methods=["POST"])
def recommendations():
    data = request.get_json()
    return jsonify({"recommendations": []})

# ─── /api/v1/ai/translate ────────────────────────────────────
@app.route("/api/v1/ai/translate", methods=["POST"])
def translate():
    data = request.get_json()
    return jsonify({"translated": ""})

# ─── /api/v1/ai/voice ────────────────────────────────────────
@app.route("/api/v1/ai/voice", methods=["POST"])
def voice():
    data = request.get_json()
    return jsonify({
        "voiceMessage": {"textHindi": "", "textRegional": "", "textEnglish": "", "durationSec": 0},
        "recipeDescription": ""
    })

# ─── /api/v1/ai/chat ──────────────────────────────────────────
@app.route("/api/v1/ai/chat", methods=["POST"])
def chat():
    data = request.get_json()
    return jsonify({"message": "AI bridge in demo mode"})

# ─── /api/v1/ai/health ───────────────────────────────────────
@app.route("/api/v1/ai/health", methods=["GET"])
def health():
    return jsonify({"status": "ok", "service": "telos-ai-bridge"})

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5002)
