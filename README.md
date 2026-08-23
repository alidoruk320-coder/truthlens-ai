# TruthLens AI

## Açıklanabilir Türkçe Sosyal Medya Güvenliği ve Doğrulama Platformu

TruthLens AI, sosyal medya içeriklerini **genel toksisite, hakaret, zorbaca davranış, nefret söylemi, görsel/OCR sinyalleri ve doğrulanabilir iddialar** bakımından analiz eden bir karar destek prototipidir. Projenin moderasyon ve insan-in-the-loop karar motoru **DiyalogKalkanı** olarak adlandırılır.

Sistem otomatik ve geri döndürülemez biçimde içerik silmez veya kullanıcı cezalandırmaz. Bunun yerine model çıktısını, kaynak zincirini, gerekçeyi ve risk seviyesini göstererek moderatöre **izin ver, etiketle, insan incelemesine al veya görünürlüğü sınırla** gibi geri döndürülebilir öneriler sunar.

> **Önemli:** Bu README, projedeki doğrudan Google Gemini mimarisine göre hazırlanmıştır. Aktif backend akışında NaraRouter, Cohere veya Laguna kullanılmaz. Eski deneysel scriptler bu mimarinin parçası değildir.

---

## 1. Proje nasıl çalışır?

TruthLens analiz akışı aşağıdaki sırayla çalışır:

```
Kullanıcı metni / URL / görsel
          │
          ├── Genel BERT+LoRA toxicity modeli
          ├── Hakaret modeli
          ├── Zorbalık modeli
          ├── Nefret dili modeli
          └── OCR ve görsel sinyalleri
                    │
                    ▼
          Gemini 3.5 Flash Lite
          Claim extraction
                    │
                    ▼
          Tavily evidence search
                    │
                    ▼
          Gemini 3.5 Flash Lite
          Final reasoning
                    │
                    ▼
          DiyalogKalkanı moderasyon önerisi
                    │
                    ▼
          Next.js sonuç ekranı + kaynak zinciri
```

### Kullanılan modeller

| Görev | Model | Çıktı |
| --- | --- | --- |
| Genel toxicity | `Doruk2404/truthlens-toxic-lora` | `notoxic` veya `toxic` ve binary olasılık |
| Hakaret | `nanelimon/bert-base-turkish-offensive` | Hakaret modelinin gerçek sınıf olasılıkları |
| Zorbaca davranış | `nanelimon/bert-base-turkish-bullying` | Zorbalık alt sınıfları ve `Nötr` karşıtı toplam skor |
| Nefret dili | `ctoraman/hate-speech-berturk` | `Neutral/Normal`, `Offensive`, `Hate` olasılıkları |
| Claim reasoning | Gemini 3.5 Flash Lite | Claim çıkarımı ve final değerlendirme |
| Evidence search | Tavily | Kaynak adayları ve URL’ler |

Genel BERT+LoRA modeli yalnızca binary görev yapar. Genel modelin confidence değeri hakaret veya zorbalık yüzdesine dönüştürülmez. Bu üç risk alanının skorları kendi modellerinden gelir.

Hate modeli için arayüzde kullanılan doğrulanmış mapping şöyledir:

```
LABEL_0 = Neutral / Normal = Nötr / normal içerik
LABEL_1 = Offensive       = Saldırgan / aşağılayıcı içerik
LABEL_2 = Hate            = Nefret söylemi
```

---

## 2. Gereksinimler

Projeyi çalıştırmak için aşağıdakiler gerekir:

| Gereksinim | Önerilen sürüm |
| --- | --- |
| Python | 3.10 veya üzeri |
| Node.js | 20 veya üzeri |
| npm | Node.js ile birlikte gelir |
| İnternet | İlk model indirme, Gemini ve Tavily için gerekir |
| İşletim sistemi | macOS, Linux veya Windows |
| GPU | Zorunlu değil; CPU ile çalışır, GPU önerilir |

İlk çalıştırmada dört Hugging Face modeli indirilir. Modellerin toplam boyutu ve CPU belleği sistemden sisteme değişebilir. Hugging Face erişimi DNS veya ağ nedeniyle başarısız olursa backend fallback durumunu dürüstçe gösterir; sahte model skoru üretmez.

---

## 3. Proje klasör yapısı

Kullanıcının proje klasörü şu yapıda olmalıdır:

```
truthlens-ai/
├── backend/
│   ├── main.py
│   ├── requirements.txt
│   ├── .env
│   ├── .env.example
│   ├── truthlens.db                 # Çalışırken oluşabilir
│   └── test_*.py
│
└── frontend/
    ├── app/
    │   ├── page.tsx
    │   ├── layout.tsx
    │   └── globals.css
    ├── package.json
    ├── package-lock.json
    └── tsconfig.json
```

Bu teslim paketinde dosyalar aynı klasördeyse, `main.py` ve Python dosyalarını backend klasörüne; `app/`, `package.json` ve Next.js dosyalarını frontend klasörüne taşıyın. `main.py` hangi klasörde çalıştırılıyorsa `.env` de aynı klasörde bulunmalıdır.

---

## 4. API anahtarları nereden alınır?

### 4.1 Google Gemini API anahtarı

1. [Google AI Studio](https://aistudio.google.com/) hesabınıza girin.

1. API key bölümünden yeni bir anahtar oluşturun.

1. Anahtarı yalnızca **backend ****`.env`**** dosyasına** yazın.

1. Anahtarı `page.tsx`, frontend `.env`, GitHub veya ekran görüntüsüne koymayın.

TruthLens claim extraction ve final reasoning için doğrudan Google Gemini API kullanır.

### 4.2 Tavily API anahtarı

1. [Tavily](https://tavily.com/) hesabı açın.

1. Dashboard üzerinden API key oluşturun.

1. Anahtarı backend `.env` içine `TAVILY_API_KEY` olarak ekleyin.

Tavily, Gemini’nin ürettiği doğrulanabilir claim için kaynak adayı arar. Tavily anahtarı yoksa kaynak zinciri sınırlı veya boş dönebilir; toxicity analizi yine çalışabilir.

### 4.3 Hugging Face token

Model repository’leri public ise `HF_TOKEN` boş bırakılabilir. Hugging Face rate limit veya private repository kullanılıyorsa [Hugging Face Settings → Access Tokens](https://huggingface.co/settings/tokens) sayfasından Read yetkili token oluşturun.

Token yalnızca backend `.env` dosyasına yazılmalıdır. Frontend’e aktarılmamalıdır.

### 4.4 Sightengine bilgileri — isteğe bağlı

Görselin yapay üretilmiş olma ihtimalini analiz etmek için [Sightengine](https://sightengine.com/) hesabındaki kullanıcı ve secret bilgilerini kullanabilirsiniz. Bu bilgiler yoksa metin, OCR ve diğer analizler çalışmaya devam eder; yalnızca Sightengine görsel AI sinyali kullanılamaz.

### 4.5 Bluesky bilgileri — isteğe bağlı demo

Bluesky sosyal demo akışını kullanacaksanız:

- `BLUESKY_HANDLE`: Bluesky kullanıcı adınız.

- `BLUESKY_APP_PASSWORD`: Bluesky uygulama parolası.

Normal TruthLens metin analizi için bu iki değişken zorunlu değildir. Gerçek hesabınızın normal parolasını kullanmayın; Bluesky uygulama parolası oluşturun.

### 4.6 Cohere ve NaraRouter

Mevcut aktif `main.py` akışında `COHERE_API_KEY`, `NARAROUTER_API_KEY` ve `NARAROUTER_MODEL` kullanılmaz. Bu nedenle çalışma için gerekli değillerdir. Eski deneysel `cohere_web_test.py` veya `image_fix.py` dosyaları çalıştırılmadıkça bu anahtarları `.env` içinde tutmanız gerekmez.

Önerilen yaklaşım:

```
# Silinebilir; aktif main.py tarafından kullanılmıyor
COHERE_API_KEY=
NARAROUTER_API_KEY=
NARAROUTER_MODEL=
```

Bu değerlerden herhangi biri daha önce gerçek anahtar olarak kullanıldıysa güvenlik için ilgili servis panelinden anahtarı iptal edip yenisini üretin.

---

## 5. Backend `.env` dosyası

Backend klasöründe `.env.example` dosyasını `.env` adıyla kopyalayın:

### macOS / Linux

```bash
cd backend
cp .env.example .env
```

### Windows PowerShell

```
cd backend
Copy-Item .env.example .env
```

Sonra `.env` dosyasını açıp aşağıdaki alanları doldurun:

```
# Zorunlu: doğrudan Google Gemini API
GOOGLE_API_KEY=BURAYA_GOOGLE_AI_STUDIO_ANAHTARI
GEMINI_MODEL=gemini-3.5-flash-lite
GEMINI_API_BASE=https://generativelanguage.googleapis.com/v1beta

# Önerilir: claim kanıtı için
TAVILY_API_KEY=BURAYA_TAVILY_ANAHTARI

# Hugging Face modelleri
TOXICITY_MODEL_ID=Doruk2404/truthlens-toxic-lora
TOXICITY_BASE_MODEL=dbmdz/bert-base-turkish-cased
INSULT_MODEL_ID=nanelimon/bert-base-turkish-offensive
BULLYING_MODEL_ID=nanelimon/bert-base-turkish-bullying
HATE_MODEL_ID=ctoraman/hate-speech-berturk
HF_TOKEN=
TOXICITY_MAX_LENGTH=256
AUXILIARY_MODEL_MAX_LENGTH=256

# İsteğe bağlı görsel AI analizi
SIGHTENGINE_API_USER=
SIGHTENGINE_API_SECRET=

# İsteğe bağlı Bluesky sosyal demo
BLUESKY_HANDLE=
BLUESKY_APP_PASSWORD=

# Frontend geliştirme adreslerine izin verir
ALLOWED_ORIGINS=http://localhost:3000,http://127.0.0.1:3000,http://localhost:5173,http://127.0.0.1:5173
```

### Hugging Face cache ayarları

macOS veya Linux’ta modelleri belirli bir diske indirmek isterseniz `.env` içine aşağıdaki gibi cache değişkenleri ekleyebilirsiniz:

```
HF_HOME=/Users/kullanici_adiniz/hf-cache
HF_HUB_CACHE=/Users/kullanici_adiniz/hf-cache/hub
TRANSFORMERS_CACHE=/Users/kullanici_adiniz/hf-cache/transformers
```

Windows örneği:

```
HF_HOME=C:/Users/KullaniciAdiniz/hf-cache
HF_HUB_CACHE=C:/Users/KullaniciAdiniz/hf-cache/hub
TRANSFORMERS_CACHE=C:/Users/KullaniciAdiniz/hf-cache/transformers
```

Klasörün gerçekten var olduğundan emin olun. Cache değişkenleri modelin Hugging Face’ten indirilmesini sağlar; internet bağlantısı olmadan ilk indirme yapılamaz. Modeller daha önce cache’e indirilmişse offline yükleme mümkün olabilir, ancak backend’in kullandığı cache yolunun doğru olması gerekir.

> `HF_HOME=/Users/dorukoz/hf-cache` yalnızca o bilgisayardaki `/Users/dorukoz` kullanıcısı için geçerlidir. Başka bir kullanıcının bilgisayarında bu yolu aynen kullanmayın; kendi kullanıcı klasörünüzü yazın.

---

## 6. `.gitignore` güvenliği

Mevcut `.gitignore` fikren doğru, ancak `**pycache**/` yazımı doğru Python cache deseni değildir. Aşağıdaki sürümü kullanın:

```
# Secrets and local environment
.env
.env.*
!.env.example

# Python virtual environments
venv/
.venv/
env/

# Python cache
__pycache__/
**/__pycache__/
*.py[cod]
*$py.class

# Hugging Face and model caches
.cache/
.huggingface/
hf-cache/
transformers-cache/

# Local application data
*.db
*.db-shm
*.db-wal

# Logs and local outputs
*.log
/tmp/

# Node / Next.js
node_modules/
.next/
out/
coverage/

# OS/editor files
.DS_Store
Thumbs.db
.vscode/
.idea/

# Test artifacts
raw_three_before.json
```

`.env.example` Git’e eklenebilir; gerçek `.env` kesinlikle eklenmemelidir. API anahtarlarını daha önce Git’e gönderdiyseniz yalnızca dosyayı silmek yeterli değildir; anahtarları servis panellerinden iptal edip yenilerini üretin.

---

## 7. macOS kurulumu ve çalıştırma

Aşağıdaki adımlar macOS içindir. Terminal uygulamasını açın. Proje klasörünüzün adını farklı verdiyseniz `truthlens-ai` yerine kendi klasör adınızı yazın.

### 7.1. Ön kontroller

```bash
python3 --version
node --version
npm --version
```

Python 3.10 veya üzeri ve Node.js 20 veya üzeri önerilir. Node.js kurulu değilse [nodejs.org](https://nodejs.org/) üzerinden LTS sürümünü kurun.

### 7.2. Backend klasörüne girin ve sanal ortam oluşturun

```bash
cd ~/truthlens-ai/backend
python3 -m venv .venv
source .venv/bin/activate
```

Terminal satırının başında `(.venv)` görürseniz sanal ortam aktiftir. Her yeni backend terminalinde önce şu komutu tekrar çalıştırmanız gerekir:

```bash
source .venv/bin/activate
```

### 7.3. Python bağımlılıklarını kurun

```bash
python -m pip install --upgrade pip
python -m pip install -r requirements.txt
```

İlk kurulumda PyTorch, Transformers, PEFT, Hugging Face Hub, Tesseract/Pillow ve FastAPI bağımlılıkları yüklenir. OCR için sistemde Tesseract yoksa Homebrew ile kurabilirsiniz:

```bash
brew install tesseract
```

### 7.4. Backend `.env` dosyasını oluşturun

```bash
cp .env.example .env
open -e .env
```

`.env` içinde en azından `GOOGLE_API_KEY`, `GEMINI_MODEL`, `TAVILY_API_KEY` ve Hugging Face model ID’lerini kontrol edin. Gerçek anahtarları yalnızca bu backend `.env` dosyasına yazın.

Apple Silicon Mac’lerde modeller CPU’da çalışabilir. İlk model indirme sırasında yeterli disk alanı ve internet bağlantısı gerekir.

### 7.5. Hugging Face cache yolunu macOS’a göre ayarlayın

Örneğin kendi kullanıcı adınız `dorukoz` ise:

```
HF_HOME=/Users/dorukoz/hf-cache
HF_HUB_CACHE=/Users/dorukoz/hf-cache/hub
TRANSFORMERS_CACHE=/Users/dorukoz/hf-cache/transformers
```

Başka bir kullanıcıdaysanız `dorukoz` yerine kendi macOS kullanıcı adınızı yazın. Bu klasörleri oluşturmak için:

```bash
mkdir -p "$HOME/hf-cache/hub" "$HOME/hf-cache/transformers"
```

### 7.6. Backend’i başlatın — Terminal 1

```bash
cd ~/truthlens-ai/backend
source .venv/bin/activate
uvicorn main:app --host 127.0.0.1 --port 8000 --reload
```

Bu terminali açık bırakın. Backend hazır olduktan sonra şu adresleri açın:

- [http://127.0.0.1:8000/health](http://127.0.0.1:8000/health)

- [http://127.0.0.1:8000/docs](http://127.0.0.1:8000/docs)

### 7.7. Frontend’i başlatın — Terminal 2

Yeni bir Terminal penceresi açın; backend terminalini kapatmayın.

```bash
cd ~/truthlens-ai/frontend
npm ci
```

Frontend backend’i varsayılan olarak `http://127.0.0.1:8000` adresinde arar. Backend adresi farklıysa:

```bash
printf 'NEXT_PUBLIC_API_BASE_URL=http://127.0.0.1:8000\n' > .env.local
```

Ardından frontend’i başlatın:

```bash
npm run dev
```

Tarayıcıda [http://localhost:3000](http://localhost:3000) adresini açın.

### 7.8. macOS için backend sağlık kontrolü

Yeni bir terminalde veya ikinci terminalde:

```bash
curl http://127.0.0.1:8000/health
```

`google_gemini_configured: true` ve dört model için `available: true` görmeniz beklenir. Hugging Face DNS veya indirme sorunu varsa ilgili model `available: false` olur; frontend bunu `Model kullanılamadı` olarak gösterir ve sahte skor üretmez.

---

## 8. Windows kurulumu ve çalıştırma

Aşağıdaki adımlar Windows 10/11 ve **PowerShell** içindir. PowerShell’i açın. Proje klasörünüzün adını farklı verdiyseniz `truthlens-ai` yerine kendi klasör adınızı yazın.

### 8.1. Ön kontroller

```
py --version
node --version
npm --version
```

Python 3.10 veya üzeri ve Node.js 20 veya üzeri önerilir. Python için [python.org](https://www.python.org/downloads/windows/) ve Node.js için [nodejs.org](https://nodejs.org/) LTS sürümünü kurun. Python kurulumunda **Add Python to PATH** seçeneğini işaretleyin.

### 8.2. Backend klasörüne girin ve sanal ortam oluşturun

```
cd $HOME\truthlens-ai\backend
py -m venv .venv
.\.venv\Scripts\Activate.ps1
```

Terminal satırının başında `(.venv)` görürseniz sanal ortam aktiftir. Her yeni backend PowerShell penceresinde önce şu komutu tekrar çalıştırmanız gerekir:

```
.\.venv\Scripts\Activate.ps1
```

Eğer PowerShell script çalıştırma politikası hatası verirse yalnızca mevcut kullanıcı için şu komutu çalıştırın:

```
Set-ExecutionPolicy -Scope CurrentUser RemoteSigned
```

Sonra aktivasyon komutunu tekrar çalıştırın.

### 8.3. Python bağımlılıklarını kurun

```
python -m pip install --upgrade pip
python -m pip install -r requirements.txt
```

İlk kurulumda PyTorch, Transformers, PEFT, Hugging Face Hub, Tesseract/Pillow ve FastAPI bağımlılıkları yüklenir. OCR için Windows’a Tesseract kurmanız gerekebilir. Kurulumdan sonra Tesseract’ın PATH’e eklendiğinden emin olun.

### 8.4. Backend `.env` dosyasını oluşturun

```
Copy-Item .env.example .env
notepad .env
```

`.env` içinde en azından `GOOGLE_API_KEY`, `GEMINI_MODEL`, `TAVILY_API_KEY` ve Hugging Face model ID’lerini kontrol edin. Gerçek anahtarları yalnızca backend `.env` dosyasına yazın.

### 8.5. Hugging Face cache yolunu Windows’a göre ayarlayın

Örneğin Windows kullanıcı adınız `Doruk` ise:

```
HF_HOME=C:/Users/Doruk/hf-cache
HF_HUB_CACHE=C:/Users/Doruk/hf-cache/hub
TRANSFORMERS_CACHE=C:/Users/Doruk/hf-cache/transformers
```

Alternatif olarak PowerShell’de cache değişkenlerini geçici olarak tanımlayabilirsiniz:

```
$env:HF_HOME="$HOME\hf-cache"
$env:HF_HUB_CACHE="$HOME\hf-cache\hub"
$env:TRANSFORMERS_CACHE="$HOME\hf-cache\transformers"
New-Item -ItemType Directory -Force "$HOME\hf-cache\hub" | Out-Null
New-Item -ItemType Directory -Force "$HOME\hf-cache\transformers" | Out-Null
```

### 8.6. Backend’i başlatın — PowerShell Terminal 1

```
cd $HOME\truthlens-ai\backend
.\.venv\Scripts\Activate.ps1
uvicorn main:app --host 127.0.0.1 --port 8000 --reload
```

Bu pencereyi açık bırakın. Backend hazır olduktan sonra şu adresleri açın:

- [http://127.0.0.1:8000/health](http://127.0.0.1:8000/health)

- [http://127.0.0.1:8000/docs](http://127.0.0.1:8000/docs)

### 8.7. Frontend’i başlatın — PowerShell Terminal 2

Yeni bir PowerShell penceresi açın; backend penceresini kapatmayın.

```
cd $HOME\truthlens-ai\frontend
npm ci
```

Frontend backend’i varsayılan olarak `http://127.0.0.1:8000` adresinde arar. Backend adresi farklıysa:

```
Set-Content -Path .env.local -Value "NEXT_PUBLIC_API_BASE_URL=http://127.0.0.1:8000"
```

Ardından frontend’i başlatın:

```
npm run dev
```

Tarayıcıda [http://localhost:3000](http://localhost:3000) adresini açın.

### 8.8. Windows için backend sağlık kontrolü

PowerShell’de:

```
Invoke-RestMethod http://127.0.0.1:8000/health | ConvertTo-Json -Depth 10
```

`google_gemini_configured: true` ve dört model için `available: true` görmeniz beklenir. Hugging Face DNS veya indirme sorunu varsa ilgili model `available: false` olur; frontend bunu `Model kullanılamadı` olarak gösterir ve sahte skor üretmez.

### 8.9. Windows’ta iki terminalin kısa özeti

**PowerShell Terminal 1 — backend:**

```
cd $HOME\truthlens-ai\backend
.\.venv\Scripts\Activate.ps1
uvicorn main:app --host 127.0.0.1 --port 8000 --reload
```

**PowerShell Terminal 2 — frontend:**

```
cd $HOME\truthlens-ai\frontend
npm ci
npm run dev
```

---

## 9. İlk analiz nasıl yapılır?

1. Backend’in `/health` durumunu kontrol edin.

1. Frontend’i `http://localhost:3000` adresinden açın.

1. Metin alanına örneğin `Sen tam bir aptalsın.` yazın.

1. **Analiz Et** düğmesine basın.

1. Sonuç ekranında genel toxicity engine’ini ve model confidence’ını kontrol edin.

1. Bağlamsal toksisite kartında hakaret, zorbalık ve hate modelinin ayrı sonuçlarını kontrol edin.

1. Doğrulanabilir bir cümlede claim, supporting/contradicting kaynaklar ve Tavily durumunu inceleyin.

Hate modelinin sonuçları arayüzde şu anlamlarla gösterilir:

```
Nötr / normal içerik
Saldırgan / aşağılayıcı içerik
Nefret söylemi
```

Model kullanılamıyorsa arayüzde **Model kullanılamadı** gösterilmelidir. Bu, gerçek `%0` ile aynı şey değildir.

---

## 10. API örnekleri

### Metin analizi

```bash
curl -X POST http://127.0.0.1:8000/analyze \
  -H "Content-Type: application/json" \
  -d '{"content":"Sen tam bir aptalsın."}'
```

`text` alanı da geriye dönük uyumluluk için kabul edilir:

```bash
curl -X POST http://127.0.0.1:8000/analyze \
  -H "Content-Type: application/json" \
  -d '{"text":"Bugün hava çok güzel."}'
```

### URL analizi

```bash
curl -X POST http://127.0.0.1:8000/analyze-url \
  -H "Content-Type: application/json" \
  -d '{"url":"https://example.com"}'
```

### Önemli response alanları

```json
{
  "toxicity_label": "toxic",
  "toxicity_confidence": 0.9994,
  "toxicity_engine": "model",
  "toxicity_models": {
    "insult": {
      "score": 99.93,
      "engine": "insult_model",
      "raw": {}
    },
    "bullying": {
      "score": 99.99,
      "engine": "bullying_model",
      "raw": {}
    },
    "hate_speech": {
      "engine": "hate_model",
      "raw": {
        "Neutral / Normal": 0.4,
        "Offensive": 95.7,
        "Hate": 3.9
      }
    }
  },
  "pipeline_status": {},
  "moderation": {}
}
```

Yüzdeler örnek amaçlıdır. Gerçek sonuç her metin ve model inference’ına göre değişir.

---

## 11. Testler

Backend sanal ortamı aktifken:

```bash
python -m py_compile main.py
python test_moderation_logic.py
python test_toxicity.py
python test_binary_toxicity_mapping.py
python test_multi_model_runtime.py
python test_analyze_raw_three.py
python test_hybrid_pipeline.py
```

Frontend production build testi:

```bash
cd ../frontend
npm ci
npm run build
```

Gerçek Hugging Face model testi internet ve yeterli RAM gerektirir. Model cache’te değilse ilk çalıştırmada indirme yapılır. Ağ/DNS yoksa `available=false` beklenen sonuçtur; bu durumda testin amacı fallback davranışının sahte skor üretmediğini doğrulamaktır.

---

## 12. Yaygın sorunlar ve çözümleri

### `Fallback (model unavailable )` görünüyor

Önce `/health` adresini açın. Dört modelden biri `available=false` ise `error` alanını okuyun. En yaygın nedenler Hugging Face DNS erişimi, ilk model indirme bağlantısının kesilmesi, yetersiz RAM/disk veya yanlış cache yoludur.

### Gemini çalışmıyor

`.env` içinde `GOOGLE_API_KEY` değerinin gerçek ve aktif olduğunu, `GEMINI_MODEL=gemini-3.5-flash-lite` satırının bulunduğunu kontrol edin. `.env` değiştikten sonra backend’i tamamen yeniden başlatın.

### Kaynaklar boş

`TAVILY_API_KEY` eksikse veya claim çıkarılamazsa Tavily evidence adımı boş kalabilir. `/analyze` response içindeki `pipeline_status` alanında `gemini_claim_extraction`, `tavily` ve `gemini_final_reasoning` durumlarını kontrol edin.

### Frontend backend’e bağlanamıyor

Backend’in gerçekten `127.0.0.1:8000` üzerinde çalıştığını kontrol edin. Farklı port kullanıyorsanız frontend `.env.local` içine `NEXT_PUBLIC_API_BASE_URL` yazıp frontend’i yeniden başlatın.

### `422 Unprocessable Entity` alınıyor

İstek gövdesinde `content` veya `text` alanlarından en az biri bulunmalıdır:

```json
{"content":"Analiz edilecek metin"}
```

### Hugging Face DNS hatası

Önce interneti ve DNS’i kontrol edin. Modeller daha önce indirildiyse `.env` içindeki `HF_HOME`, `HF_HUB_CACHE` ve `TRANSFORMERS_CACHE` yollarının aynı kullanıcı ve aynı backend ortamı için doğru olduğundan emin olun. Cache yoksa modeller internet erişimli bir ortamda indirilmeden tamamen offline çalıştırılamaz.

### Port zaten kullanılıyor

```bash
lsof -i :8000
kill -9 PID
```

Windows PowerShell:

```
netstat -ano | findstr :8000
taskkill /PID PID /F
```

---

## 13. Güvenlik kontrol listesi

- Gerçek API anahtarlarını `.env` içinde tutun.

- `.env` dosyasını Git’e göndermeyin.

- `GOOGLE_API_KEY`, `TAVILY_API_KEY`, `HF_TOKEN`, Sightengine secret ve Bluesky app password değerlerini frontend’e koymayın.

- Gerçek anahtar Git’e girdiyse panelden iptal edip yenisini üretin.

- Bluesky normal hesabınızın parolasını değil app password kullanın.

- Üretim ortamında `ALLOWED_ORIGINS` değerini yalnızca gerçek frontend domainiyle sınırlandırın.

- Hugging Face model cache’ini ve `truthlens.db` dosyasını public repository’ye eklemeyin.

---

## 14. NSosyal / Bluesky demo

TruthLens’in sosyal demo ekranı platform adapter mantığını gösterir. `BLUESKY_HANDLE` ve `BLUESKY_APP_PASSWORD` tanımlıysa Bluesky feed ve sosyal aksiyonlar çalışabilir. NSosyal entegrasyonu prototipte adapter/simülasyon sözleşmesiyle gösterilir; gerçek üretim hesabında paylaşım, silme veya cezalandırma işlemi yapmadan önce platform izinleri, API sözleşmesi ve insan onayı akışı ayrıca doğrulanmalıdır.

DiyalogKalkanı’nın amacı otomatik silme değil; moderatöre açıklanabilir ve geri döndürülebilir karar desteği sunmaktır.

---

## 15. Üretim öncesi kontrol

```
[ ] .env oluşturuldu ve gerçek anahtarlar yalnızca backend’de tutuluyor
[ ] NaraRouter/Cohere eski anahtarları aktif config’ten kaldırıldı
[ ] Backend requirements kuruldu
[ ] /health açılıyor
[ ] Dört Hugging Face modelinin available durumu kontrol edildi
[ ] Gemini configured/success durumu kontrol edildi
[ ] Tavily evidence testi yapıldı
[ ] Frontend localhost:3000 üzerinde açıldı
[ ] Üç örnek metin analiz edildi
[ ] npm run build başarılı
[ ] Gerçek .env Git’e girmiyor
[ ] API anahtarları README veya ekran görüntüsünde görünmüyor
```

---

## 16. Lisans ve sorumlu kullanım

TruthLens AI bir moderasyon karar destek prototipidir. Model sonuçları olasılıksal olduğundan tek başına hukuki, cezai veya kullanıcı hesabını etkileyen geri döndürülemez kararlar için kullanılmamalıdır. Orta ve yüksek riskli sonuçlarda insan incelemesi, itiraz ve denetim kaydı korunmalıdır.

Kullanılan açık kaynak model ve kütüphanelerin lisans koşulları ayrıca incelenmeli ve dağıtım sırasında ilgili model kartlarındaki şartlara uyulmalıdır.

---

## 17. Kaynaklar

1. [Google Gemini API Documentation](https://ai.google.dev/gemini-api/docs)

1. [Tavily Documentation](https://docs.tavily.com/)

1. [Hugging Face — Doruk2404/truthlens-toxic-lora](https://huggingface.co/Doruk2404/truthlens-toxic-lora)

1. [Hugging Face — nanelimon/bert-base-turkish-offensive](https://huggingface.co/nanelimon/bert-base-turkish-offensive)

1. [Hugging Face — nanelimon/bert-base-turkish-bullying](https://huggingface.co/nanelimon/bert-base-turkish-bullying)

1. [Hugging Face — ctoraman/hate-speech-berturk](https://huggingface.co/ctoraman/hate-speech-berturk)

1. [FastAPI Documentation](https://fastapi.tiangolo.com/)

1. [Next.js Documentation](https://nextjs.org/docs)

1. [Bluesky AT Protocol Documentation](https://docs.bsky.app/)

---

## En kısa çalıştırma özeti

```bash
# Terminal 1
cd truthlens-ai/backend
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
uvicorn main:app --host 127.0.0.1 --port 8000 --reload

# Terminal 2
cd truthlens-ai/frontend
npm ci
npm run dev

# Tarayıcı
open http://localhost:3000
```

Windows’ta `source .venv/bin/activate` yerine `.\.venv\Scripts\Activate.ps1` kullanın.