import json
import sys
sys.path.insert(0, '/home/ubuntu/upload')
import main

calls = []

def fake_llm(messages, temperature=0.2):
    calls.append(messages[0]['content'])
    if len(calls) == 1:
        return json.dumps({
            'has_claim': True,
            'claim': 'Günde 8 bardak su içmek tüm hastalıkları önler.',
            'claims': ['Günde 8 bardak su içmek tüm hastalıkları önler.'],
            'search_query': 'günde 8 bardak su tüm hastalıkları önler bilimsel kanıt'
        })
    return json.dumps({
        'truthfulness': 'Yanıltıcı', 'confidence': 0.95,
        'reason': 'Kaynaklar tüm hastalıkları önlediği iddiasını desteklemiyor.',
        'supporting_urls': [], 'contradicting_urls': ['https://example.org/water'],
        'score': 28, 'manipulation': 20, 'clickbait': 40, 'emotion': 'Endişe',
        'polarization_risk': 5, 'echo_chamber': 'Düşük', 'ai_rewrite': 'Su tüketimi önemlidir ancak tüm hastalıkları önlediği söylenemez.',
        'social_risk_summary': 'Sağlık iddiası kanıtla paylaşılmalı.', 'validity': 'Belirsiz',
        'time_validity': 'Güncel kaynak kontrolü gerekir.', 'context': 'Bilimsel kanıt gerekir.',
        'explanation': 'Yanıltıcı.', 'score_breakdown': 'Kanıt çelişkili.'
    })

main.call_llm = fake_llm
main.search_with_tavily = lambda query, max_results=5: [
    {'title': 'Su tüketimi ve sağlık', 'url': 'https://example.org/water', 'content': 'Yeterli su sağlık için yararlı olabilir; tüm hastalıkları önlediği gösterilmemiştir.'}
]
main.TOXICITY_SERVICE.predict = lambda text: {'available': True, 'label': 'notoxic', 'confidence': 0.9976, 'toxic_probability': 0.0024}

result = main.run_analysis('Günde 8 bardak su içmek tüm hastalıkları önler. hibrit-test-2026')
assert len(calls) == 2, len(calls)
assert result.toxicity_label == 'notoxic'
assert abs(result.toxicity_confidence - 0.9976) < 1e-6
assert result.claim
assert result.truthfulness == 'Yanıltıcı'
assert result.evidence and result.evidence[0]['relation'] == 'contradicts'
print('HYBRID_PIPELINE_OK', json.dumps({'gemini_calls': len(calls), 'toxicity': result.toxicity_label, 'claim': result.claim, 'truthfulness': result.truthfulness, 'evidence_count': len(result.evidence)}, ensure_ascii=False))
