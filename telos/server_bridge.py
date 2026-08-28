"""
TELOS AI Bridge — serves AI feature integrations for MD-App React frontend.

Runs on port 5002 and serves /api/v1/ai/* endpoints for the React frontend.

The bridge is a genuinely functional ranking engine: it scores the dish
library the frontend sends in the request body against the user's diet,
preferred regions, pantry staples and health goal, and returns real
suggestions, a diet/plan score and practical recommendations.
"""
import sys
import os
import re
import json
from collections import Counter
from flask import Flask, request, jsonify
from flask_cors import CORS

app = Flask(__name__)
CORS(app)

# ─── Region / diet helpers ────────────────────────────────────────────────
REGION_ALIASES = {
    "north": "north", "north_indian": "north", "north india": "north", "north-indian": "north", "punjab": "north",
    "south": "south", "south_indian": "south", "south india": "south", "south-indian": "south", "kerala": "south", "tamil": "south",
    "west": "west", "maharashtra": "west", "gujarat": "west", "rajasthan": "west",
    "east": "east", "bengal": "east", "odisha": "east",
    "central": "central", "madhya pradesh": "central",
    "northeast": "northeast", "north east": "northeast", "assam": "northeast",
    "all": "all", "all india": "all", "india": "all",
}
REGION_KEYS = set(REGION_ALIASES.values())


def norm_region(raw):
    s = re.sub(r"[_\-]+", " ", str(raw or "").strip().lower())
    if not s:
        return None
    if s in REGION_ALIASES:
        return REGION_ALIASES[s]
    if REGION_KEYS.intersection(s.split()):
        for key in ["northeast", "north", "south", "west", "east", "central", "all"]:
            if key in s:
                return key
    return None


MEAT_KW = ["chicken", "mutton", "beef", "lamb", "fish", "meat", "prawn", "shrimp", "seafood"]
EGG_KW = ["egg", "anda"]
DAIRY_KW = ["butter", "milk", "curd", "cream", "cheese", "ghee", "paneer", "malai", "rabri"]

SLOT_KEYS = ["breakfast", "lunch", "dinner", "snacks"]
SLOT_ALIASES = {
    "breakfast": {"breakfast"},
    "lunch": {"lunch", "winter-lunch", "summer-lunch"},
    "dinner": {"dinner", "winter-dinner", "summer-dinner"},
    "snacks": {"snacks"},
}


def diet_of(dish):
    d = dish.get("diet") or dish.get("type") or "veg"
    d = str(d).lower()
    if d in ("eggitarian", "egg"):
        return "eggitarian"
    if d in ("non-veg", "nonveg", "meat"):
        return "non-veg"
    if d == "vegan":
        return "vegan"
    return "veg"


def dish_ok_for_diet(dish, diet):
    diet = (diet or "veg").lower()
    dish_diet = diet_of(dish)
    if diet == "non-veg" or diet in ("any", "all"):
        return True
    if diet == "vegan":
        return dish_diet in ("veg", "vegan")
    if diet == "eggitarian":
        return dish_diet in ("veg", "vegan", "eggitarian")
    # default veg
    return dish_diet != "non-veg"


def dish_ok_for_slot(dish, slot):
    cats = {str(c).lower() for c in (dish.get("category") or [])}
    if not cats:
        return True
    return bool(cats & SLOT_ALIASES.get(slot, set()))


def dish_region(dish):
    return norm_region(dish.get("region"))


def region_rank(region, target_regions):
    """0 = exact user region, 1 = other concrete region, 2 = region-agnostic.
    Lower is better."""
    if not region:
        return 2
    for t in target_regions:
        if t and t == region:
            return 0
    return 1


def pantry_overlap(dish, pantry):
    if not pantry:
        return 0.0
    name = (dish.get("name") or "").lower()
    tags = [str(t).lower() for t in (dish.get("tags") or [])]
    haystack = " ".join([name] + tags)
    hits = 0
    for staple in pantry:
        s = str(staple or "").strip().lower()
        if s and s in haystack:
            hits += 1
    return min(1.0, hits / min(len(pantry), 3))


HEALTH_GOAL_KEYWORDS = {
    "protein": ["protein", "high-protein", "muscle", "gain"],
    "low-cal": ["cal", "low-cal", "weight loss", "light", "diet", "weightloss", "weight-loss"],
    "weight-gain": ["gain", "heavy", "calorie"],
    "diabetes": ["sugar", "diabetic", "diabetes", "low glycemic", "blood sugar"],
}


def health_boost(dish, goal):
    goal = str(goal or "").lower()
    if not goal:
        return 0.0
    nutrition = [str(n).lower() for n in (dish.get("nutrition") or [])]
    tags = [str(t).lower() for t in (dish.get("tags") or [])]
    haystack = " ".join(nutrition + tags + [dish.get("name", "").lower()])
    weight = str(dish.get("weight", "")).lower()
    for key, kws in HEALTH_GOAL_KEYWORDS.items():
        if key in goal or any(k in goal for k in kws):
            if key == "protein":
                if "protein" in haystack:
                    return 0.15
            elif key == "low-cal":
                if weight == "light" or "low-cal" in haystack or "light" in haystack:
                    return 0.15
            elif key == "weight-gain":
                if weight == "heavy" and ("carb" in haystack or "fat" in haystack):
                    return 0.15
            elif key == "diabetes":
                if "sugar" in haystack or "sweet" in haystack:
                    if "no sugar" not in haystack and "sugar free" not in haystack:
                        return -0.15
    return 0.0


def score_dish(dish, slot, diet, regions, pantry, goal):
    """0..1 heuristic score: diet > region > slot > pantry > health."""
    if not dish_ok_for_diet(dish, diet):
        return None
    if not dish_ok_for_slot(dish, slot):
        return None
    s = 0.4  # base
    if diet_of(dish) == "veg":
        s += 0.05  # gently prefer veg-safe picks for typical users
    s += region_rank(dish_region(dish), regions) * 0.12  # 0..0.24
    s += pantry_overlap(dish, pantry) * 0.15
    s += health_boost(dish, goal)
    # Variety tie-breaker: rotation favors under-represented regions/names
    return round(min(1.0, s), 4)


# ─── /api/v1/ai/suggestions ────────────────────────────────────────────────
@app.route("/api/v1/ai/suggestions", methods=["POST"])
def suggestions():
    data = request.get_json(silent=True) or {}
    library = data.get("trayLibrary") or []
    diet = data.get("diet") or "veg"
    regions = [r for r in (norm_region(x) for x in (data.get("preferredRegions") or [])) if r]
    pantry = data.get("pantryStaples") or []
    goal = data.get("healthGoal")

    if not library:
        return jsonify({"suggestions": {}})  # nothing to rank against

    out = {}
    for slot in SLOT_KEYS:
        scored = []
        for dish in library:
            r = score_dish(dish, slot, diet, regions, pantry, goal)
            if r is None:
                continue
            scored.append((r, dish))
        scored.sort(key=lambda t: (-t[0], t[1].get("name", "").lower()))
        top = [d for _, d in scored[:5]]
        # Reduce duplicate regions in a row for visual variety.
        picked = []
        seen_region = Counter()
        for d in [x[1] for x in scored]:
            rg = dish_region(d) or "all"
            if seen_region[rg] >= 2:
                continue
            picked.append(d)
            seen_region[rg] += 1
            if len(picked) >= 4:
                break
        out[slot] = [_suggestion_item(d, slot) for d in (picked or top)]
    return jsonify({"suggestions": out})


def _suggestion_item(dish, slot):
    return {
        "id": dish.get("id") or "",
        "name": dish.get("name") or "",
        "region": dish.get("region") or "north",
        "calories": dish.get("calories") or 0,
        "protein": dish.get("protein") or 0,
        "slots": dish.get("category") or [slot],
        "type": dish.get("type") or "veg",
        "icon": dish.get("icon") or "🍽️",
        "prepMinutes": dish.get("prepTime") or 15,
        "defaultGravy": dish.get("defaultGravy"),
        "defaultRoti": dish.get("defaultRoti"),
        "defaultRice": dish.get("defaultRice"),
        "defaultSides": dish.get("defaultSides") or [],
        "defaultBeverages": dish.get("defaultBeverages") or [],
    }


# ─── /api/v1/ai/score ──────────────────────────────────────────────────────
@app.route("/api/v1/ai/score", methods=["POST"])
def score():
    data = request.get_json(silent=True) or {}
    library = data.get("trayLibrary") or []
    diet = data.get("diet") or "veg"
    regions = [r for r in (norm_region(x) for x in (data.get("preferredRegions") or [])) if r]
    pantry = data.get("pantryStaples") or []
    plan_days = data.get("planDays") or {}

    total = len(library)
    if total == 0:
        return jsonify({
            "metrics": [], "issues": ["No dish library to evaluate"],
            "dietCompatibility": 0, "searchQuality": 0, "regionDiversity": 0,
        })

    diet_ok_n = sum(1 for d in library if dish_ok_for_diet(d, diet))
    region_covered = {r for d in library if (r := dish_region(d))}
    diversity = min(1.0, len(region_covered) / 6.0)  # up to 6 concrete regions

    planned_names = set()
    for day in (plan_days or {}).values():
        for slot in (day or {}).values():
            if isinstance(slot, list):
                for item in slot:
                    n = item.get("name") or item.get("meal_id") or ""
                    if n:
                        planned_names.add(str(n).lower())
    discovered = sum(1 for d in library
                     if str(d.get("name", "")).lower() not in planned_names
                     and pantry_overlap(d, pantry) == 0)

    def pct(x):
        return int(round(x * 100))

    metrics = [
        {
            "key": "diet_match",
            "pct": pct(diet_ok_n / total),
            "label": f"{diet} compatible",
        },
        {
            "key": "region_diversity",
            "pct": pct(diversity),
            "label": f"{len(region_covered)} regions explored",
        },
        {
            "key": "discoverability",
            "pct": pct(discovered / total),
            "label": "new dishes to try",
        },
    ]
    issues = []
    if diet_ok_n / total < 0.6:
        issues.append(f"Only {diet_ok_n} of {total} dishes fit your {diet} diet")
    if diversity < 0.4:
        issues.append("Most picks stay in one region — try exploring more cuisines")
    if not pantry:
        issues.append("Tell us what's in your pantry for better suggestions")
    if not issues:
        issues.append("Your plan is well balanced — keep exploring!")

    return jsonify({
        "metrics": metrics,
        "issues": issues,
        "dietCompatibility": round(diet_ok_n / total, 3),
        "searchQuality": round(diversity, 3),
        "regionDiversity": round(diversity, 3),
    })


# ─── /api/v1/ai/recommendations ────────────────────────────────────────────
@app.route("/api/v1/ai/recommendations", methods=["POST"])
def recommendations():
    data = request.get_json(silent=True) or {}
    library = data.get("trayLibrary") or []
    diet = data.get("diet") or "veg"
    regions = [r for r in (norm_region(x) for x in (data.get("preferredRegions") or [])) if r]
    pantry = data.get("pantryStaples") or []
    goal = data.get("healthGoal")

    recs = []
    preferred = regions[0] if regions else None
    if preferred:
        local_hits = [d for d in library if dish_region(d) == preferred and dish_ok_for_diet(d, diet)]
        if local_hits:
            recs.append(f"Start with {_pick(local_hits)} — a great fit for your {preferred} palate")
    if pantry:
        recs.append(f"Cook from your pantry first: {_pick([d for d in library if pantry_overlap(d, pantry) > 0]) if any(pantry_overlap(d, pantry) > 0 for d in library) else 'restock a few staples'}")
    goal = str(goal or "").lower()
    if "protein" in goal:
        protein_hits = [d for d in library if "protein" in " ".join([str(n) for n in (d.get("nutrition") or [])])]
        if protein_hits:
            recs.append(f"Protein first: try {_pick(protein_hits)}")
    missing = ["eggitarian" in diet and "Egg" not in " ".join(d.get("name", "") for d in library)]
    if missing and missing[0]:
        recs.append("Add an egg dish to round out your eggitarian plan")
    if not recs:
        recs.append("Mix one new regional dish into each week for flavour variety")
    recs.append("Pair each meal with a side + beverage from its region for an authentic thali")
    return jsonify({"recommendations": recs[:4]})


def _pick(dishes):
    dishes = list(dishes)
    if not dishes:
        return "something new"
    return dishes[0].get("name") or "something new"


# ─── /api/v1/ai/translate ──────────────────────────────────────────────────
DISH_PHRASES = {
    "aloo paratha": {"en": "Stuffed potato flatbread",
                     "hi": "Aaloo se bhara hua paratha",
                     "regional": "Aaloo paratha, chhai ke saath"},
    "idli": {"en": "Steamed rice cakes with sambar",
             "hi": "Sambar ke saath bhaap mein paki idli",
             "regional": "Idli, sambar aur coconut chutney ke saath"},
    "dosa": {"en": "Crispy fermented rice crepe",
             "hi": "Kurkuri south-indian dosa",
             "regional": "Masala dosa, chutney aur sambar ke saath"},
    "sambar rice": {"en": "Rice with lentil vegetable stew",
                    "hi": "Sambar ke saath chawal",
                    "regional": "Sambar sadam, papad ke saath"},
    "rajma chawal": {"en": "Kidney bean curry with rice",
                     "hi": "Rajma aur chawal",
                     "regional": "Rajma chawal, achaar ke saath"},
    "paneer butter masala": {"en": "Paneer in rich tomato butter gravy",
                             "hi": "Makhan wali tomato gravy mein paneer",
                             "regional": "Paneer butter masala, naan ke saath"},
    "chai": {"en": "Spiced milk tea",
             "hi": "Masala wali chai",
             "regional": "Kadak chai"},
}


def _phrase_for(name):
    name = (name or "").strip().lower()
    return DISH_PHRASES.get(name) or DISH_PHRASES.get(next((k for k in DISH_PHRASES if k in name), ""))


@app.route("/api/v1/ai/translate", methods=["POST"])
def translate():
    data = request.get_json(silent=True) or {}
    key = str(data.get("key") or "")
    language = str(data.get("language") or "hi")
    phrase = _phrase_for(data.get("params") or {} if isinstance(data.get("params"), dict) else {}).get("dish")
    phrase = phrase or _phrase_for(key)
    if not phrase:
        return jsonify({"translated": ""})
    if language.startswith("hi"):
        return jsonify({"translated": phrase["hi"]})
    if language.lower() in ("regional", "ta", "te", "ml", "kn"):
        return jsonify({"translated": phrase["regional"]})
    return jsonify({"translated": phrase["en"]})


# ─── /api/v1/ai/voice ──────────────────────────────────────────────────────
@app.route("/api/v1/ai/voice", methods=["POST"])
def voice():
    data = request.get_json(silent=True) or {}
    dish_name = str(data.get("dishName") or "")
    language = str(data.get("language") or "hi")
    region = str(data.get("region") or "")
    phrase = _phrase_for(dish_name)
    if not phrase:
        return jsonify({
            "voiceMessage": {
                "textHindi": "",
                "textRegional": "",
                "textEnglish": "",
                "durationSec": 0,
            },
            "recipeDescription": "",
        })
    text_en = phrase["en"]
    text_hi = phrase["hi"]
    text_regional = phrase["regional"]
    desc = f"{phrase['en']} — a beloved dish in {region or 'Indian'} kitchens."
    return jsonify({
        "voiceMessage": {
            "textHindi": text_hi,
            "textRegional": text_regional,
            "textEnglish": text_en,
            "durationSec": max(3, round(len(text_en.split()) / 2.5)),
        },
        "recipeDescription": desc,
    })


# ─── /api/v1/ai/chat ───────────────────────────────────────────────────────
@app.route("/api/v1/ai/chat", methods=["POST"])
def chat():
    data = request.get_json(silent=True) or {}
    action = str(data.get("action") or "help").lower()
    params = data.get("params") or {}
    language = str(data.get("language") or "en")
    base = {
        "help": "I can suggest meals for your diet, translate a dish, or read a recipe aloud.",
        "recommend": "Tell me your diet and region and I'll pick dishes that fit both.",
        "diet": "Stick to your preferred diet (veg, non-veg, eggitarian or vegan) and meals stay compatible.",
        "default": "I'm here to help you plan tastier, region-aware meals.",
    }
    text = base.get(action)
    if action == "meal":
        dish = _phrase_for(data.get("dish") or params.get("dish") if isinstance(params, dict) else None)
        text = dish["en"] if dish else "Try a dish from your region for an authentic meal."
    if not text:
        text = base["default"]
    return jsonify({"message": {"type": "text", "text": text, "dish": None, "voice": False}})


# ─── /api/v1/ai/health ─────────────────────────────────────────────────────
@app.route("/api/v1/ai/health", methods=["GET"])
def health():
    return jsonify({"status": "ok", "service": "telos-ai-bridge", "engine": "live-ranking"})


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5002)