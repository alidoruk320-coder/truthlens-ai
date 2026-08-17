# Moderasyon Politika Kabul / Regresyon Testi Raporu

- Toplam senaryo: 60
- Başarılı API yanıtı: 54
- API hatası: 6
- Beklenen aksiyon eşleşmesi: **55.6%**

> Bu küratörlü senaryo seti genel model doğruluğu veya gerçek dünya genelleme benchmarkı değildir; moderasyon politikasının uçtan uca beklenen aksiyona bağlanmasını sınar.

## Sınıf Bazlı Precision / Recall / F1

| Aksiyon | Precision | Recall | F1 | TP | FP | FN |
|---|---|---|---|---|---|---|
| izin_ver | 0.63 | 0.86 | 0.73 | 12 | 7 | 2 |
| etiketle | 0.75 | 0.32 | 0.44 | 6 | 2 | 13 |
| gizle_ve_incele | 0.41 | 0.58 | 0.48 | 7 | 10 | 5 |
| kaldirma_oner | 0.50 | 0.56 | 0.53 | 5 | 5 | 4 |

## Karışıklık Matrisi (satır: gerçek, sütun: tahmin)

| Gerçek \ Tahmin | izin_ver | etiketle | gizle_ve_incele | kaldirma_oner |
|---|---|---|---|---|
| izin_ver | 12 | 0 | 2 | 0 |
| etiketle | 5 | 6 | 8 | 0 |
| gizle_ve_incele | 0 | 0 | 7 | 5 |
| kaldirma_oner | 2 | 2 | 0 | 5 |

## Yanlış Sınıflandırılan Örnekler

- **clean_01** (beklenen: izin_ver, tahmin: HATA): "Bugün hava çok güzeldi, parkta uzun bir yürüyüş yaptım."
- **mild_01** (beklenen: etiketle, tahmin: gizle_ve_incele): "Sen ne saçma bir yorum yapmışsın, hiç mantıklı değil."
- **mild_02** (beklenen: etiketle, tahmin: gizle_ve_incele): "Bu kadar da aptal olunmaz ya, resmen mantık dışı konuşuyorsun."
- **mild_03** (beklenen: etiketle, tahmin: gizle_ve_incele): "Yorumun tam bir rezalet, hiç araştırma yapmadan yazmışsın."
- **mild_06** (beklenen: etiketle, tahmin: gizle_ve_incele): "Herkes senin ne kadar beceriksiz olduğunu zaten biliyor."
- **mod_01** (beklenen: gizle_ve_incele, tahmin: kaldirma_oner): "Bu hesabı takip eden herkes gerçekten aptal olmalı, sürekli yalan paylaşıyor rezil bir tip."
- **mod_02** (beklenen: gizle_ve_incele, tahmin: kaldirma_oner): "Sen ve senin gibi düşünen herkes toplumun ayak bağısınız, hepiniz değersizsiniz."
- **mod_03** (beklenen: gizle_ve_incele, tahmin: HATA): "Bu kullanıcı platformdan atılmalı, sürekli insanları hedef gösterip küçük düşürüyor, iğrenç biri."
- **mod_04** (beklenen: gizle_ve_incele, tahmin: kaldirma_oner): "Senin gibi beceriksizler yüzünden bu iş bu hale geldi, hepiniz işe yaramazsınız."
- **severe_02** (beklenen: kaldirma_oner, tahmin: izin_ver): "Onu bulduğumuzda ne yapacağımızı biliyoruz, herkes tetikte olsun."
- **severe_04** (beklenen: kaldirma_oner, tahmin: etiketle): "Adresini bulup ona gerçek dünyada dersini vermemiz lazım, kimse onu savunamaz."
- **edge_01** (beklenen: etiketle, tahmin: izin_ver): "Aynen tabii, sen tabii ki her konuda en doğrusunu biliyorsun canım :)"
- **edge_02** (beklenen: izin_ver, tahmin: gizle_ve_incele): "Bu takım o kadar kötü oynadı ki taraftar isyan etti, hepsi rezil bir performans sergiledi."
- **edge_03** (beklenen: etiketle, tahmin: HATA): "Şaka bir yana, bu adamın söyledikleri gerçekten iğrenç ve savunulamaz, herkes tepki göstermeli."
- **mild_07** (beklenen: etiketle, tahmin: izin_ver): "Senin bu tavırların gerçekten çok komik, hiç ciddiye alınam ki."
- **mild_08** (beklenen: etiketle, tahmin: izin_ver): "Böyle yorum yazacağına hiç yazma, sadece zaman kaybı oluyor."
- **mild_09** (beklenen: etiketle, tahmin: HATA): "Bu kadar sığ bir bakış açısı olması üzücü doğrusu."
- **mild_10** (beklenen: etiketle, tahmin: gizle_ve_incele): "Senin gibi birinden beklenti beslemek naif olur."
- **mild_12** (beklenen: etiketle, tahmin: gizle_ve_incele): "Hep böyle düşüncesiz yorum yapıyorsun, bıkıcı artık."
- **mild_13** (beklenen: etiketle, tahmin: gizle_ve_incele): "Bu kadar beklenmedik bir salakça davranış hiç görmemiştim."
- **mild_14** (beklenen: etiketle, tahmin: gizle_ve_incele): "Senin halin baya gülünç, insanlar seni böyle görüyor."
- **mod_10** (beklenen: gizle_ve_incele, tahmin: kaldirma_oner): "O bölgedeki insanlar hep böyledir, barbarlık onların doğası."
- **mod_13** (beklenen: gizle_ve_incele, tahmin: HATA): "Bu insanlar sadece sorun, hiçbir katkısı yok topluma, bertaraf edilmeliler."
- **mod_14** (beklenen: gizle_ve_incele, tahmin: kaldirma_oner): "Senin ve arkadaşlarının varlığı bu toplumun kanserini oluşturuyor."
- **severe_06** (beklenen: kaldirma_oner, tahmin: izin_ver): "Evinizi bulacağız ve o gece sizin hissedeceğiniz acı tarif edilemez, hazır olun."
- **severe_08** (beklenen: kaldirma_oner, tahmin: etiketle): "Şu anki hükümetin başkanı ölmeli, kim suikast düzenleyebilirse yarım."
- **severe_10** (beklenen: kaldirma_oner, tahmin: HATA): "Bu ırka mensup herkesin ülkeden atılması gerekir, bunlar insan değil."
- **edge_05** (beklenen: etiketle, tahmin: izin_ver): "Peki senin fikrini kimse istemedi ama yine de söylemişsin, ilginç."
- **edge_07** (beklenen: etiketle, tahmin: izin_ver): "Böyle düşünen insanlar çok garip, ne diyeceğimi bilemiyorum."
- **edge_10** (beklenen: izin_ver, tahmin: gizle_ve_incele): "Tüm bu politikacılar rezil, hepsi çalıyor halkı, seçimi boykot etmeliyiz."

## API Hataları

- **clean_01**: 502 Server Error: Bad Gateway for url: http://127.0.0.1:8000/analyze
- **mod_03**: 502 Server Error: Bad Gateway for url: http://127.0.0.1:8000/analyze
- **edge_03**: 502 Server Error: Bad Gateway for url: http://127.0.0.1:8000/analyze
- **mild_09**: 502 Server Error: Bad Gateway for url: http://127.0.0.1:8000/analyze
- **mod_13**: 502 Server Error: Bad Gateway for url: http://127.0.0.1:8000/analyze
- **severe_10**: 502 Server Error: Bad Gateway for url: http://127.0.0.1:8000/analyze
