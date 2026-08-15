# Moderasyon Pipeline Değerlendirme Raporu

- Toplam örnek: 26
- Genel doğruluk (accuracy): **46.2%**

## Sınıf Bazlı Precision / Recall / F1

| Aksiyon | Precision | Recall | F1 | TP | FP | FN |
|---|---|---|---|---|---|---|
| izin_ver | 0.75 | 0.86 | 0.80 | 6 | 2 | 1 |
| etiketle | 1.00 | 0.11 | 0.20 | 1 | 0 | 8 |
| gizle_ve_incele | 0.25 | 0.33 | 0.29 | 2 | 6 | 4 |
| kaldirma_oner | 0.33 | 0.75 | 0.46 | 3 | 6 | 1 |

## Karışıklık Matrisi (satır: gerçek, sütun: tahmin)

| Gerçek \ Tahmin | izin_ver | etiketle | gizle_ve_incele | kaldirma_oner |
|---|---|---|---|---|
| izin_ver | 6 | 0 | 1 | 0 |
| etiketle | 1 | 1 | 5 | 2 |
| gizle_ve_incele | 0 | 0 | 2 | 4 |
| kaldirma_oner | 1 | 0 | 0 | 3 |

## Yanlış Sınıflandırılan Örnekler

- **mild_01** (beklenen: etiketle, tahmin: gizle_ve_incele): "Sen ne saçma bir yorum yapmışsın, hiç mantıklı değil."
- **mild_02** (beklenen: etiketle, tahmin: kaldirma_oner): "Bu kadar da aptal olunmaz ya, resmen mantık dışı konuşuyorsun."
- **mild_03** (beklenen: etiketle, tahmin: gizle_ve_incele): "Yorumun tam bir rezalet, hiç araştırma yapmadan yazmışsın."
- **mild_04** (beklenen: etiketle, tahmin: gizle_ve_incele): "Sürekli aynı saçmalığı tekrarlıyorsun, biraz susmayı öğren."
- **mild_05** (beklenen: etiketle, tahmin: gizle_ve_incele): "Bu paylaşımı yapan kişi gerçekten çok cahil görünüyor."
- **mild_06** (beklenen: etiketle, tahmin: kaldirma_oner): "Herkes senin ne kadar beceriksiz olduğunu zaten biliyor."
- **mod_01** (beklenen: gizle_ve_incele, tahmin: kaldirma_oner): "Bu hesabı takip eden herkes gerçekten aptal olmalı, sürekli yalan paylaşıyor rezil bir tip."
- **mod_02** (beklenen: gizle_ve_incele, tahmin: kaldirma_oner): "Sen ve senin gibi düşünen herkes toplumun ayak bağısınız, hepiniz değersizsiniz."
- **mod_04** (beklenen: gizle_ve_incele, tahmin: kaldirma_oner): "Senin gibi beceriksizler yüzünden bu iş bu hale geldi, hepiniz işe yaramazsınız."
- **mod_06** (beklenen: gizle_ve_incele, tahmin: kaldirma_oner): "Bu yaştan sonra hâlâ bunu anlamıyorsan gerçekten zekan yetersiz demektir."
- **severe_02** (beklenen: kaldirma_oner, tahmin: izin_ver): "Onu bulduğumuzda ne yapacağımızı biliyoruz, herkes tetikte olsun."
- **edge_01** (beklenen: etiketle, tahmin: izin_ver): "Aynen tabii, sen tabii ki her konuda en doğrusunu biliyorsun canım :)"
- **edge_02** (beklenen: izin_ver, tahmin: gizle_ve_incele): "Bu takım o kadar kötü oynadı ki taraftar isyan etti, hepsi rezil bir performans sergiledi."
- **edge_03** (beklenen: etiketle, tahmin: gizle_ve_incele): "Şaka bir yana, bu adamın söyledikleri gerçekten iğrenç ve savunulamaz, herkes tepki göstermeli."
