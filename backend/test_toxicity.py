import unittest

from main import AnalysisResponse, ToxicityAnalysis, build_demo_feed, summarize_demo_feed


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

    def test_demo_feed_has_posts_and_summary(self):
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


if __name__ == "__main__":
    unittest.main()
