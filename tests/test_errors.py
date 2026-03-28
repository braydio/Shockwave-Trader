from __future__ import annotations

import unittest

from arbiter.lib.errors import ConfigError, ErrorType, validate_required_config


class ErrorUtilityTests(unittest.TestCase):
    def test_validate_required_config_raises_for_missing_values(self) -> None:
        with self.assertRaises(ConfigError) as ctx:
            validate_required_config({"PUBLIC_API_ACCESS_TOKEN": ""}, ["PUBLIC_API_ACCESS_TOKEN"])

        self.assertEqual(ctx.exception.error_type, ErrorType.CONFIG_MISSING)
        self.assertIn("PUBLIC_API_ACCESS_TOKEN", ctx.exception.details["config_key"])


if __name__ == "__main__":
    unittest.main()
