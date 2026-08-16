"""
Kullanım (kendi ortamınızda, API sunucunuz ayaktayken):

    python3 main.py                     # ayrı terminalde sunucuyu başlatın
    python3 evaluate_moderation.py      # bu scripti çalıştırın

Çıktı: eval_report.md dosyası -> küratörlü moderasyon politika kabul/regresyon testi
raporu üretir. Bu sonuç genel model doğruluğu değildir.

Bu script main.py'yi import ETMEZ; gerçek HTTP isteği atar. Böylece
ölçtüğünüz şey gerçekten uçtan uca çalışan sisteminizdir (LLM dahil),
sadece kod okuması değil.
"""
import json
import time
import sys

import requests

API_BASE = "http://127.0.0.1:8000"
DATASET_PATH = "eval_dataset.json"
REPORT_PATH = "eval_report.md"

ACTIONS = ["izin_ver", "etiketle", "gizle_ve_incele", "kaldirma_oner"]


def load_dataset():
    with open(DATASET_PATH, "r", encoding="utf-8") as f:
        return json.load(f)["items"]


def call_analyze(text: str) -> str:
    resp = requests.post(f"{API_BASE}/analyze", json={"content": text}, timeout=60)
    resp.raise_for_status()
    data = resp.json()
    return data.get("moderation", {}).get("action", "izin_ver")


def confusion_matrix(y_true, y_pred, labels):
    matrix = {t: {p: 0 for p in labels} for t in labels}
    for t, p in zip(y_true, y_pred):
        if t not in matrix or p not in labels:
            continue
        matrix[t][p] += 1
    return matrix


def precision_recall_f1(matrix, labels):
    rows = []
    for label in labels:
        tp = matrix[label][label]
        fp = sum(matrix[other][label] for other in labels if other != label)
        fn = sum(matrix[label][other] for other in labels if other != label)
        precision = tp / (tp + fp) if (tp + fp) else 0.0
        recall = tp / (tp + fn) if (tp + fn) else 0.0
        f1 = 2 * precision * recall / (precision + recall) if (precision + recall) else 0.0
        rows.append((label, precision, recall, f1, tp, fp, fn))
    return rows


def main():
    items = load_dataset()
    y_true, y_pred, mismatches, errors = [], [], [], []

    print(f"{len(items)} örnek üzerinde /analyze çağrılıyor...")
    for i, item in enumerate(items, 1):
        try:
            predicted = call_analyze(item["text"])
        except Exception as e:
            errors.append((item["id"], str(e)))
            print(f"  [{i}/{len(items)}] HATA ({item['id']}): {e}")
            mismatches.append((item["id"], item["text"], item["expected_action"], "HATA"))
            time.sleep(0.3)
            continue
        y_true.append(item["expected_action"])
        y_pred.append(predicted)
        match = "OK" if predicted == item["expected_action"] else "FARK"
        print(f"  [{i}/{len(items)}] {item['id']:12s} beklenen={item['expected_action']:16s} tahmin={predicted:16s} {match}")
        if match == "FARK":
            mismatches.append((item["id"], item["text"], item["expected_action"], predicted))
        time.sleep(0.3)  # API'yi yormamak için

    matrix = confusion_matrix(y_true, y_pred, ACTIONS)
    rows = precision_recall_f1(matrix, ACTIONS)
    agreement = sum(1 for t, p in zip(y_true, y_pred) if t == p) / len(y_true) if y_true else 0.0

    with open(REPORT_PATH, "w", encoding="utf-8") as f:
        f.write("# Moderasyon Politika Kabul / Regresyon Testi Raporu\n\n")
        f.write(f"- Toplam senaryo: {len(items)}\n")
        f.write(f"- Başarılı API yanıtı: {len(y_true)}\n")
        f.write(f"- API hatası: {len(errors)}\n")
        f.write(f"- Beklenen aksiyon eşleşmesi: **{agreement:.1%}**\n\n")
        f.write("> Bu küratörlü senaryo seti genel model doğruluğu veya gerçek dünya genelleme benchmarkı değildir; moderasyon politikasının uçtan uca beklenen aksiyona bağlanmasını sınar.\n\n")
        f.write("## Sınıf Bazlı Precision / Recall / F1\n\n")
        f.write("| Aksiyon | Precision | Recall | F1 | TP | FP | FN |\n")
        f.write("|---|---|---|---|---|---|---|\n")
        for label, p, r, f1, tp, fp, fn in rows:
            f.write(f"| {label} | {p:.2f} | {r:.2f} | {f1:.2f} | {tp} | {fp} | {fn} |\n")
        f.write("\n## Karışıklık Matrisi (satır: gerçek, sütun: tahmin)\n\n")
        f.write("| Gerçek \\ Tahmin | " + " | ".join(ACTIONS) + " |\n")
        f.write("|---" * (len(ACTIONS) + 1) + "|\n")
        for t in ACTIONS:
            f.write(f"| {t} | " + " | ".join(str(matrix[t][p]) for p in ACTIONS) + " |\n")
        f.write("\n## Yanlış Sınıflandırılan Örnekler\n\n")
        if mismatches:
            for mid, text, expected, predicted in mismatches:
                f.write(f"- **{mid}** (beklenen: {expected}, tahmin: {predicted}): \"{text}\"\n")
        else:
            f.write("Yok — tüm örnekler beklenen aksiyonla eşleşti.\n")

        f.write("\n## API Hataları\n\n")
        if errors:
            for error_id, error_text in errors:
                f.write(f"- **{error_id}**: {error_text}\n")
        else:
            f.write("Yok.\n")

    print(f"\nRapor yazıldı: {REPORT_PATH}")
    print(f"Politika aksiyonu eşleşmesi: {agreement:.1%}")
    print(f"API hatası: {len(errors)}")


if __name__ == "__main__":
    main()
