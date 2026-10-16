import unittest

from backend.app import (
    MAX_MESSAGE_LENGTH,
    MAX_USERNAME_LENGTH,
    validate_message_text,
    validate_room_id,
    validate_username,
)


class ValidationTests(unittest.TestCase):
    def test_accepts_room_name_boundaries(self):
        self.assertEqual(validate_room_id("team-chat_2"), "team-chat_2")
        self.assertEqual(validate_room_id("a" * 64), "a" * 64)

    def test_rejects_invalid_room_names(self):
        for room_id in ("", "has spaces", "slashes/are-invalid", "a" * 65, None):
            with self.subTest(room_id=room_id):
                with self.assertRaises(ValueError):
                    validate_room_id(room_id)

    def test_trims_and_limits_display_names(self):
        self.assertEqual(validate_username("  Ada  "), "Ada")
        self.assertEqual(validate_username("a" * MAX_USERNAME_LENGTH), "a" * MAX_USERNAME_LENGTH)
        with self.assertRaises(ValueError):
            validate_username("a" * (MAX_USERNAME_LENGTH + 1))

    def test_trims_and_limits_messages(self):
        self.assertEqual(validate_message_text("  Hello  "), "Hello")
        self.assertEqual(validate_message_text("x" * MAX_MESSAGE_LENGTH), "x" * MAX_MESSAGE_LENGTH)
        with self.assertRaises(ValueError):
            validate_message_text("x" * (MAX_MESSAGE_LENGTH + 1))
        with self.assertRaises(ValueError):
            validate_message_text("   ")


if __name__ == "__main__":
    unittest.main()
