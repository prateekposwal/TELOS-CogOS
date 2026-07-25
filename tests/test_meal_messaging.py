"""Tests for MealDrama WhatsApp-style messaging."""

import pytest
from telos.adapters.meal_messaging import (
    MealDramaMessenger, MessageType, VoiceMessage,
    TRANSLATIONS, LANGUAGES, SLOT_TRANSLATIONS,
)


class TestMessengerBasics:
    def test_create_chat(self):
        chat = MealDramaMessenger("Test Kitchen", "english")
        assert chat.household_name == "Test Kitchen"
        assert len(chat.members) == 0
        assert len(chat.messages) == 0

    def test_add_member(self):
        chat = MealDramaMessenger("Test")
        chat.add_member("Alice", "user_a", ["english"])
        assert len(chat.members) == 1
        assert chat.members[0]["name"] == "Alice"

    def test_add_member_creates_system_message(self):
        chat = MealDramaMessenger("Test")
        chat.add_member("Bob", "user_b")
        msgs = chat.get_chat()
        assert any("Bob joined" in m for m in msgs)

    def test_remove_member(self):
        chat = MealDramaMessenger("Test")
        chat.add_member("Alice", "user_a")
        chat.add_member("Bob", "user_b")
        chat.remove_member("user_a")
        assert len(chat.members) == 1
        assert chat.members[0]["name"] == "Bob"

    def test_remove_member_creates_system_message(self):
        chat = MealDramaMessenger("Test")
        chat.add_member("Alice", "user_a")
        chat.remove_member("user_a")
        msgs = chat.get_chat()
        assert any("left" in m for m in msgs)


class TestMessageSending:
    def test_send_text(self):
        chat = MealDramaMessenger("Test")
        chat.add_member("Alice", "user_a")
        msg = chat.send(MessageType.TEXT, "Alice", "Hello everyone!")
        assert msg.content == "Hello everyone!"
        assert msg.sender == "Alice"

    def test_assign_meal(self):
        chat = MealDramaMessenger("Test")
        msg = chat.assign_meal("Alice", "pasta", "dinner")
        assert msg.msg_type == MessageType.MEAL_ASSIGN
        assert "pasta" in msg.content
        assert msg.dish == "pasta"
        assert msg.slot == "dinner"

    def test_assign_meal_hindi(self):
        chat = MealDramaMessenger("Test")
        msg = chat.assign_meal("Mom", "dal-makhani", "dinner", "hindi")
        assert "raat ka khana" in msg.content or "dal-makhani" in msg.content

    def test_suggest_meal(self):
        chat = MealDramaMessenger("Test")
        msg = chat.suggest_meal("Alice", "dosa", "breakfast")
        assert msg.msg_type == MessageType.MEAL_SUGGEST
        assert msg.dish == "dosa"

    def test_suggest_meal_tamil(self):
        chat = MealDramaMessenger("Test")
        msg = chat.suggest_meal("Priya", "idli", "breakfast", "tamil")
        assert msg.language == "tamil"

    def test_meal_ready(self):
        chat = MealDramaMessenger("Test")
        msg = chat.meal_ready("Alice", "Pizza")
        assert msg.msg_type == MessageType.MEAL_READY
        assert "ready" in msg.content.lower()

    def test_split_expense(self):
        chat = MealDramaMessenger("Test")
        chat.add_member("Alice", "a")
        chat.add_member("Bob", "b")
        msg = chat.split_expense("Alice", "Groceries", 1000)
        assert msg.msg_type == MessageType.EXPENSE
        assert "₹" in msg.content or "1000" in msg.content

    def test_shopping_needed(self):
        chat = MealDramaMessenger("Test")
        msg = chat.shopping_needed("Alice", "Biriyani", "Chicken, Rice")
        assert msg.msg_type == MessageType.SHOPPING
        assert "Chicken" in msg.content

    def test_assign_slot(self):
        chat = MealDramaMessenger("Test")
        msg = chat.assign_slot("Alice", "breakfast")
        assert msg.msg_type == MessageType.SLOT_ASSIGN

    def test_assign_slot_hindi(self):
        chat = MealDramaMessenger("Test")
        msg = chat.assign_slot("Mom", "lunch", "hindi")
        assert msg.language == "hindi"

    def test_rate_meal(self):
        chat = MealDramaMessenger("Test")
        msg = chat.rate_meal("Alice", "Dal Makhani", 4)
        assert msg.msg_type == MessageType.RATING
        assert "Dal Makhani" in msg.content

    def test_message_timestamp_auto(self):
        chat = MealDramaMessenger("Test")
        msg = chat.send(MessageType.TEXT, "Alice", "Hi")
        assert len(msg.timestamp) > 0

    def test_each_message_has_unique_type(self):
        chat = MealDramaMessenger("Test")
        chat.add_member("Alice", "a")
        chat.assign_meal("Alice", "pasta", "dinner")
        chat.suggest_meal("Alice", "pizza", "lunch")
        chat.meal_ready("Alice", "Pasta")
        chat.split_expense("Alice", "Food", 500)
        chat.assign_slot("Alice", "breakfast")
        chat.rate_meal("Alice", "Pasta", 5)
        chat.shopping_needed("Alice", "Pasta", "Tomato")
        types = {m.msg_type for m in chat.messages if m.msg_type != MessageType.SYSTEM}
        assert len(types) >= 6


class TestVoiceMessages:
    def test_create_voice_message(self):
        voice = VoiceMessage(
            text_hindi="Dal taiyar hai",
            text_english="Dal is ready",
            duration_sec=15,
            language="hindi",
        )
        assert voice.duration_sec == 15
        assert voice.display("hindi") == "🎤 Dal taiyar hai (15s)"
        assert voice.display("english") == "🎤 Dal is ready (15s)"

    def test_sample_for_dish(self):
        voice = VoiceMessage.sample_for_dish("dal-makhani", "hindi")
        assert voice.duration_sec > 0
        assert "makhani" in voice.text_hindi.lower()

    def test_sample_for_dish_tamil(self):
        voice = VoiceMessage.sample_for_dish("dosa", "tamil", "south_indian")
        assert voice.language == "tamil"
        assert voice.region == "south_indian"

    def test_send_voice_message(self):
        chat = MealDramaMessenger("Test")
        chat.add_member("Alice", "a")
        voice = VoiceMessage.sample_for_dish("dal-makhani", "hindi")
        msg = chat.send_voice("Alice", voice)
        assert msg.msg_type == MessageType.VOICE
        assert msg.voice is not None

    def test_meal_ready_with_voice(self):
        chat = MealDramaMessenger("Test")
        chat.add_member("Alice", "a")
        voice = VoiceMessage.sample_for_dish("dosa", "tamil")
        msg = chat.meal_ready("Alice", "Dosa", "tamil", voice)
        assert msg.voice is not None
        assert msg.language == "tamil"


class TestChatView:
    def test_chat_has_all_messages(self):
        chat = MealDramaMessenger("Test")
        chat.add_member("Alice", "a")
        chat.send(MessageType.TEXT, "Alice", "Hi")
        chat.send(MessageType.TEXT, "Alice", "Bye")
        lines = chat.get_chat()
        assert len(lines) == 3  # 1 system + 2 text

    def test_filter_by_member(self):
        chat = MealDramaMessenger("Test")
        chat.add_member("Alice", "a")
        chat.add_member("Bob", "b")
        chat.assign_meal("Alice", "pasta", "dinner")
        chat.assign_meal("Bob", "pizza", "lunch")
        alice_msgs = chat.get_chat(member_filter="Alice")
        assert len(alice_msgs) == 1  # meal assign only (system uses diff sender)
        for m in alice_msgs:
            assert "Bob" not in m

    def test_filter_by_type(self):
        chat = MealDramaMessenger("Test")
        chat.add_member("Alice", "a")
        chat.assign_meal("Alice", "pasta", "dinner")
        chat.meal_ready("Alice", "Pasta")
        assign_msgs = chat.get_chat(msg_type_filter=MessageType.MEAL_ASSIGN)
        assert len(assign_msgs) == 1
        assert "pasta" in assign_msgs[0].lower()

    def test_display_all_includes_members(self):
        chat = MealDramaMessenger("Test")
        chat.add_member("Alice", "a", ["english"])
        chat.add_member("Bob", "b", ["hindi"])
        display = chat.display_all()
        assert "Alice" in display
        assert "Bob" in display
        assert "english" in display
        assert "hindi" in display

    def test_multilingual_members(self):
        chat = MealDramaMessenger("Test")
        chat.add_member("Alice", "a", ["english", "hindi"])
        assert len(chat.members[0]["languages"]) == 2


class TestTranslations:
    def test_all_languages_have_translations(self):
        for key in TRANSLATIONS:
            assert "english" in TRANSLATIONS[key]
            for lang in LANGUAGES:
                assert lang in TRANSLATIONS[key], f"Missing {lang} for {key}"

    def test_all_slots_have_translations(self):
        for slot in ["breakfast", "lunch", "dinner", "snacks"]:
            assert slot in SLOT_TRANSLATIONS
            for lang in LANGUAGES:
                assert lang in SLOT_TRANSLATIONS[slot], f"Missing {lang} for {slot}"

    def test_translation_format_works(self):
        template = TRANSLATIONS["i_will_cook"]["hindi"]
        result = template.format(name="Mom", dish="dal-makhani", slot="dinner")
        assert "Mom" in result
        assert "dal-makhani" in result

    def test_voice_message_formats(self):
        voice = VoiceMessage(text_hindi="Namaste", text_english="Hello",
                            duration_sec=5, language="hindi")
        assert "🎤" in voice.display()
        assert "(5s)" in voice.display()


class TestEndToEnd:
    def test_household_messaging_flow(self):
        chat = MealDramaMessenger("Family Kitchen")

        chat.add_member("Mom", "m1", ["hindi", "punjabi"])
        chat.add_member("Dad", "m2", ["english", "hindi"])
        chat.add_member("Son", "m3", ["english", "tamil"])

        chat.assign_meal("Mom", "dal-makhani", "dinner", "hindi")
        chat.suggest_meal("Son", "dosa", "breakfast", "tamil")
        chat.assign_slot("Dad", "lunch")
        chat.split_expense("Dad", "Groceries", 1500)

        lines = chat.get_chat()
        assert len(lines) >= 6
        assert chat.display_all() is not None

    def test_different_languages_in_same_chat(self):
        chat = MealDramaMessenger("Test")
        chat.add_member("Alice", "a")
        chat.assign_meal("Alice", "pasta", "dinner", "english")
        chat.assign_meal("Alice", "pasta", "dinner", "hindi")
        chat.assign_meal("Alice", "pasta", "dinner", "tamil")

        english = chat.get_chat(language="english")
        assert len(english) == 4  # 1 system + 3 meals

    def test_chat_line_format(self):
        chat = MealDramaMessenger("Test")
        chat.add_member("Alice", "a")
        msg = chat.assign_meal("Alice", "pasta", "dinner")
        line = msg.to_chat_line()
        assert "Alice" in line
        assert "🍳" in line or "pasta" in line
        assert "[" in line and "]" in line  # timestamp
