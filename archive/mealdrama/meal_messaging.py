"""
MealDrama WhatsApp-style messaging — language translation, voice messages,
regional meal descriptions, and collective household chat.
"""

import random
from datetime import datetime
from typing import List, Dict, Optional, Any
from enum import Enum
from dataclasses import dataclass, field


LANGUAGES = ["english", "hindi", "tamil", "telugu", "bengali", "marathi", "gujarati", "punjabi"]


TRANSLATIONS = {
    "i_will_cook": {
        "english": "{name} will cook {dish} for {slot}",
        "hindi": "{name} {slot} ke liye {dish} banayenge",
        "tamil": "{name} {slot} kku {dish} samaippar",
        "telugu": "{name} {slot} ki {dish} vandutaru",
        "bengali": "{name} {slot} er jonyo {dish} ranna korbe",
        "marathi": "{name} {slot} sathi {dish} shijwel",
        "gujarati": "{name} {slot} mate {dish} banavshe",
        "punjabi": "{name} {slot} layi {dish} banavega",
    },
    "suggest_meal": {
        "english": "How about {dish} for {slot}?",
        "hindi": "{slot} ke liye {dish} kaisa rahega?",
        "tamil": "{slot} kku {dish} eppadi?",
        "telugu": "{slot} ki {dish} ela untundi?",
        "bengali": "{slot} er jonyo {dish} kemon hobe?",
        "marathi": "{slot} sathi {dish} kasa vatel?",
        "gujarati": "{slot} mate {dish} kem raheshe?",
        "punjabi": "{slot} layi {dish} kiwein hovega?",
    },
    "meal_ready": {
        "english": "{dish} is ready! Come eat!",
        "hindi": "{dish} taiyar hai! Khaane aao!",
        "tamil": "{dish} ready! Sapitanga!",
        "telugu": "{dish} ready! Tinadaaniki raa!",
        "bengali": "{dish} ready! Khete aso!",
        "marathi": "{dish} ready! Jevnyala ya!",
        "gujarati": "{dish} ready! Khaava aavo!",
        "punjabi": "{dish} ready! Khaan nu aao!",
    },
    "shopping_needed": {
        "english": "We need {items} for {dish}",
        "hindi": "{dish} ke liye {items} chahiye",
        "tamil": "{dish} kku {items} venum",
        "telugu": "{dish} ki {items} kavali",
        "bengali": "{dish} er jonyo {items} dorkar",
        "marathi": "{dish} sathi {items} lagto",
        "gujarati": "{dish} mate {items} joie",
        "punjabi": "{dish} layi {items} chahide",
    },
    "split_expense": {
        "english": "Split ₹{amount} for {item} — ₹{share} each",
        "hindi": "{item} ke liye ₹{amount} — ₹{share} prati vyakti",
        "tamil": "{item} kku ₹{amount} — ₹{share} ovvorutharkum",
        "telugu": "{item} ki ₹{amount} — ₹{share} okkokarikii",
        "bengali": "{item} er jonyo ₹{amount} — ₹{share} proti jon",
        "marathi": "{item} sathi ₹{amount} — ₹{share} prati vyakti",
        "gujarati": "{item} mate ₹{amount} — ₹{share} prati vyakti",
        "punjabi": "{item} layi ₹{amount} — ₹{share} har ikk nu",
    },
    "rate_meal": {
        "english": "Rate {dish}: ⭐⭐⭐⭐⭐",
        "hindi": "{dish} ko rate karein: ⭐⭐⭐⭐⭐",
        "tamil": "{dish} kku rating: ⭐⭐⭐⭐⭐",
        "telugu": "{dish} ki rating: ⭐⭐⭐⭐⭐",
        "bengali": "{dish} er rating: ⭐⭐⭐⭐⭐",
        "marathi": "{dish} la rating: ⭐⭐⭐⭐⭐",
        "gujarati": "{dish} ne rating: ⭐⭐⭐⭐⭐",
        "punjabi": "{dish} nu rating: ⭐⭐⭐⭐⭐",
    },
    "assign_slot": {
        "english": "{name} takes {slot} slot",
        "hindi": "{name} {slot} ka slot lete hain",
        "tamil": "{name} {slot} slot eduppar",
        "telugu": "{name} {slot} slot teesukuntaru",
        "bengali": "{name} {slot} slot nicche",
        "marathi": "{name} {slot} slot ghetoy",
        "gujarati": "{name} {slot} slot lai che",
        "punjabi": "{name} {slot} slot lainda hai",
    },
}


SLOT_TRANSLATIONS = {
    "breakfast": {"english": "breakfast", "hindi": "naashta", "tamil": "kaalai", "telugu": "upaharam", "bengali": "nashta", "marathi": "nashta", "gujarati": "nashto", "punjabi": "nashta"},
    "lunch": {"english": "lunch", "hindi": "dopahar ka khana", "tamil": "madiyam", "telugu": "madiyam bhojanam", "bengali": "dupur", "marathi": "dupaar", "gujarati": "bapor", "punjabi": "dupahar da khana"},
    "dinner": {"english": "dinner", "hindi": "raat ka khana", "tamil": "iravu", "telugu": "raatri bhojanam", "bengali": "raat", "marathi": "raatri", "gujarati": "raatno", "punjabi": "raat da khana"},
    "snacks": {"english": "snacks", "hindi": "nashta", "tamil": "sina", "telugu": "chinna", "bengali": "jalakhabar", "marathi": "khau", "gujarati": "fafda", "punjabi": "nashta"},
}


DISHRECIPE_TRANSLATIONS = {
    "dal-makhani": {
        "english": "Slow-cooked black lentils in creamy tomato gravy",
        "hindi": "Malai daar ya tamatar ki grevi mein dheemi aanch par pakaaye gaye kaale masoor ki daal",
        "tamil": "Kulambu thanni ilaithu kozhuthu akkappatta karuppu paruppu",
        "bengali": "Malai daal aar tomaar jholey dheere aagye ranna kora kaalo masoor daal",
    },
    "rajma-chawal": {
        "english": "Red kidney beans curry with steamed rice",
        "hindi": "Uble chawal ke saath laal raajma ki sabzi",
        "tamil": "Soodaana saadamudan sigappu karuppu kulambu",
        "bengali": "Bhaat-er saathe laal raajma torkari",
    },
    "chicken-curry": {
        "english": "Spiced chicken simmered in onion-tomato gravy",
        "hindi": "Pyaaz-tamatar ke gravy mein pakka hua murg masala",
        "tamil": "Vengaya-thakkali kulambula venthathu kozhi",
        "bengali": "Peyaj-tomaar jholey ranna kora murgi",
    },
    "dosa": {
        "english": "Crispy fermented rice-lentil crepe",
        "hindi": "Khasta khaameer wala chawal-udad daal ka cheela",
        "tamil": "Soodaana arisi-paruppu maavu dose",
        "telugu": "Vepadu lo unna biyyam-pappu pindi dosa",
    },
    "pasta-arrabbiata": {
        "english": "Spicy tomato garlic pasta with olive oil",
        "hindi": "Lahsun aur mirch wala tamatar pasta",
        "tamil": "Kaara thakkali-poondu pasta",
    },
}


@dataclass
class VoiceMessage:
    """A recorded voice message describing a meal in a regional language."""
    text_hindi: str = ""
    text_regional: str = ""
    text_english: str = ""
    duration_sec: int = 0
    language: str = "hindi"
    region: str = ""

    def display(self, lang: str = "english") -> str:
        if lang == "hindi":
            return f"🎤 {self.text_hindi} ({self.duration_sec}s)"
        if lang in LANGUAGES and lang != "english" and self.text_regional:
            return f"🎤 {self.text_regional} ({self.duration_sec}s)"
        return f"🎤 {self.text_english} ({self.duration_sec}s)"

    @staticmethod
    def sample_for_dish(dish_name: str, lang: str = "hindi", region: str = "north_indian") -> "VoiceMessage":
        texts = {
            "dal-makhani": {
                "hindi": "Daal makhani bahut achhi bani hai, saara ghar mehek raha hai. Khaane aa jao!",
                "punjabi": "Dal makhani bahut sohni bani aa, poora ghar mahak reha aa. Khaan nu aa jao!",
                "tamil": "Dal makhani romba nalla aagiruchu. Veedhu ellam manam adikkuthu. Sapaadu saapadu!",
            },
            "chicken-biryani": {
                "hindi": "Chicken biryani taiyaar hai, dum mein pakaayi gayi hai. Zaroor aakar try karein!",
                "telugu": "Chicken biryani ready, dum lo vandindi. Tappakunda try cheyandi!",
                "bengali": "Chicken biryani ready, dhum-e ranna kora. Ese try korben!",
            },
            "dosa": {
                "hindi": "Dosa crispy bana hai, saath mein sambar aur chutney. Naashta kar lo!",
                "tamil": "Dose crispy aagiruchu! Sambar chutney ready. Kaalai saapadu saapadu!",
            },
        }
        t = texts.get(dish_name, {}).get(lang, texts.get(dish_name, {}).get("hindi", f"{dish_name} ready! Come eat!"))
        eng = f"{dish_name} is ready!"
        return VoiceMessage(
            text_hindi=t if lang == "hindi" else texts.get(dish_name, {}).get("hindi", eng),
            text_regional=t if lang != "hindi" else "",
            text_english=eng,
            duration_sec=random.randint(8, 30),
            language=lang,
            region=region,
        )


class MessageType(Enum):
    TEXT = "text"
    MEAL_ASSIGN = "meal_assign"
    MEAL_SUGGEST = "meal_suggest"
    MEAL_READY = "meal_ready"
    EXPENSE = "expense"
    VOICE = "voice"
    SHOPPING = "shopping"
    RATING = "rating"
    SLOT_ASSIGN = "slot_assign"
    SYSTEM = "system"


@dataclass
class Message:
    msg_type: MessageType
    sender: str
    content: str
    language: str = "english"
    timestamp: str = ""
    voice: Optional[VoiceMessage] = None
    dish: str = ""
    slot: str = ""
    amount: float = 0.0
    metadata: Dict[str, Any] = field(default_factory=dict)

    def __post_init__(self):
        if not self.timestamp:
            self.timestamp = datetime.now().strftime("%H:%M")

    def display(self, lang: str = "english") -> str:
        if self.voice and self.msg_type == MessageType.VOICE:
            return self.voice.display(lang)
        if lang == "english" or lang == self.language:
            return self.content
        return f"{self.content}"

    def to_chat_line(self, lang: str = "english") -> str:
        icon_map = {
            MessageType.TEXT: "",
            MessageType.MEAL_ASSIGN: "🍳",
            MessageType.MEAL_SUGGEST: "💡",
            MessageType.MEAL_READY: "🍽️",
            MessageType.EXPENSE: "💰",
            MessageType.VOICE: "🎤",
            MessageType.SHOPPING: "🛒",
            MessageType.RATING: "⭐",
            MessageType.SLOT_ASSIGN: "📋",
            MessageType.SYSTEM: "🔔",
        }
        icon = icon_map.get(self.msg_type, "")
        content = self.display(lang)
        return f"[{self.timestamp}] {icon} {self.sender}: {content}"


class MealDramaMessenger:
    """WhatsApp-style group chat for household meal coordination."""

    def __init__(self, household_name: str, default_lang: str = "english"):
        self.household_name = household_name
        self.default_lang = default_lang
        self.members: List[Dict] = []
        self.messages: List[Message] = []
        self.meal_schedule: Dict[str, Dict[str, Optional[str]]] = {}  # {date: {slot: member_id}}

    def add_member(self, name: str, user_id: str, languages: Optional[List[str]] = None):
        self.members.append({
            "name": name, "user_id": user_id,
            "languages": languages or ["english"],
        })
        self._system(f"{name} joined the household")

    def remove_member(self, user_id: str):
        member = next((m for m in self.members if m["user_id"] == user_id), None)
        if member:
            self.members = [m for m in self.members if m["user_id"] != user_id]
            self._system(f"{member['name']} left the household")

    def send(self, msg_type: MessageType, sender: str, content: str = "",
             language: str = "english", **kwargs) -> Message:
        msg = Message(
            msg_type=msg_type, sender=sender, content=content,
            language=language, **kwargs
        )
        self.messages.append(msg)
        return msg

    def _system(self, text: str) -> Message:
        return self.send(MessageType.SYSTEM, "📱 MealDrama", text)

    def assign_meal(self, member_name: str, dish: str, slot: str, language: str = "english") -> Message:
        template = TRANSLATIONS["i_will_cook"].get(language, TRANSLATIONS["i_will_cook"]["english"])
        slot_local = SLOT_TRANSLATIONS.get(slot, {}).get(language, slot)
        content = template.format(name=member_name, dish=dish, slot=slot_local)
        return self.send(MessageType.MEAL_ASSIGN, member_name, content,
                        language=language, dish=dish, slot=slot)

    def suggest_meal(self, member_name: str, dish: str, slot: str, language: str = "english") -> Message:
        template = TRANSLATIONS["suggest_meal"].get(language, TRANSLATIONS["suggest_meal"]["english"])
        slot_local = SLOT_TRANSLATIONS.get(slot, {}).get(language, slot)
        content = template.format(dish=dish, slot=slot_local)
        return self.send(MessageType.MEAL_SUGGEST, member_name, content,
                        language=language, dish=dish, slot=slot)

    def meal_ready(self, member_name: str, dish: str, language: str = "english",
                   voice: Optional[VoiceMessage] = None) -> Message:
        template = TRANSLATIONS["meal_ready"].get(language, TRANSLATIONS["meal_ready"]["english"])
        content = template.format(dish=dish)
        return self.send(MessageType.MEAL_READY, member_name, content,
                        language=language, dish=dish, voice=voice)

    def send_voice(self, member_name: str, voice: VoiceMessage) -> Message:
        return self.send(MessageType.VOICE, member_name, "",
                        language=voice.language, voice=voice)

    def split_expense(self, member_name: str, item: str, amount: float,
                      language: str = "english") -> Message:
        share = round(amount / max(len(self.members), 1), 2)
        template = TRANSLATIONS["split_expense"].get(language, TRANSLATIONS["split_expense"]["english"])
        content = template.format(amount=amount, item=item, share=share)
        return self.send(MessageType.EXPENSE, member_name, content,
                        language=language, amount=amount)

    def shopping_needed(self, member_name: str, dish: str, items: str,
                         language: str = "english") -> Message:
        template = TRANSLATIONS["shopping_needed"].get(language, TRANSLATIONS["shopping_needed"]["english"])
        content = template.format(dish=dish, items=items)
        return self.send(MessageType.SHOPPING, member_name, content,
                        language=language, dish=dish)

    def assign_slot(self, member_name: str, slot: str, language: str = "english") -> Message:
        template = TRANSLATIONS["assign_slot"].get(language, TRANSLATIONS["assign_slot"]["english"])
        slot_local = SLOT_TRANSLATIONS.get(slot, {}).get(language, slot)
        content = template.format(name=member_name, slot=slot_local)
        return self.send(MessageType.SLOT_ASSIGN, member_name, content,
                        language=language, slot=slot)

    def rate_meal(self, member_name: str, dish: str, rating: int = 5,
                  language: str = "english") -> Message:
        template = TRANSLATIONS["rate_meal"].get(language, TRANSLATIONS["rate_meal"]["english"])
        content = template.format(dish=dish) + "⭐" * min(rating, 5)
        return self.send(MessageType.RATING, member_name, content,
                        language=language, dish=dish)

    def get_chat(self, language: str = "english", member_filter: Optional[str] = None,
                 msg_type_filter: Optional[MessageType] = None) -> List[str]:
        msgs = self.messages
        if member_filter:
            msgs = [m for m in msgs if m.sender == member_filter]
        if msg_type_filter:
            msgs = [m for m in msgs if m.msg_type == msg_type_filter]
        return [m.to_chat_line(language) for m in msgs]

    def get_chat_by_language(self, user_languages: Dict[str, str]) -> Dict[str, List[str]]:
        result = {}
        for user_id, lang in user_languages.items():
            member = next((m for m in self.members if m["user_id"] == user_id), None)
            if member:
                result[member["name"]] = self.get_chat(language=lang)
        return result

    def display_all(self, language: str = "english") -> str:
        lines = [f"📱 {self.household_name} — {len(self.members)} members"]
        lines.append(f"{'='*45}")
        for m in self.members:
            langs = ", ".join(m["languages"])
            lines.append(f"  👤 {m['name']} ({langs})")
        lines.append(f"{'='*45}")
        lines.extend(self.get_chat(language))
        lines.append(f"{'='*45}")
        lines.append(f"💬 {len(self.messages)} messages")
        return "\n".join(lines)


def demo_messaging():
    chat = MealDramaMessenger("Prateek's Kitchen", "english")

    chat.add_member("Prateek", "user_1", ["english", "hindi"])
    chat.add_member("Mom", "user_2", ["hindi", "punjabi"])
    chat.add_member("Alex", "user_3", ["english", "tamil"])
    chat.add_member("Priya", "user_4", ["telugu", "english"])

    chat.suggest_meal("Prateek", "dosa", "breakfast")
    chat.assign_meal("Mom", "dal-makhani", "dinner", "hindi")
    chat.assign_slot("Alex", "lunch", "tamil")

    voice = VoiceMessage.sample_for_dish("dal-makhani", "hindi", "north_indian")
    chat.meal_ready("Mom", "Dal Makhani", "hindi", voice)

    voice2 = VoiceMessage.sample_for_dish("dosa", "tamil", "south_indian")
    chat.meal_ready("Alex", "Dosa", "tamil", voice2)

    chat.rate_meal("Priya", "Dal Makhani", 5, "telugu")
    chat.shopping_needed("Prateek", "Biriyani", "Chicken, Rice, Spices, Yogurt")
    chat.split_expense("Alex", "Groceries", 1240.00, "tamil")

    print(chat.display_all("english"))
    print("\n\n--- Same chat in Hindi ---\n")
    print(chat.display_all("hindi"))

    return chat


if __name__ == "__main__":
    demo_messaging()
