#!/usr/bin/env python3
"""
MealDrama AI Bridge — serves Python adapter functions as API endpoints
for the MD-App React frontend. Runs on port 5002.

Express proxies /api/v1/ai/* -> http://localhost:5002
"""

import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from flask import Flask, request, jsonify
from flask_cors import CORS

from telos.adapters.meal_library import (
    get_dishes, compute_diet_compatibility,
    compute_search_quality, compute_region_diversity, DIET_TYPES, REGIONS,
)
from telos.adapters.mealdrama_adapter import (
    suggest_next_dishes, _extract_features, GOAL_STATE,
)
from telos.adapters.meal_messaging import (
    MealDramaMessenger, VoiceMessage, MessageType, TRANSLATIONS,
    SLOT_TRANSLATIONS, DISHRECIPE_TRANSLATIONS,
)

app = Flask(__name__)
CORS(app)


@app.route("/health")
def health():
    return jsonify({"status": "ok", "service": "mealdrama-ai"})


@app.route("/api/v1/ai/suggestions", methods=["POST"])
def suggestions():
    data = request.get_json()
    tray = data.get("trayLibrary", {})
    diet = data.get("diet", "vegetarian")
    regions = data.get("preferredRegions", [])
    count = data.get("count", 10)

    all_sugs = suggest_next_dishes(tray, diet, regions, count=count)
    result = {}
    for slot in ["breakfast", "lunch", "dinner", "snacks"]:
        result[slot] = [
            {
                "id": d["id"],
                "name": d["name"],
                "region": d["region"],
                "calories": d.get("calories", 0),
                "protein": d.get("protein", 0),
                "slots": d["slots"],
            }
            for d in all_sugs if slot in d["slots"]
        ][:3]

    return jsonify({"suggestions": result})


@app.route("/api/v1/ai/score", methods=["POST"])
def score():
    data = request.get_json()
    tray = data.get("trayLibrary", {})
    plan = data.get("planDays", {})
    pantry = data.get("pantryStaples", [])
    diet = data.get("diet", "vegetarian")
    regions = data.get("preferredRegions", [])
    health = data.get("healthGoal")

    state = _extract_features(tray, plan, pantry, health, diet_profile=diet, preferred_regions=regions)

    diet_match = compute_diet_compatibility(tray, diet)
    search = compute_search_quality(tray, diet)
    region_div = compute_region_diversity(tray)

    labels = [
        ("meal_count", "Meal Count", float(state[0])),
        ("tray_size", "Tray Size", float(state[1])),
        ("pantry", "Pantry", float(state[3])),
        ("plan_completion", "Plan", float(state[8])),
        ("diet_match", "Diet Match", float(state[10])),
        ("discoverability", "Discoverability", float(state[11])),
        ("region_diversity", "Region Diversity", float(state[12])),
    ]

    metrics = [{"key": k, "label": l, "value": round(v, 2), "pct": min(int(v * 100), 100)} for k, l, v in labels]

    issues = []
    if state[10] < 0.6:
        issues.append(f"Low diet match ({state[10]*100:.0f}%) for {diet}")
    if state[11] < 0.5:
        issues.append(f"Undiscovered dishes ({state[11]*100:.0f}% left to explore)")
    if state[12] < 0.3:
        issues.append("Low cuisine diversity — try dishes from other regions")
    if state[0] < 0.3:
        issues.append("Low meal count — add more meals to your plan")

    return jsonify({
        "metrics": metrics,
        "issues": issues,
        "dietCompatibility": round(diet_match, 2),
        "searchQuality": round(search, 2),
        "regionDiversity": round(region_div, 2),
    })


@app.route("/api/v1/ai/recommendations", methods=["POST"])
def recommendations():
    data = request.get_json()
    tray = data.get("trayLibrary", {})
    plan = data.get("planDays", {})
    pantry = data.get("pantryStaples", [])
    diet = data.get("diet", "vegetarian")
    regions = data.get("preferredRegions", [])
    health = data.get("healthGoal")

    state = _extract_features(tray, plan, pantry, health, diet_profile=diet, preferred_regions=regions)
    diet_match = compute_diet_compatibility(tray, diet)
    search = compute_search_quality(tray, diet)

    recs = []
    if diet_match < 0.8:
        recs.append(f"Add dishes that match your {diet} diet to improve compatibility")
    if search < 0.6:
        all_sugs = suggest_next_dishes(tray, diet, regions, count=5)
        if all_sugs:
            names = [d["name"] for d in all_sugs[:3]]
            recs.append(f"Try adding: {', '.join(names)}")
    if state[12] < 0.3:
        recs.append("Explore a new cuisine — try dishes from a different region")
    if not health:
        recs.append("Set a health goal for personalized meal suggestions")
    if state[0] < 0.3:
        recs.append("Plan more meals to build a complete weekly schedule")

    return jsonify({"recommendations": recs, "dietLabel": diet})


@app.route("/api/v1/ai/translate", methods=["POST"])
def translate():
    data = request.get_json()
    key = data.get("key")
    lang = data.get("language", "english")
    params = data.get("params", {})

    if not key or key not in TRANSLATIONS:
        return jsonify({"error": "Invalid translation key"}), 400

    template = TRANSLATIONS[key].get(lang, TRANSLATIONS[key]["english"])
    try:
        translated = template.format(**params)
    except KeyError as e:
        return jsonify({"error": f"Missing param: {e}"}), 400

    return jsonify({"translated": translated, "language": lang})


@app.route("/api/v1/ai/voice", methods=["POST"])
def voice():
    data = request.get_json()
    dish = data.get("dishName", "")
    lang = data.get("language", "hindi")
    region = data.get("region", "north_indian")

    if not dish or dish == "meal-plan":
        dish = "dal-makhani"
    voice_msg = VoiceMessage.sample_for_dish(dish, lang, region)

    recipe = DISHRECIPE_TRANSLATIONS.get(dish, {})
    recipe_text = recipe.get(lang) or recipe.get("english", "")

    return jsonify({
        "voiceMessage": {
            "textHindi": voice_msg.text_hindi,
            "textRegional": voice_msg.text_regional,
            "textEnglish": voice_msg.text_english,
            "durationSec": voice_msg.duration_sec,
            "language": voice_msg.language,
            "region": voice_msg.region,
        },
        "recipeDescription": recipe_text,
    })


@app.route("/api/v1/ai/chat", methods=["POST"])
def chat():
    data = request.get_json()
    action = data.get("action", "")
    params = data.get("params", {})
    lang = data.get("language", "english")

    chat_instance = MealDramaMessenger("MD-App", lang)

    result = {}
    if action == "assign_meal":
        msg = chat_instance.assign_meal(params.get("name", ""), params.get("dish", ""), params.get("slot", ""), lang)
        result = {"type": "meal_assign", "text": msg.content, "dish": msg.dish}
    elif action == "suggest":
        msg = chat_instance.suggest_meal(params.get("name", ""), params.get("dish", ""), params.get("slot", ""), lang)
        result = {"type": "suggest", "text": msg.content}
    elif action == "meal_ready":
        voice = None
        if params.get("voice"):
            voice = VoiceMessage.sample_for_dish(params["dish"], lang, params.get("region", ""))
        msg = chat_instance.meal_ready(params.get("name", ""), params.get("dish", ""), lang, voice)
        result = {"type": "meal_ready", "text": msg.content, "voice": voice is not None}
    elif action == "split_expense":
        msg = chat_instance.split_expense(params.get("name", ""), params.get("item", ""), float(params.get("amount", 0)), lang)
        result = {"type": "expense", "text": msg.content}
    elif action == "assign_slot":
        msg = chat_instance.assign_slot(params.get("name", ""), params.get("slot", ""), lang)
        result = {"type": "slot_assign", "text": msg.content}
    elif action == "rate":
        msg = chat_instance.rate_meal(params.get("name", ""), params.get("dish", ""), int(params.get("rating", 5)), lang)
        result = {"type": "rating", "text": msg.content}
    elif action == "shopping":
        msg = chat_instance.shopping_needed(params.get("name", ""), params.get("dish", ""), params.get("items", ""), lang)
        result = {"type": "shopping", "text": msg.content}
    else:
        return jsonify({"error": f"Unknown action: {action}"}), 400

    return jsonify({"message": result})


if __name__ == "__main__":
    print("\n🥗 MealDrama AI Bridge running on http://localhost:5002\n")
    app.run(host="0.0.0.0", port=5002, debug=True)
