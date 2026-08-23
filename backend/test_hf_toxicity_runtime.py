import json
import main

loaded = main.TOXICITY_SERVICE.load_once()
outputs = []
for text in [
    "Bugün hava çok güzel.",
    "Sen tam bir aptalsın.",
    "Bu makale yapay zeka hakkında bilgi veriyor.",
    "Sana çok teşekkür ederim.",
]:
    prediction = main.TOXICITY_SERVICE.predict(text)
    outputs.append({"text": text, "prediction": prediction})

print(json.dumps({
    "loaded": loaded,
    "model_id": main.TOXICITY_MODEL_ID,
    "base_model": main.TOXICITY_BASE_MODEL,
    "device": main.TOXICITY_SERVICE.device,
    "error": main.TOXICITY_SERVICE.error,
    "outputs": outputs,
}, ensure_ascii=False))
