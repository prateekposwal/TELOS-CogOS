"""
MealDrama Dish Library — Regional cuisines × diet profiles × meal slots.
"""

from typing import Dict, List, Optional

DIET_TYPES = ["vegetarian", "eggetarian", "non_veg", "vegan", "jain"]

REGIONS = ["north_indian", "south_indian", "italian", "mexican", "east_asian", "middle_eastern"]

SLOTS = ["breakfast", "lunch", "dinner", "snacks"]

DishEntry = Dict

def diet_tag(diet: str) -> str:
    mapping = {
        "vegetarian": "veg",
        "eggetarian": "egg",
        "non_veg": "nonveg",
        "vegan": "vegan",
        "jain": "jain",
    }
    return mapping.get(diet, "veg")

MEAL_LIBRARY: List[DishEntry] = [
    # ── North Indian ──────────────────────────────────────────
    {"id": "aloo-paratha", "name": "Aloo Paratha", "region": "north_indian", "diet": ["veg", "vegan", "jain"],
     "slots": ["breakfast", "lunch", "dinner"], "ingredients": ["Potato", "Wheat Flour", "Spices"], "protein": 6, "calories": 280},
    {"id": "poha", "name": "Poha", "region": "north_indian", "diet": ["veg", "vegan", "jain"],
     "slots": ["breakfast", "snacks"], "ingredients": ["Rice Flakes", "Peanuts", "Lemon", "Spices"], "protein": 5, "calories": 220},
    {"id": "chole-bhature", "name": "Chole Bhature", "region": "north_indian", "diet": ["veg", "vegan"],
     "slots": ["breakfast", "lunch", "dinner"], "ingredients": ["Chickpeas", "Wheat Flour", "Spices", "Oil"], "protein": 12, "calories": 450},
    {"id": "rajma-chawal", "name": "Rajma Chawal", "region": "north_indian", "diet": ["veg", "vegan", "jain"],
     "slots": ["lunch", "dinner"], "ingredients": ["Kidney Beans", "Rice", "Spices", "Tomato"], "protein": 14, "calories": 380},
    {"id": "dal-makhani", "name": "Dal Makhani", "region": "north_indian", "diet": ["veg", "vegan"],
     "slots": ["lunch", "dinner"], "ingredients": ["Black Lentils", "Cream", "Butter", "Spices"], "protein": 16, "calories": 350},
    {"id": "paneer-butter-masala", "name": "Paneer Butter Masala", "region": "north_indian", "diet": ["veg"],
     "slots": ["lunch", "dinner"], "ingredients": ["Paneer", "Cream", "Tomato", "Butter", "Spices"], "protein": 18, "calories": 400},
    {"id": "roti", "name": "Roti", "region": "north_indian", "diet": ["veg", "vegan", "jain"],
     "slots": ["lunch", "dinner"], "ingredients": ["Wheat Flour"], "protein": 4, "calories": 120},
    {"id": "chicken-curry", "name": "Chicken Curry", "region": "north_indian", "diet": ["nonveg"],
     "slots": ["lunch", "dinner"], "ingredients": ["Chicken", "Onion", "Tomato", "Spices", "Oil"], "protein": 28, "calories": 320},
    {"id": "egg-curry", "name": "Egg Curry", "region": "north_indian", "diet": ["egg", "nonveg"],
     "slots": ["lunch", "dinner"], "ingredients": ["Eggs", "Onion", "Tomato", "Spices"], "protein": 14, "calories": 240},
    {"id": "egg-bhurji", "name": "Egg Bhurji", "region": "north_indian", "diet": ["egg", "nonveg"],
     "slots": ["breakfast", "snacks"], "ingredients": ["Eggs", "Onion", "Spices"], "protein": 12, "calories": 180},

    # ── South Indian ──────────────────────────────────────────
    {"id": "idli", "name": "Idli", "region": "south_indian", "diet": ["veg", "vegan", "jain"],
     "slots": ["breakfast", "dinner", "snacks"], "ingredients": ["Rice", "Urad Dal"], "protein": 5, "calories": 150},
    {"id": "dosa", "name": "Masala Dosa", "region": "south_indian", "diet": ["veg", "vegan", "jain"],
     "slots": ["breakfast", "lunch", "dinner"], "ingredients": ["Rice", "Urad Dal", "Potato", "Spices"], "protein": 6, "calories": 250},
    {"id": "vada", "name": "Medu Vada", "region": "south_indian", "diet": ["veg", "vegan"],
     "slots": ["breakfast", "snacks"], "ingredients": ["Urad Dal", "Spices", "Oil"], "protein": 8, "calories": 200},
    {"id": "sambar-rice", "name": "Sambar Rice", "region": "south_indian", "diet": ["veg", "vegan", "jain"],
     "slots": ["lunch", "dinner"], "ingredients": ["Rice", "Toor Dal", "Vegetables", "Spices", "Tamarind"], "protein": 10, "calories": 300},
    {"id": "rasam-rice", "name": "Rasam Rice", "region": "south_indian", "diet": ["veg", "vegan", "jain"],
     "slots": ["lunch", "dinner"], "ingredients": ["Rice", "Tomato", "Tamarind", "Spices"], "protein": 6, "calories": 250},
    {"id": "curd-rice", "name": "Curd Rice", "region": "south_indian", "diet": ["veg"],
     "slots": ["lunch", "dinner"], "ingredients": ["Rice", "Yogurt", "Spices"], "protein": 8, "calories": 200},
    {"id": "chicken-biryani", "name": "Chicken Biryani", "region": "south_indian", "diet": ["nonveg"],
     "slots": ["lunch", "dinner"], "ingredients": ["Chicken", "Rice", "Spices", "Onion", "Yogurt"], "protein": 25, "calories": 450},
    {"id": "egg-dosa", "name": "Egg Dosa", "region": "south_indian", "diet": ["egg", "nonveg"],
     "slots": ["breakfast", "lunch", "dinner"], "ingredients": ["Rice", "Urad Dal", "Eggs"], "protein": 10, "calories": 280},

    # ── Italian ──────────────────────────────────────────────
    {"id": "pasta-arrabbiata", "name": "Pasta Arrabbiata", "region": "italian", "diet": ["veg", "vegan"],
     "slots": ["lunch", "dinner"], "ingredients": ["Pasta", "Tomato", "Garlic", "Olive Oil", "Chili"], "protein": 8, "calories": 350},
    {"id": "margherita-pizza", "name": "Margherita Pizza", "region": "italian", "diet": ["veg", "jain"],
     "slots": ["lunch", "dinner", "snacks"], "ingredients": ["Wheat Flour", "Mozzarella", "Tomato", "Basil"], "protein": 14, "calories": 400},
    {"id": "risotto", "name": "Mushroom Risotto", "region": "italian", "diet": ["veg", "vegan"],
     "slots": ["lunch", "dinner"], "ingredients": ["Rice", "Mushroom", "Vegetable Stock", "Wine"], "protein": 7, "calories": 350},
    {"id": "eggs-benedict", "name": "Eggs Benedict", "region": "italian", "diet": ["egg", "nonveg"],
     "slots": ["breakfast"], "ingredients": ["Eggs", "Bread", "Butter", "Lemon"], "protein": 18, "calories": 300},
    {"id": "chicken-alfredo", "name": "Chicken Alfredo", "region": "italian", "diet": ["nonveg"],
     "slots": ["lunch", "dinner"], "ingredients": ["Chicken", "Pasta", "Cream", "Parmesan"], "protein": 32, "calories": 500},

    # ── Mexican ──────────────────────────────────────────────
    {"id": "veg-tacos", "name": "Veg Tacos", "region": "mexican", "diet": ["veg", "vegan"],
     "slots": ["lunch", "dinner", "snacks"], "ingredients": ["Corn Tortilla", "Beans", "Vegetables", "Salsa"], "protein": 10, "calories": 250},
    {"id": "bean-burrito", "name": "Bean Burrito", "region": "mexican", "diet": ["veg", "vegan", "jain"],
     "slots": ["lunch", "dinner"], "ingredients": ["Wheat Tortilla", "Beans", "Rice", "Salsa"], "protein": 12, "calories": 350},
    {"id": "chicken-tacos", "name": "Chicken Tacos", "region": "mexican", "diet": ["nonveg"],
     "slots": ["lunch", "dinner", "snacks"], "ingredients": ["Chicken", "Corn Tortilla", "Salsa", "Lime"], "protein": 24, "calories": 280},
    {"id": "huevos-rancheros", "name": "Huevos Rancheros", "region": "mexican", "diet": ["egg", "nonveg"],
     "slots": ["breakfast"], "ingredients": ["Eggs", "Corn Tortilla", "Beans", "Salsa"], "protein": 16, "calories": 320},
    {"id": "guacamole", "name": "Guacamole with Chips", "region": "mexican", "diet": ["veg", "vegan", "jain"],
     "slots": ["snacks"], "ingredients": ["Avocado", "Lime", "Onion", "Tomato", "Corn Chips"], "protein": 3, "calories": 200},

    # ── East Asian ────────────────────────────────────────────
    {"id": "fried-rice", "name": "Vegetable Fried Rice", "region": "east_asian", "diet": ["veg", "vegan", "jain"],
     "slots": ["lunch", "dinner"], "ingredients": ["Rice", "Vegetables", "Soy Sauce", "Oil"], "protein": 6, "calories": 300},
    {"id": "noodles", "name": "Veg Hakka Noodles", "region": "east_asian", "diet": ["veg", "vegan"],
     "slots": ["lunch", "dinner", "snacks"], "ingredients": ["Noodles", "Vegetables", "Soy Sauce", "Oil"], "protein": 7, "calories": 320},
    {"id": "sushi", "name": "Vegetable Sushi", "region": "east_asian", "diet": ["veg", "vegan", "jain"],
     "slots": ["lunch", "dinner", "snacks"], "ingredients": ["Rice", "Seaweed", "Vegetables", "Vinegar"], "protein": 5, "calories": 200},
    {"id": "chicken-stir-fry", "name": "Chicken Stir Fry", "region": "east_asian", "diet": ["nonveg"],
     "slots": ["lunch", "dinner"], "ingredients": ["Chicken", "Vegetables", "Soy Sauce", "Ginger", "Garlic"], "protein": 30, "calories": 280},
    {"id": "egg-fried-rice", "name": "Egg Fried Rice", "region": "east_asian", "diet": ["egg", "nonveg"],
     "slots": ["lunch", "dinner"], "ingredients": ["Rice", "Eggs", "Vegetables", "Soy Sauce"], "protein": 12, "calories": 320},
    {"id": "ramen-veg", "name": "Vegetable Ramen", "region": "east_asian", "diet": ["veg", "vegan"],
     "slots": ["lunch", "dinner"], "ingredients": ["Noodles", "Vegetable Broth", "Vegetables", "Tofu"], "protein": 10, "calories": 350},
    {"id": "ramen-egg", "name": "Egg Ramen", "region": "east_asian", "diet": ["egg", "nonveg"],
     "slots": ["lunch", "dinner"], "ingredients": ["Noodles", "Broth", "Eggs", "Vegetables"], "protein": 14, "calories": 380},
    {"id": "ramen-chicken", "name": "Chicken Ramen", "region": "east_asian", "diet": ["nonveg"],
     "slots": ["lunch", "dinner"], "ingredients": ["Noodles", "Chicken Broth", "Chicken", "Eggs"], "protein": 28, "calories": 420},

    # ── Middle Eastern ────────────────────────────────────────
    {"id": "hummus-pita", "name": "Hummus with Pita", "region": "middle_eastern", "diet": ["veg", "vegan", "jain"],
     "slots": ["breakfast", "snacks", "lunch"], "ingredients": ["Chickpeas", "Tahini", "Lemon", "Olive Oil", "Pita"], "protein": 10, "calories": 280},
    {"id": "falafel-wrap", "name": "Falafel Wrap", "region": "middle_eastern", "diet": ["veg", "vegan"],
     "slots": ["lunch", "dinner"], "ingredients": ["Chickpeas", "Pita", "Vegetables", "Tahini"], "protein": 14, "calories": 350},
    {"id": "shawarma-chicken", "name": "Chicken Shawarma", "region": "middle_eastern", "diet": ["nonveg"],
     "slots": ["lunch", "dinner"], "ingredients": ["Chicken", "Pita", "Garlic Sauce", "Vegetables"], "protein": 26, "calories": 380},
    {"id": "shakshuka", "name": "Shakshuka", "region": "middle_eastern", "diet": ["egg", "nonveg", "veg"],
     "slots": ["breakfast", "lunch", "dinner"], "ingredients": ["Eggs", "Tomato", "Spices", "Olive Oil"], "protein": 14, "calories": 220},
    {"id": "baba-ganoush", "name": "Baba Ganoush", "region": "middle_eastern", "diet": ["veg", "vegan", "jain"],
     "slots": ["snacks"], "ingredients": ["Eggplant", "Tahini", "Lemon", "Olive Oil"], "protein": 3, "calories": 150},
]


def get_dishes_by_diet(diet: str) -> List[DishEntry]:
    key = diet_tag(diet)
    return [d for d in MEAL_LIBRARY if key in d["diet"]]


def get_dishes_by_region(region: str) -> List[DishEntry]:
    return [d for d in MEAL_LIBRARY if d["region"] == region]


def get_dishes_by_slot(slot: str) -> List[DishEntry]:
    return [d for d in MEAL_LIBRARY if slot in d["slots"]]


def get_dishes(diet: Optional[str] = None, region: Optional[str] = None,
               slot: Optional[str] = None) -> List[DishEntry]:
    results = list(MEAL_LIBRARY)
    if diet:
        key = diet_tag(diet)
        results = [d for d in results if key in d["diet"]]
    if region:
        results = [d for d in results if d["region"] == region]
    if slot:
        results = [d for d in results if slot in d["slots"]]
    return results


def compute_diet_compatibility(tray_library: Dict[str, List], diet: str) -> float:
    key = diet_tag(diet)
    total = sum(len(v) for v in tray_library.values())
    if total == 0:
        return 0.0
    compatible = 0
    for slot, dishes in tray_library.items():
        for d in dishes:
            dish_id = d["id"] if isinstance(d, dict) else d
            dish = next((m for m in MEAL_LIBRARY if m["id"] == dish_id), None)
            if dish and key in dish["diet"]:
                compatible += 1
            elif dish is None:
                compatible += 1
    return compatible / max(total, 1)


def compute_search_quality(tray_library: Dict[str, List], diet: str) -> float:
    """How many diet-compatible dishes exist in the library that are NOT in the tray."""
    key = diet_tag(diet)
    tray_ids = set()
    for dishes in tray_library.values():
        for d in dishes:
            dish_id = d["id"] if isinstance(d, dict) else d
            tray_ids.add(dish_id)
    available = [d for d in MEAL_LIBRARY if key in d["diet"] and d["id"] not in tray_ids]
    total_possible = len([d for d in MEAL_LIBRARY if key in d["diet"]])
    return len(available) / max(total_possible, 1)


def compute_region_diversity(tray_library: Dict[str, List]) -> float:
    regions_seen = set()
    for dishes in tray_library.values():
        for d in dishes:
            dish_id = d["id"] if isinstance(d, dict) else d
            dish = next((m for m in MEAL_LIBRARY if m["id"] == dish_id), None)
            if dish:
                regions_seen.add(dish["region"])
    return len(regions_seen) / max(len(REGIONS), 1)
