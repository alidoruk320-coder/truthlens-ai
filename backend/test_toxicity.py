import unittest
import json

from main import AnalysisResponse, ToxicityAnalysis, ModerationDecision, decide_moderation_action


class ToxicityAnalysisTest(unittest.TestCase):
    def test_analysis_response_includes_toxicity_object(self):
        result = AnalysisResponse(
            score=77,
            manipulation=42,
            clickbait=30,
            result="Kısmen doğru",
            explanation="Açıklama",
            score_breakdown="Kısa açıklama",
            validity="Belirsiz",
            emotion="Öfke",
            time_validity="İçerik güncel görünüyor fakat bağlam eksik.",
            polarization_risk=35,
            echo_chamber="Tek görüşlü akış riski orta düzeyde.",
            ai_rewrite="Daha tarafsız bir versiyon önerilir.",
            social_risk_summary="Toplumsal etkisi sınırda.",
            claims=["İddia 1"],
            context="Bağlam var.",
            sources=[],
            supporting_sources=[],
            contradicting_sources=[],
            toxicity=ToxicityAnalysis(
                insult=87,
                bullying=72,
                hate_speech=14,
                targeted_person_or_group="Belirli bir kişi",
                risk_level="Yüksek",
                context_note="Kişiye yönelik hakaret içermektedir.",
            ),
        )

        self.assertEqual(result.toxicity.insult, 87)
        self.assertEqual(result.toxicity.risk_level, "Yüksek")
        self.assertEqual(result.toxicity.targeted_person_or_group, "Belirli bir kişi")
        # moderation alanı verilmese bile default_factory ile üretilmeli (geriye dönük uyumluluk)
        self.assertIsInstance(result.moderation, ModerationDecision)
        self.assertEqual(result.moderation.action, "izin_ver")

    def test_run_analysis_falls_back_when_llm_is_unavailable(self):
        import main

        original = main.call_llm
        main.call_llm = lambda *args, **kwargs: (_ for _ in ()).throw(RuntimeError("Google Gemini hatası"))
        try:
            result = main.run_analysis("Bu içerik analize ediliyor.")
            self.assertIsInstance(result, AnalysisResponse)
            self.assertEqual(result.moderation.action, "izin_ver")
            self.assertIn("beklemede", result.explanation.lower())
        finally:
            main.call_llm = original

    def test_run_analysis_returns_explicit_fallback_without_fake_toxicity_scores(self):
        import main

        original = main.call_llm
        original_predict = main.TOXICITY_SERVICE.predict
        original_insult = main.INSULT_SERVICE.predict
        original_bullying = main.BULLYING_SERVICE.predict
        original_hate = main.HATE_SERVICE.predict
        unavailable = lambda text: {"available": False, "engine": "fallback", "raw": {}}
        main.TOXICITY_SERVICE.predict = lambda text: {"available": False, "label": "notoxic", "confidence": 0.0}
        main.INSULT_SERVICE.predict = unavailable
        main.BULLYING_SERVICE.predict = unavailable
        main.HATE_SERVICE.predict = unavailable
        main.call_llm = lambda *args, **kwargs: json.dumps({
            "score": 50,
            "manipulation": 0,
            "clickbait": 0,
            "result": "Kanıt yetersiz",
            "explanation": "test",
            "score_breakdown": "test",
            "validity": "Belirsiz",
            "emotion": "Nötr",
            "time_validity": "test",
            "polarization_risk": 0,
            "echo_chamber": "test",
            "ai_rewrite": "test",
            "social_risk_summary": "test",
            "toxicity": {
                "insult": 0,
                "bullying": 0,
                "hate_speech": 0,
                "targeted_person_or_group": "Genel",
                "risk_level": "Düşük",
                "context_note": "test",
            },
            "claims": [],
            "context": "test",
            "sources": [],
            "supporting_sources": [],
            "contradicting_sources": [],
        })
        try:
            result = main.run_analysis("bu salak bile biri oldu")
            self.assertEqual(result.toxicity.insult, 0)
            self.assertEqual(result.toxicity.bullying, 0)
            self.assertEqual(result.toxicity.hate_speech, 0)
            self.assertIn("skor üretilmedi", result.toxicity.context_note.lower())
            self.assertEqual(result.toxicity_engine, "fallback")
            self.assertEqual(result.moderation.action, "izin_ver")
        finally:
            main.call_llm = original
            main.TOXICITY_SERVICE.predict = original_predict
            main.INSULT_SERVICE.predict = original_insult
            main.BULLYING_SERVICE.predict = original_bullying
            main.HATE_SERVICE.predict = original_hate

    def test_demo_feed_has_posts_and_summary(self):
        from main import build_demo_feed, summarize_demo_feed

        posts = build_demo_feed()
        self.assertGreater(len(posts), 2)
        self.assertIn("truthlens_score", posts[0])
        self.assertIn("emotion", posts[0])

        summary = summarize_demo_feed(posts)
        self.assertIn("top_emotion", summary)
        self.assertIn("risk_level", summary)

    def test_normalized_bluesky_post_includes_media_and_avatar(self):
        from main import normalize_bluesky_post

        fake_post = {
            "uri": "at://did/app.bsky.feed.post/123",
            "author": {
                "handle": "truthlensai.bsky.social",
                "avatar": "https://cdn.example.com/avatar.png",
            },
            "record": {
                "text": "Görsel içeriği olan bir paylaşım",
            },
            "embed": {
                "images": [
                    {"fullsize": "https://cdn.example.com/img1.jpg"},
                    {"fullsize": "https://cdn.example.com/img2.jpg"},
                ]
            },
            "reply_count": 3,
            "repost_count": 4,
            "like_count": 5,
        }

        normalized = normalize_bluesky_post(fake_post)
        self.assertIn("image_urls", normalized)
        self.assertEqual(len(normalized["image_urls"]), 2)
        self.assertTrue(normalized["image_urls"][0].startswith("http"))
        self.assertEqual(normalized["avatar"], "https://cdn.example.com/avatar.png")
        self.assertEqual(normalized["engagement"]["likes"], 5)


class ModerationDecisionTest(unittest.TestCase):
    """
    decide_moderation_action() deterministik karar motorunun sınır durumları.
    LLM çağrısı yapmaz -> ağ/API anahtarı olmadan da CI'da koşulabilir.
    """

    def _toxicity(self, insult=0, bullying=0, hate_speech=0, risk_level="Düşük"):
        return ToxicityAnalysis(
            insult=insult,
            bullying=bullying,
            hate_speech=hate_speech,
            risk_level=risk_level,
            targeted_person_or_group="Test",
            context_note="test",
        )

    def test_clean_content_is_allowed(self):
        decision = decide_moderation_action(self._toxicity())
        self.assertEqual(decision.action, "izin_ver")
        self.assertFalse(decision.requires_human_review)
        self.assertFalse(decision.appeal_eligible)

    def test_mild_signal_gets_labeled_not_removed(self):
        decision = decide_moderation_action(self._toxicity(insult=30))
        self.assertEqual(decision.action, "etiketle")

    def test_moderate_signal_requires_human_review(self):
        decision = decide_moderation_action(self._toxicity(hate_speech=45))
        self.assertEqual(decision.action, "gizle_ve_incele")
        self.assertTrue(decision.requires_human_review)
        self.assertTrue(decision.appeal_eligible)

    def test_severe_signal_never_auto_deletes(self):
        decision = decide_moderation_action(self._toxicity(hate_speech=90))
        self.assertEqual(decision.action, "kaldirma_oner")
        self.assertIn("oner", decision.action)  # "öner" -> insan onayı gerektirir, otomatik silme değil

    def test_decision_is_deterministic(self):
        sample = self._toxicity(insult=55, bullying=40, hate_speech=20, risk_level="Orta")
        results = {decide_moderation_action(sample).action for _ in range(50)}
        self.assertEqual(len(results), 1)

    def test_action_severity_is_monotonic_in_hate_speech(self):
        severity = {"izin_ver": 0, "etiketle": 1, "gizle_ve_incele": 2, "kaldirma_oner": 3}
        prev = -1
        for hs in range(0, 101, 5):
            decision = decide_moderation_action(self._toxicity(hate_speech=hs))
            current = severity[decision.action]
            self.assertGreaterEqual(current, prev, f"hate_speech={hs} aksiyonu geriletti")
            prev = current

    def test_targeted_group_dehumanization_is_severe(self):
        toxicity = ToxicityAnalysis(
            insult=25,
            bullying=15,
            hate_speech=68,
            targeted_person_or_group="Dini/Etnik Grup",
            risk_level="Yüksek",
            context_note="Dehumanization",
        )
        decision = decide_moderation_action(toxicity)
        self.assertEqual(decision.action, "kaldirma_oner")


if __name__ == "__main__":
    unittest.main()
