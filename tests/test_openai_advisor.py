from __future__ import annotations

import unittest

from arbiter.llm.openai_advisor import OpenAITradeAdvisor, TradeHypothesisRequest


class OpenAIAdvisorTests(unittest.TestCase):
    def test_build_input_includes_trade_fields(self) -> None:
        request = TradeHypothesisRequest(
            symbol="XLE",
            side="buy",
            thesis="Energy strength",
            price_context="XLE outperforming SPY",
            position_size="$500",
            risk_notes="Stop on trend break",
        )

        text = OpenAITradeAdvisor._build_input(request)

        self.assertIn("Symbol: XLE", text)
        self.assertIn("Side: buy", text)
        self.assertIn("Thesis: Energy strength", text)

    def test_extract_text_prefers_output_text(self) -> None:
        payload = {"output_text": "lean-support"}
        self.assertEqual(OpenAITradeAdvisor._extract_text(payload), "lean-support")

    def test_extract_text_falls_back_to_output_content(self) -> None:
        payload = {
            "output": [
                {
                    "content": [
                        {"type": "output_text", "text": "reject"},
                    ]
                }
            ]
        }
        self.assertEqual(OpenAITradeAdvisor._extract_text(payload), "reject")


if __name__ == "__main__":
    unittest.main()
