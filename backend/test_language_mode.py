import json
import unittest

import main


class LanguageModeTests(unittest.TestCase):
    def test_analysis_cache_is_separated_by_language(self):
        content = "The claim to verify"
        self.assertNotEqual(
            main.analysis_cache_key(content, language="tr"),
            main.analysis_cache_key(content, language="en"),
        )

    def test_claim_extraction_requests_english_but_keeps_search_query_original(self):
        original_call_llm = main.call_llm
        prompts = []

        def fake_call_llm(messages, temperature=0.2):
            prompts.append(messages[0]["content"])
            return json.dumps({"has_claim": True, "claim": "A claim", "claims": ["A claim"], "search_query": "özgün dilde arama"})

        main.call_llm = fake_call_llm
        try:
            result = main.extract_claim_with_gemini("Türkçe içerik", "en")
        finally:
            main.call_llm = original_call_llm

        self.assertEqual(result["search_query"], "özgün dilde arama")
        self.assertIn("Write the claim and claims in English", prompts[0])
        self.assertIn("Keep search_query in the input's original language", prompts[0])

    def test_final_reasoning_requests_english_user_facing_text(self):
        original_call_llm = main.call_llm
        prompts = []

        def fake_call_llm(messages, temperature=0.2):
            prompts.append(messages[0]["content"])
            return json.dumps({"truthfulness": "Misleading", "reason": "The evidence does not support the claim."})

        main.call_llm = fake_call_llm
        try:
            main.final_reasoning_with_gemini("A claim", "The claim", [], "en")
        finally:
            main.call_llm = original_call_llm

        self.assertIn("Write every user-facing text value in English", prompts[0])

    def test_moderation_action_code_is_stable_with_english_copy(self):
        toxicity = main.ToxicityAnalysis(
            insult=0,
            bullying=0,
            hate_speech=0,
            targeted_person_or_group="General",
            risk_level="Low",
            context_note="",
        )
        decision = main.decide_moderation_action(toxicity, "en")
        self.assertEqual(decision.action, "izin_ver")
        self.assertEqual(decision.action_label, "Content allowed")
        self.assertEqual(decision.reason, "No significant toxicity signals were detected.")

    def test_english_truth_verdict_can_earn_verification_badge(self):
        result = main.AnalysisResponse(
            score=95,
            manipulation=0,
            clickbait=0,
            result="True",
            explanation="Supported by evidence.",
            score_breakdown="Strong evidence.",
            validity="Valid",
            emotion="Neutral",
            time_validity="Current",
            polarization_risk=0,
            echo_chamber="Low",
            ai_rewrite="A neutral version.",
            social_risk_summary="Low risk.",
            claims=["A claim"],
            context="Context.",
            sources=[],
            supporting_sources=[],
            contradicting_sources=[],
            toxicity=main.ToxicityAnalysis(
                targeted_person_or_group="General",
                risk_level="Low",
                context_note="",
            ),
            moderation=main.decide_moderation_action(
                main.ToxicityAnalysis(targeted_person_or_group="General", risk_level="Low", context_note=""),
                "en",
            ),
        )
        badge = main.compute_truthlens_verification(result, language="en")
        self.assertTrue(badge.verified, badge.reasons)
        self.assertEqual(badge.short_label, "Evidence review complete")


if __name__ == "__main__":
    unittest.main()