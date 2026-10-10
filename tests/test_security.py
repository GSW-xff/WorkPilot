import unittest

from workpilot.security import idempotency_key, parameter_hash, redact


class SecurityTest(unittest.TestCase):
    def test_parameter_hash_is_order_independent(self) -> None:
        self.assertEqual(parameter_hash({"a": 1, "b": 2}), parameter_hash({"b": 2, "a": 1}))

    def test_idempotency_key_is_tenant_scoped(self) -> None:
        first = idempotency_key("tenant-a", "task", "step", "mail.send", {"to": ["a"]})
        second = idempotency_key("tenant-b", "task", "step", "mail.send", {"to": ["a"]})
        self.assertNotEqual(first, second)

    def test_redaction_handles_nested_credentials_and_bearer_tokens(self) -> None:
        value = {
            "token": "secret-value",
            "nested": [{"password": "pass"}],
            "message": "Authorization: Bearer abc.def-123",
        }
        sanitized = redact(value)
        self.assertEqual("[REDACTED]", sanitized["token"])
        self.assertEqual("[REDACTED]", sanitized["nested"][0]["password"])
        self.assertNotIn("abc.def-123", sanitized["message"])

    def test_redaction_handles_provider_key_shapes_in_free_text(self) -> None:
        sanitized = redact("sk-1234567890abcdefghijkl ghp_123456789012345678901234567890")
        self.assertNotIn("sk-", sanitized)
        self.assertNotIn("ghp_", sanitized)


if __name__ == "__main__":
    unittest.main()
