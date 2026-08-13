import json
import os

from dotenv import load_dotenv
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field
from google import genai


# --------------------------------------------------
# ENVIRONMENT
# --------------------------------------------------

load_dotenv()

GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")


# --------------------------------------------------
# FASTAPI
# --------------------------------------------------

app = FastAPI(
    title="TruthLens AI API",
    description="Yapay zeka destekli bilgi ve sosyal medya içerik analiz sistemi",
    version="0.4.0",
)


# --------------------------------------------------
# CORS
# --------------------------------------------------

app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:3000",
        "http://127.0.0.1:3000",
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# --------------------------------------------------
# REQUEST MODEL
# --------------------------------------------------

class AnalysisRequest(BaseModel):
    content: str = Field(
        min_length=1,
        max_length=10000
    )


# --------------------------------------------------
# RESPONSE MODEL
# --------------------------------------------------

class AnalysisResponse(BaseModel):
    score: int
    manipulation: int
    clickbait: int
    ai_probability: int
    result: str
    explanation: str
    claims: list[str]
    context: str


# --------------------------------------------------
# HOME
# --------------------------------------------------

@app.get("/")
def root():
    return {
        "status": "online",
        "service": "TruthLens AI API",
        "version": "0.4.0",
    }


# --------------------------------------------------
# ANALYSIS
# --------------------------------------------------

@app.post(
    "/analyze",
    response_model=AnalysisResponse
)
def analyze(request: AnalysisRequest):

    # API KEY CONTROL
    if not GEMINI_API_KEY:
        raise RuntimeError(
            "GEMINI_API_KEY is not configured."
        )

    # GEMINI CLIENT
    client = genai.Client(
        api_key=GEMINI_API_KEY
    )

    # --------------------------------------------------
    # PROMPT
    # --------------------------------------------------

    prompt = f"""
Sen TruthLens AI adlı Türkçe bir bilgi doğrulama
ve içerik analiz sisteminin yapay zeka motorusun.

Kullanıcının gönderdiği sosyal medya gönderisini,
haber metnini veya iddiayı analiz et.

İÇERİK:
---
{request.content}
---

DİL KURALI — ÇOK ÖNEMLİ:

- Cevabın TAMAMI TÜRKÇE olmalıdır.
- Tüm açıklamalar TÜRKÇE olmalıdır.
- Tüm gerekçeler TÜRKÇE olmalıdır.
- Tüm iddialar TÜRKÇE yazılmalıdır.
- Eksik bağlam açıklaması TÜRKÇE olmalıdır.
- Genel değerlendirme TÜRKÇE olmalıdır.
- Analizin nedenlerini TÜRKÇE ve anlaşılır şekilde açıkla.
- İngilizce açıklama, İngilizce başlık veya İngilizce cümle kullanma.
- Özel isimler, marka isimleri, bilimsel terimler veya kaynak adları
  gerektiğinde orijinal biçiminde bırakılabilir.
- JSON anahtarları aşağıda verilen şekilde İngilizce kalmalıdır.
- JSON anahtarlarının DEĞERLERİ tamamen TÜRKÇE olmalıdır.

--------------------------------------------------
ANALİZ GÖREVLERİ
--------------------------------------------------

1. Metindeki doğrulanabilir ana iddiaları belirle.

2. İddiaların güvenilirliğini değerlendir.

3. Metindeki yanıltıcı anlatımları belirle.

4. Eksik veya önemli bağlamı belirle.

5. Manipülasyon belirtilerini değerlendir.

6. Clickbait belirtilerini değerlendir.

7. Metnin yapay zeka tarafından oluşturulmuş olma ihtimalini değerlendir.

8. Her değerlendirme için NEDEN böyle düşündüğünü Türkçe olarak açıkla.

--------------------------------------------------
ÖNEMLİ KURALLAR
--------------------------------------------------

- Metinde bulunmayan bilgi, kaynak, araştırma, kişi,
  kurum veya istatistik UYDURMA.

- Kullanıcı metninde kaynak bulunmuyorsa,
  varmış gibi kaynak gösterme.

- Bir iddianın yanlış olduğundan emin değilsen
  kesin olarak "yanlış" deme.

- Yeterli kanıt yoksa bunu açıkça belirt.

- "Kanıt bulunamadı" ile
  "iddia yanlıştır" ifadelerini birbirine karıştırma.

- Bir metnin yapay zeka tarafından yazılmış olması,
  onun yanlış olduğu anlamına gelmez.

- AI olasılığı ile bilgi güvenilirliğini birbirinden
  bağımsız değerlendir.

- Skorların nedenini explanation alanında
  Türkçe olarak açıkla.

- Korkutucu, sansasyonel veya kesin ifadeleri
  özellikle incele.

- "Bilim insanları", "uzmanlar", "araştırmalar"
  gibi belirsiz otoriteler kullanılıyorsa bunu belirt.

- Metnin amacı bilgi vermek, ikna etmek, korkutmak,
  yönlendirmek veya etkileşim almak olabilir.
  Bunu değerlendir.

--------------------------------------------------
SKORLAR
--------------------------------------------------

score:

Genel güvenilirlik skoru.

0 = çok düşük güvenilirlik
100 = çok yüksek güvenilirlik

manipulation:

Manipülasyon riski.

0 = belirgin manipülasyon yok
100 = çok yüksek manipülasyon riski

clickbait:

Clickbait riski.

0 = clickbait belirtisi yok
100 = çok yüksek clickbait riski

ai_probability:

Metnin yapay zeka tarafından oluşturulmuş olma ihtimali.

0 = çok düşük ihtimal
100 = çok yüksek ihtimal

--------------------------------------------------
ÖNEMLİ AYRIM
--------------------------------------------------

Bir metnin AI tarafından yazılmış olması,
metnin yanlış olduğu anlamına GELMEZ.

Bu nedenle:

ai_probability

skorunu:

score

hesaplamasında tek başına belirleyici yapma.

--------------------------------------------------
JSON KURALI
--------------------------------------------------

SADECE GEÇERLİ JSON DÖNDÜR.

Markdown kullanma.

```json kullanma.

``` kullanma.

JSON'un dışına hiçbir açıklama yazma.

Aşağıdaki yapıyı birebir kullan:

{{
    "score": 0,
    "manipulation": 0,
    "clickbait": 0,
    "ai_probability": 0,
    "result": "Türkçe kısa genel değerlendirme",
    "explanation": "Bu sonuca neden ulaşıldığını ayrıntılı ve anlaşılır Türkçe ile açıkla.",
    "claims": [
        "Metindeki doğrulanabilir ana iddia Türkçe olarak yazılacak."
    ],
    "context": "Metinde eksik olan önemli bağlam Türkçe olarak açıklanacak."
}}

--------------------------------------------------
SON KONTROL
--------------------------------------------------

JSON'u oluşturmadan önce:

- Bütün açıklamaların Türkçe olduğunu kontrol et.
- Bütün gerekçelerin Türkçe olduğunu kontrol et.
- Bütün iddiaların Türkçe olduğunu kontrol et.
- Context alanının Türkçe olduğunu kontrol et.
- İngilizce cümle bulunmadığını kontrol et.
- JSON formatının geçerli olduğunu kontrol et.
- JSON dışında hiçbir şey yazma.
"""


    # --------------------------------------------------
    # GEMINI REQUEST
    # --------------------------------------------------

    response = client.models.generate_content(
        model="gemini-2.5-flash",
        contents=prompt,
    )


    # --------------------------------------------------
    # RESPONSE TEXT
    # --------------------------------------------------

    text = response.text.strip()


    # --------------------------------------------------
    # MARKDOWN CLEANUP
    # --------------------------------------------------

    if text.startswith("```json"):
        text = text[len("```json"):].strip()

    elif text.startswith("```"):
        text = text[len("```"):].strip()


    if text.endswith("```"):
        text = text[:-3].strip()


    # --------------------------------------------------
    # JSON PARSE
    # --------------------------------------------------

    try:

        data = json.loads(text)

    except json.JSONDecodeError:

        raise RuntimeError(
            "AI geçerli bir JSON cevabı döndürmedi."
        )


    # --------------------------------------------------
    # BASIC VALIDATION
    # --------------------------------------------------

    required_fields = [
        "score",
        "manipulation",
        "clickbait",
        "ai_probability",
        "result",
        "explanation",
        "claims",
        "context",
    ]

    for field in required_fields:

        if field not in data:

            raise RuntimeError(
                f"AI cevabında gerekli alan eksik: {field}"
            )


    # --------------------------------------------------
    # SCORE LIMITS
    # --------------------------------------------------

    data["score"] = max(
        0,
        min(100, int(data["score"]))
    )

    data["manipulation"] = max(
        0,
        min(100, int(data["manipulation"]))
    )

    data["clickbait"] = max(
        0,
        min(100, int(data["clickbait"]))
    )

    data["ai_probability"] = max(
        0,
        min(100, int(data["ai_probability"]))
    )


    # --------------------------------------------------
    # RETURN
    # --------------------------------------------------

    return AnalysisResponse(
        score=data["score"],
        manipulation=data["manipulation"],
        clickbait=data["clickbait"],
        ai_probability=data["ai_probability"],
        result=str(data["result"]),
        explanation=str(data["explanation"]),
        claims=[
            str(claim)
            for claim in data["claims"]
        ],
        context=str(data["context"]),
    )