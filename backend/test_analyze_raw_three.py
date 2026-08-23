import json
import requests

texts = [
    "Sen tam bir aptalsın.",
    "Bugün hava çok güzel.",
    "Kimse seninle konuşmak istemiyor, herkes senden nefret ediyor.",
]
results = []
for text in texts:
    response = requests.post("http://127.0.0.1:8000/analyze", json={"content": text}, timeout=120)
    payload = response.json()
    results.append({
        "text": text,
        "http_status": response.status_code,
        "toxicity": payload.get("toxicity"),
        "toxicity_models": payload.get("toxicity_models"),
        "toxicity_label": payload.get("toxicity_label"),
        "toxicity_confidence": payload.get("toxicity_confidence"),
        "toxicity_engine": payload.get("toxicity_engine"),
        "pipeline_status": payload.get("pipeline_status"),
    })
print(json.dumps(results, ensure_ascii=False, indent=2))
with open("raw_three_before.json", "w", encoding="utf-8") as f:
    json.dump(results, f, ensure_ascii=False, indent=2)
