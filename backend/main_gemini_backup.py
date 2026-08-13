import json
import os
import re
from typing import List, Optional

import requests
from bs4 import BeautifulSoup
from dotenv import load_dotenv

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field

from google import genai
from google.genai import types


# ============================================================
# ENVIRONMENT
# ============================================================

load_dotenv()

GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")


# ============================================================
# FASTAPI
# ============================================================

app = FastAPI(
    title="TruthLens AI API",
    description=(
        "Yapay zeka destekli bilgi doğrulama ve "
        "sosyal medya içerik analiz sistemi"
    ),
    version="2.0.0",
)


# ============================================================
# CORS
# ============================================================

app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:3000",
        "http://127.0.0.1:3000",
        "http://localhost:5173",
        "http://127.0.0.1:5173",
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# ============================================================
# REQUEST MODEL
# ============================================================

class AnalysisRequest(BaseModel):
    content: str = Field(
        min_length=1,
        max_length=10000,
    )


# ============================================================
# SOURCE MODEL
# ============================================================

class Source(BaseModel):
    title: str
    url: str
    relevance: str
    reliability: int
    reliability_reason: str = ""


# ============================================================
# RESPONSE MODEL
# ============================================================

class AnalysisResponse(BaseModel):
    score: int
    manipulation: int
    clickbait: int
    ai_probability: int

    result: str
    explanation: str

    claims: List[str]
    context: str

    sources: List[Source]
    supporting_sources: List[Source]
    contradicting_sources: List[Source]


# ============================================================
# HOME
# ============================================================

@app.get("/")
def root():
    return {
        "status": "online",
        "service": "TruthLens AI API",
        "version": "2.0.0",
    }


# ============================================================
# HEALTH CHECK
# ============================================================

@app.get("/health")
def health():
    return {
        "status": "healthy",
        "gemini_configured": bool(GEMINI_API_KEY),
    }


# ============================================================
# URL DETECTION
# ============================================================

def extract_url(text: str) -> Optional[str]:
    """
    Metnin içinde URL bulur.

    Desteklenen örnekler:

    https://nsosyal.com/post/123

    [https://nsosyal.com/post/123](https://nsosyal.com/post/123)
    """

    if not text:
        return None

    # Markdown URL
    markdown_match = re.search(
        r"\[[^\]]*\]\((https?://[^)\s]+)\)",
        text,
        re.IGNORECASE,
    )

    if markdown_match:
        return markdown_match.group(1).strip()

    # Normal URL
    match = re.search(
        r"https?://[^\s<>\"]+",
        text,
        re.IGNORECASE,
    )

    if not match:
        return None

    url = match.group(0).strip()

    # Gereksiz kapanış karakterlerini temizle
    url = url.rstrip(
        ".,;:!?)]}\"'"
    )

    return url


# ============================================================
# NSOSYAL URL VALIDATION
# ============================================================

def is_nsosyal_url(url: str) -> bool:
    """
    URL'nin NSosyal'e ait olup olmadığını kontrol eder.
    """

    if not url:
        return False

    return bool(
        re.match(
            r"^https?://(?:www\.)?nsosyal\.com/",
            url,
            re.IGNORECASE,
        )
    )


def is_nsosyal_post_url(url: str) -> bool:
    """
    URL'nin gerçek bir NSosyal gönderi URL'si
    olup olmadığını kontrol eder.
    """

    if not url:
        return False

    return bool(
        re.match(
            r"^https?://(?:www\.)?nsosyal\.com/post/[0-9]+(?:/)?(?:\?.*)?$",
            url,
            re.IGNORECASE,
        )
    )


# ============================================================
# WEB PAGE FETCH
# ============================================================

def fetch_webpage(url: str) -> Optional[str]:
    """
    Web sayfasını indirir.
    """

    headers = {
        "User-Agent": (
            "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
            "AppleWebKit/537.36 "
            "(KHTML, like Gecko) "
            "Chrome/139.0.0.0 Safari/537.36"
        ),
        "Accept-Language": (
            "tr-TR,tr;q=0.9,en;q=0.8"
        ),
        "Accept": (
            "text/html,"
            "application/xhtml+xml,"
            "application/xml;q=0.9,"
            "*/*;q=0.8"
        ),
    }

    try:
        response = requests.get(
            url,
            headers=headers,
            timeout=15,
            allow_redirects=True,
        )

        response.raise_for_status()

        return response.text

    except requests.RequestException as e:

        print(
            f"[TruthLens] Web request error: {e}"
        )

        return None

    except Exception as e:

        print(
            f"[TruthLens] Unexpected web error: {e}"
        )

        return None


# ============================================================
# JSON-LD OBJECTS
# ============================================================

def get_json_ld_objects(
    soup: BeautifulSoup,
) -> List[dict]:
    """
    Sayfadaki JSON-LD objelerini çıkarır.
    """

    objects: List[dict] = []

    scripts = soup.find_all(
        "script",
        type="application/ld+json",
    )

    for script in scripts:

        content = (
            script.string
            or script.get_text()
            or ""
        ).strip()

        if not content:
            continue

        try:
            data = json.loads(content)

        except (
            json.JSONDecodeError,
            TypeError,
        ):
            continue

        # Tek obje
        if isinstance(data, dict):

            objects.append(data)

            graph = data.get("@graph")

            if isinstance(graph, list):

                for item in graph:

                    if isinstance(item, dict):
                        objects.append(item)

        # Liste
        elif isinstance(data, list):

            for item in data:

                if isinstance(item, dict):
                    objects.append(item)

    return objects


# ============================================================
# NSOSYAL JSON-LD EXTRACTION
# ============================================================

def extract_nsosyal_social_media_post(
    soup: BeautifulSoup,
    requested_url: str,
) -> Optional[dict]:
    """
    NSosyal'in JSON-LD içindeki
    SocialMediaPosting objesini bulur.

    articleBody alanını kullanır.
    """

    requested_post_id = None

    id_match = re.search(
        r"/post/([0-9]+)",
        requested_url,
        re.IGNORECASE,
    )

    if id_match:
        requested_post_id = id_match.group(1)

    objects = get_json_ld_objects(soup)

    for obj in objects:

        if not isinstance(obj, dict):
            continue

        obj_type = obj.get("@type")

        # @type liste olabilir
        if isinstance(obj_type, list):

            is_social_post = (
                "SocialMediaPosting"
                in obj_type
            )

        else:

            is_social_post = (
                obj_type
                == "SocialMediaPosting"
            )

        if not is_social_post:
            continue

        obj_url = str(
            obj.get("url", "")
        )

        # ----------------------------------------------------
        # POST ID KONTROLÜ
        # ----------------------------------------------------

        if requested_post_id:

            if requested_post_id not in obj_url:

                object_id = str(
                    obj.get("@id", "")
                )

                if (
                    requested_post_id
                    not in object_id
                ):
                    continue

        # ----------------------------------------------------
        # ARTICLE BODY
        # ----------------------------------------------------

        article_body = obj.get(
            "articleBody"
        )

        if not article_body:
            continue

        article_body = str(
            article_body
        ).strip()

        if len(article_body) < 20:
            continue

        author = obj.get("author")

        if isinstance(author, dict):
            author = author.get(
                "name",
                ""
            )

        return {
            "text": article_body,
            "title": obj.get("headline"),
            "url": obj.get("url"),
            "author": author,
            "datePublished": obj.get(
                "datePublished"
            ),
            "dateModified": obj.get(
                "dateModified"
            ),
            "image": obj.get("image"),
            "method": (
                "json-ld-socialmediaposting"
            ),
        }

    return None


# ============================================================
# META EXTRACTION
# ============================================================

def get_meta_content(
    soup: BeautifulSoup,
    property_name: Optional[str] = None,
    name: Optional[str] = None,
) -> Optional[str]:

    tag = None

    if property_name:

        tag = soup.find(
            "meta",
            attrs={
                "property": property_name
            },
        )

    if not tag and name:

        tag = soup.find(
            "meta",
            attrs={
                "name": name
            },
        )

    if not tag:
        return None

    value = tag.get("content")

    if not value:
        return None

    return value.strip()


# ============================================================
# EXTRACT PAGE CONTENT
# ============================================================

def extract_page_content(
    html: str,
    url: str,
) -> dict:
    """
    Sayfadaki içeriği kademeli olarak çıkarır.

    Öncelik:

    1. NSosyal JSON-LD SocialMediaPosting
    2. OpenGraph description
    3. Twitter description
    4. Normal description
    5. HTML metni
    """

    soup = BeautifulSoup(
        html,
        "html.parser",
    )

    # ========================================================
    # 1. NSOSYAL JSON-LD
    # ========================================================

    social_post = (
        extract_nsosyal_social_media_post(
            soup,
            url,
        )
    )

    if social_post:

        return {
            "success": True,
            "text": social_post["text"],
            "title": social_post.get(
                "title"
            ),
            "method": social_post["method"],
            "author": social_post.get(
                "author"
            ),
            "datePublished": social_post.get(
                "datePublished"
            ),
            "image": social_post.get(
                "image"
            ),
        }

    # ========================================================
    # 2. OPENGRAPH
    # ========================================================

    og_description = get_meta_content(
        soup,
        property_name="og:description",
    )

    if (
        og_description
        and len(og_description) >= 20
    ):

        return {
            "success": True,
            "text": og_description[:20000],
            "title": get_meta_content(
                soup,
                property_name="og:title",
            ),
            "method": "opengraph",
        }

    # ========================================================
    # 3. TWITTER
    # ========================================================

    twitter_description = get_meta_content(
        soup,
        name="twitter:description",
    )

    if (
        twitter_description
        and len(twitter_description) >= 20
    ):

        return {
            "success": True,
            "text": twitter_description[:20000],
            "title": get_meta_content(
                soup,
                name="twitter:title",
            ),
            "method": "twitter",
        }

    # ========================================================
    # 4. NORMAL DESCRIPTION
    # ========================================================

    meta_description = get_meta_content(
        soup,
        name="description",
    )

    if (
        meta_description
        and len(meta_description) >= 20
    ):

        title = None

        if (
            soup.title
            and soup.title.string
        ):
            title = soup.title.string.strip()

        return {
            "success": True,
            "text": meta_description[:20000],
            "title": title,
            "method": "description",
        }

    # ========================================================
    # 5. NORMAL HTML
    # ========================================================

    for element in soup.find_all(
        [
            "script",
            "style",
            "noscript",
            "svg",
            "iframe",
            "nav",
            "footer",
        ]
    ):
        element.decompose()

    page_text = soup.get_text(
        separator=" ",
        strip=True,
    )

    page_text = re.sub(
        r"\s+",
        " ",
        page_text,
    ).strip()

    if len(page_text) >= 80:

        title = None

        if (
            soup.title
            and soup.title.string
        ):
            title = soup.title.string.strip()

        return {
            "success": True,
            "text": page_text[:20000],
            "title": title,
            "method": "html",
        }

    return {
        "success": False,
        "text": "",
        "title": None,
        "method": "failed",
    }


# ============================================================
# GET POST CONTENT
# ============================================================

def get_post_content(
    url: str,
) -> dict:
    """
    URL'den gerçek gönderi içeriğini çıkarır.
    """

    # --------------------------------------------------------
    # NSOSYAL URL KONTROLÜ
    # --------------------------------------------------------

    if is_nsosyal_url(url):

        if not is_nsosyal_post_url(url):

            return {
                "success": False,
                "text": "",
                "reason": (
                    "NSosyal URL'si bir "
                    "gönderi URL'si değil."
                ),
            }

    # --------------------------------------------------------
    # HTML İNDİR
    # --------------------------------------------------------

    html = fetch_webpage(url)

    if not html:

        return {
            "success": False,
            "text": "",
            "reason": (
                "Gönderi sayfasına erişilemedi."
            ),
        }

    # --------------------------------------------------------
    # İÇERİK ÇIKAR
    # --------------------------------------------------------

    result = extract_page_content(
        html,
        url,
    )

    if not result["success"]:

        return {
            "success": False,
            "text": "",
            "reason": (
                "Sayfadan okunabilir gönderi "
                "içeriği alınamadı."
            ),
        }

    text = result["text"].strip()

    # --------------------------------------------------------
    # ÇOK KISA
    # --------------------------------------------------------

    if len(text) < 20:

        return {
            "success": False,
            "text": "",
            "reason": (
                "Alınan içerik çok kısa."
            ),
        }

    # --------------------------------------------------------
    # LOGIN SAYFASI KONTROLÜ
    # --------------------------------------------------------

    lower_text = text.lower()

    login_phrases = [
        "giriş yap",
        "kayıt ol",
        "hesap oluştur",
        "sign in",
        "log in",
    ]

    login_count = sum(
        phrase in lower_text
        for phrase in login_phrases
    )

    if (
        result["method"]
        != "json-ld-socialmediaposting"
        and login_count >= 2
        and len(text) < 500
    ):

        return {
            "success": False,
            "text": "",
            "reason": (
                "Gönderi yerine giriş/kayıt "
                "sayfası alınmış olabilir."
            ),
        }

    # --------------------------------------------------------
    # BAŞARILI
    # --------------------------------------------------------

    return {
        "success": True,
        "text": text,
        "title": result.get("title"),
        "method": result.get("method"),
        "author": result.get("author"),
        "datePublished": result.get(
            "datePublished"
        ),
        "image": result.get("image"),
        "reason": "",
    }


# ============================================================
# SOURCE CLEANER
# ============================================================

def clean_source_list(
    source_list,
) -> List[Source]:

    clean_sources: List[Source] = []

    if not isinstance(
        source_list,
        list,
    ):
        return clean_sources

    seen_urls = set()

    for source in source_list:

        if not isinstance(
            source,
            dict,
        ):
            continue

        title = str(
            source.get(
                "title",
                "",
            )
        ).strip()

        source_url_value = str(
            source.get(
                "url",
                "",
            )
        ).strip()

        relevance = str(
            source.get(
                "relevance",
                "",
            )
        ).strip()

        reliability_reason = str(
            source.get(
                "reliability_reason",
                "",
            )
        ).strip()

        try:

            reliability = int(
                source.get(
                    "reliability",
                    0,
                )
            )

        except (
            TypeError,
            ValueError,
        ):

            reliability = 0

        reliability = max(
            0,
            min(
                100,
                reliability,
            ),
        )

        # ----------------------------------------------------
        # URL KONTROLÜ
        # ----------------------------------------------------

        valid_url = bool(
            re.match(
                r"^https?://",
                source_url_value,
                re.IGNORECASE,
            )
        )

        if not valid_url:
            continue

        # ----------------------------------------------------
        # BAŞLIK KONTROLÜ
        # ----------------------------------------------------

        if not title:
            continue

        # ----------------------------------------------------
        # DUPLICATE URL
        # ----------------------------------------------------

        normalized_url = source_url_value.rstrip(
            "/"
        ).lower()

        if normalized_url in seen_urls:
            continue

        seen_urls.add(
            normalized_url
        )

        clean_sources.append(
            Source(
                title=title,
                url=source_url_value,
                relevance=relevance,
                reliability=reliability,
                reliability_reason=(
                    reliability_reason
                ),
            )
        )

    return clean_sources


# ============================================================
# CLEAN GEMINI JSON
# ============================================================

def clean_json_response(
    text: str,
) -> str:
    """
    Gemini JSON'u markdown code block içinde
    döndürürse temizler.
    """

    if not text:
        return ""

    text = text.strip()

    # Markdown code block
    text = re.sub(
        r"^```(?:json)?\s*",
        "",
        text,
        flags=re.IGNORECASE,
    )

    text = re.sub(
        r"\s*```$",
        "",
        text,
    )

    text = text.strip()

    # Gemini bazen JSON'dan önce/sonra
    # gereksiz açıklama döndürebilir.
    # İlk { ve son } arasını almaya çalış.
    first_brace = text.find("{")
    last_brace = text.rfind("}")

    if (
        first_brace != -1
        and last_brace != -1
        and last_brace > first_brace
    ):
        text = text[
            first_brace:last_brace + 1
        ]

    return text.strip()


# ============================================================
# GEMINI CLIENT
# ============================================================

def create_gemini_client():

    if not GEMINI_API_KEY:

        raise HTTPException(
            status_code=500,
            detail=(
                "GEMINI_API_KEY yapılandırılmamış. "
                ".env dosyanı kontrol et."
            ),
        )

    try:

        return genai.Client(
            api_key=GEMINI_API_KEY
        )

    except Exception as e:

        raise HTTPException(
            status_code=500,
            detail=(
                "Gemini istemcisi oluşturulamadı: "
                f"{str(e)}"
            ),
        )


# ============================================================
# RESEARCH PROMPT
# ============================================================

def build_research_prompt(
    analyzed_content: str,
    source_url: Optional[str],
) -> str:

    return f"""
Sen TruthLens AI adlı Türkçe bilgi doğrulama sisteminin
araştırma motorusun.

Aşağıdaki içerik gerçek kullanıcı içeriğidir.

--- İÇERİK BAŞLANGICI ---

{analyzed_content}

--- İÇERİK SONU ---

Kaynak URL:
{source_url or "URL yok"}

============================================================

GÖREV

Metindeki doğrulanabilir ana iddiaları tespit et ve araştır.

1. Önce metindeki doğrulanabilir iddiaları ayır.

2. Her önemli iddianın gerçekten araştırılması gerekip
   gerekmediğini değerlendir.

3. Gerekli olduğunda Google Search kullan.

4. Mümkün olduğunca birincil ve yüksek kaliteli kaynaklara
   ulaş.

KAYNAK ÖNCELİĞİ

1. Resmi devlet kurumları
2. Resmi uluslararası kuruluşlar
3. Bilimsel kuruluşlar
4. Üniversiteler
5. Hakemli bilimsel yayınlar
6. Birincil kaynaklar
7. Güvenilir haber kuruluşları
8. Diğer güvenilir yayınlar

ÖNEMLİ AYRIM

Bir kaynağın güvenilir olması ile belirli bir iddiayı
desteklemesi aynı şey değildir.

Örneğin bir üniversite sitesi güvenilir olabilir fakat
incelenen iddiayı desteklemiyor olabilir.

Bu durumda kaynağı destekleyici kaynak olarak gösterme.

DESTEKLEYEN KAYNAK

Bir kaynak ancak iddianın ana anlamını gerçekten
destekliyorsa supporting olarak değerlendirilmelidir.

ÇELİŞEN KAYNAK

Bir kaynak ancak iddianın ana anlamına gerçekten
karşı çıkıyorsa contradicting olarak değerlendirilmelidir.

Sadece aynı konudan bahseden kaynaklar destekleyici veya
çelişen kaynak değildir.

DİKKAT

- Kaynak uydurma.
- URL uydurma.
- Google Search sonuç sayfasını kaynak olarak verme.
- Mümkünse doğrudan kaynak sayfasını bul.
- Bir kaynağın söylemediği şeyi söylediğini iddia etme.
- İçerikte olmayan iddialar üretme.
- Kanıt bulunamadı ile yanlış ifadesini karıştırma.
- Yeterli kanıt yoksa bunu açıkça belirt.
- Eski bir bilgi ile güncel bir bilgiyi karıştırma.
- Tarih önemliyse kaynağın tarihini dikkate al.
- Birden fazla güvenilir kaynak aynı sonucu gösteriyorsa
  bunu belirt.
- Kaynaklar arasında anlaşmazlık varsa bunu belirt.

NSOSYAL ÖZEL KURALI

Eğer içerik NSosyal gönderisinden alınmışsa NSosyal
platformunun kendisini araştırma.

Gönderideki gerçek iddiaları araştır.

SONUÇ

Araştırma sonucunu düz metin olarak ver.

Henüz JSON üretme.

Araştırma sırasında kullandığın gerçek kaynakların
başlıklarını, URL'lerini ve hangi iddiayla ilişkili
olduklarını açıkça belirt.
"""


# ============================================================
# JSON PROMPT
# ============================================================

def build_json_prompt(
    analyzed_content: str,
    research_text: str,
    source_url: Optional[str],
) -> str:

    return f"""
Sen TruthLens AI adlı Türkçe bilgi doğrulama ve sosyal medya
içerik analiz sisteminin sonuç oluşturma motorusun.

Aşağıdaki kullanıcı içeriğini ve araştırma sonucunu kullan.

============================================================
KULLANICI İÇERİĞİ
============================================================

{analyzed_content}

============================================================
KAYNAK URL
============================================================

{source_url or "URL yok"}

============================================================
ARAŞTIRMA SONUCU
============================================================

{research_text}

============================================================

Şimdi yalnızca geçerli JSON üret.

Markdown kullanma.

JSON dışında hiçbir şey yazma.

============================================================
ALANLAR
============================================================

score
manipulation
clickbait
ai_probability
result
explanation
claims
context
sources
supporting_sources
contradicting_sources

============================================================
SKORLAR
============================================================

score:

İçeriğin araştırma sonucuna göre genel doğruluk/güvenilirlik
değerlendirmesi.

0 = çok düşük güvenilirlik
100 = çok yüksek güvenilirlik

Bu skor "AI tarafından yazılmış olma" ihtimalinden bağımsızdır.

------------------------------------------------------------

manipulation:

İçeriğin okuyucuyu yönlendirme/manipüle etme riski.

0 = belirgin manipülasyon yok
100 = çok yüksek manipülasyon

------------------------------------------------------------

clickbait:

Başlık veya anlatımın clickbait olma riski.

0 = clickbait belirtisi yok
100 = çok yüksek clickbait

------------------------------------------------------------

ai_probability:

Metnin yapay zeka tarafından oluşturulmuş olma ihtimali.

0 = çok düşük
100 = çok yüksek

ÖNEMLİ:

AI tarafından yazılmış olmak metnin yanlış olduğu anlamına
gelmez.

ai_probability ve score birbirinden bağımsız değerlendirilmelidir.

AI tespiti yalnızca dilsel belirtilere dayanıyorsa bunu
kesinlik olarak sunma.

============================================================
CLAIMS
============================================================

claims:

Metindeki doğrulanabilir ana iddiaları listele.

İçerikte olmayan iddialar ekleme.

============================================================
CONTEXT
============================================================

context:

Sonucu anlamak için gerekli önemli eksik bağlamı yaz.

Bağlam gerekmiyorsa:

"Ek bağlam gerekmiyor."

============================================================
RESULT
============================================================

result:

Türkçe kısa sonuç.

Örnek sonuç kategorileri:

"Doğru"
"Büyük ölçüde doğru"
"Kısmen doğru"
"Yanıltıcı"
"Yanlış"
"Kanıt yetersiz"
"Bağlama bağlı"

Ancak kategoriyi araştırma sonucuna göre seç.

============================================================
EXPLANATION
============================================================

explanation:

Sonucun nedenini açıkla.

Hangi iddiaların desteklendiğini,
hangilerinin desteklenmediğini veya çeliştiğini belirt.

============================================================
SOURCES
============================================================

sources:

Araştırmada kullanılan genel kaynaklar.

============================================================
SUPPORTING SOURCES
============================================================

supporting_sources:

İddiayı gerçekten destekleyen kaynaklar.

Sadece aynı konu hakkında olan kaynakları buraya koyma.

============================================================
CONTRADICTING SOURCES
============================================================

contradicting_sources:

İddiayla gerçekten çelişen kaynaklar.

Sadece aynı konu hakkında olan kaynakları buraya koyma.

============================================================
SOURCE FORMAT
============================================================

Her kaynak şu alanlara sahip olmalıdır:

title
url
relevance
reliability
reliability_reason

reliability:

0-100 arasında tam sayı.

Kaynağın güvenilirliğini değerlendir.

reliability_reason:

Kaynağın neden güvenilir olduğunu veya neden daha düşük
güvenilirliğe sahip olduğunu Türkçe açıkla.

relevance:

Kaynağın bu içerikteki iddiayla ilişkisini Türkçe açıkla.

============================================================
KAYNAK KURALLARI
============================================================

- URL uydurma.
- Sahte kaynak üretme.
- Google Search sonuç sayfasını kaynak olarak verme.
- Kaynağın gerçek URL'sini kullan.
- Aynı URL'yi tekrar tekrar ekleme.
- Kaynağın söylemediği şeyi söylediğini iddia etme.
- Kaynak bulunamazsa listeyi [] yap.
- Kanıt bulunamadıysa "yanlış" sonucuna zorunlu olarak gitme.
- Çelişen güvenilir kaynaklar varsa bunu açıkça belirt.
- Kaynak güvenilirliği ile iddiayı destekleme durumu
  birbirinden bağımsızdır.

============================================================
DİL
============================================================

result Türkçe olmalıdır.

explanation Türkçe olmalıdır.

claims Türkçe olmalıdır.

context Türkçe olmalıdır.

relevance Türkçe olmalıdır.

reliability_reason Türkçe olmalıdır.

JSON anahtarları İngilizce olmalıdır.

============================================================
JSON
============================================================

Aşağıdaki yapıyı kullan:

{{
    "score": 0,
    "manipulation": 0,
    "clickbait": 0,
    "ai_probability": 0,

    "result": "Türkçe kısa değerlendirme",

    "explanation": "Sonucun açıklaması",

    "claims": [
        "Ana doğrulanabilir iddia"
    ],

    "context": "Gerekli bağlam",

    "sources": [
        {{
            "title": "Kaynak başlığı",
            "url": "Gerçek URL",
            "relevance": "Kaynağın iddiayla ilişkisi",
            "reliability": 0,
            "reliability_reason": "Güvenilirlik nedeni"
        }}
    ],

    "supporting_sources": [
        {{
            "title": "Kaynak başlığı",
            "url": "Gerçek URL",
            "relevance": "İddiayı nasıl desteklediği",
            "reliability": 0,
            "reliability_reason": "Güvenilirlik nedeni"
        }}
    ],

    "contradicting_sources": [
        {{
            "title": "Kaynak başlığı",
            "url": "Gerçek URL",
            "relevance": "İddiayla nasıl çeliştiği",
            "reliability": 0,
            "reliability_reason": "Güvenilirlik nedeni"
        }}
    ]
}}
"""


# ============================================================
# GEMINI RESEARCH
# ============================================================

def run_gemini_research(
    client,
    analyzed_content: str,
    source_url: Optional[str],
) -> str:

    prompt = build_research_prompt(
        analyzed_content,
        source_url,
    )

    try:

        response = client.models.generate_content(
            model="gemini-2.5-flash",
            contents=prompt,
            config=types.GenerateContentConfig(
                tools=[
                    types.Tool(
                        google_search=types.GoogleSearch()
                    )
                ],
                temperature=0.2,
            ),
        )

    except Exception as e:

        print(
            f"[TruthLens] Research Gemini error: {e}"
        )

        raise HTTPException(
            status_code=502,
            detail=(
                "Gemini araştırma hatası: "
                f"{str(e)}"
            ),
        )

    if not response.text:

        raise HTTPException(
            status_code=502,
            detail=(
                "Gemini araştırma sonucunu boş döndürdü."
            ),
        )

    return response.text.strip()


# ============================================================
# GEMINI JSON GENERATION
# ============================================================

def run_gemini_json(
    client,
    analyzed_content: str,
    research_text: str,
    source_url: Optional[str],
) -> str:

    prompt = build_json_prompt(
        analyzed_content,
        research_text,
        source_url,
    )

    try:

        response = client.models.generate_content(
            model="gemini-2.5-flash",
            contents=prompt,
            config=types.GenerateContentConfig(
                temperature=0.1,
                response_mime_type="application/json",
            ),
        )

    except Exception as e:

        print(
            f"[TruthLens] JSON Gemini error: {e}"
        )

        raise HTTPException(
            status_code=502,
            detail=(
                "Gemini JSON oluşturma hatası: "
                f"{str(e)}"
            ),
        )

    if not response.text:

        raise HTTPException(
            status_code=502,
            detail=(
                "Gemini JSON sonucunu boş döndürdü."
            ),
        )

    return clean_json_response(
        response.text
    )


# ============================================================
# VALIDATE SCORE
# ============================================================

def safe_score(
    value,
    default: int = 0,
) -> int:

    try:

        return max(
            0,
            min(
                100,
                int(value),
            ),
        )

    except (
        TypeError,
        ValueError,
    ):

        return default


# ============================================================
# ANALYZE
# ============================================================

@app.post(
    "/analyze",
    response_model=AnalysisResponse,
)
def analyze(
    request: AnalysisRequest,
):

    # ========================================================
    # API KEY
    # ========================================================

    if not GEMINI_API_KEY:

        raise HTTPException(
            status_code=500,
            detail=(
                "GEMINI_API_KEY yapılandırılmamış. "
                ".env dosyanı kontrol et."
            ),
        )

    # ========================================================
    # INPUT
    # ========================================================

    original_content = (
        request.content.strip()
    )

    if not original_content:

        raise HTTPException(
            status_code=400,
            detail="İçerik boş olamaz.",
        )

    url = extract_url(
        original_content
    )

    analyzed_content = original_content

    source_url = None

    extraction_method = "direct-text"

    # ========================================================
    # URL VARSA
    # ========================================================

    if url:

        source_url = url

        print(
            f"[TruthLens] URL bulundu: {url}"
        )

        # ----------------------------------------------------
        # NSOSYAL
        # ----------------------------------------------------

        if is_nsosyal_url(url):

            print(
                "[TruthLens] NSosyal URL'si tespit edildi."
            )

            post = get_post_content(
                url
            )

            if not post["success"]:

                raise HTTPException(
                    status_code=422,
                    detail=(
                        "Gönderinin içeriğine doğrudan "
                        "erişilemedi. TruthLens AI, "
                        "içeriğini okuyamadığı bir gönderi "
                        "hakkında tahminde bulunmaz. "
                        f"Nedeni: {post['reason']}"
                    ),
                )

            analyzed_content = (
                post["text"]
            )

            extraction_method = (
                post.get(
                    "method",
                    "unknown",
                )
            )

            print(
                "[TruthLens] İçerik başarıyla alındı."
            )

            print(
                "[TruthLens] Extraction method: "
                f"{extraction_method}"
            )

            print(
                "[TruthLens] İçerik uzunluğu: "
                f"{len(analyzed_content)}"
            )

        # ----------------------------------------------------
        # DİĞER URL'LER
        # ----------------------------------------------------

        else:

            post = get_post_content(
                url
            )

            if post["success"]:

                analyzed_content = (
                    post["text"]
                )

                extraction_method = (
                    post.get(
                        "method",
                        "unknown",
                    )
                )

                print(
                    "[TruthLens] Harici URL içeriği alındı."
                )

            else:

                raise HTTPException(
                    status_code=422,
                    detail=(
                        "URL içeriği okunamadı. "
                        f"Nedeni: {post['reason']}"
                    ),
                )

    # ========================================================
    # GEMINI CLIENT
    # ========================================================

    client = create_gemini_client()

    # ========================================================
    # 1. AŞAMA: WEB ARAŞTIRMASI
    # ========================================================

    print(
        "[TruthLens] Gemini araştırması başlıyor..."
    )

    research_text = run_gemini_research(
        client=client,
        analyzed_content=analyzed_content,
        source_url=source_url,
    )

    print(
        "[TruthLens] Gemini araştırması tamamlandı."
    )

    # ========================================================
    # 2. AŞAMA: JSON ANALİZİ
    # ========================================================

    print(
        "[TruthLens] Gemini JSON analizi başlıyor..."
    )

    json_text = run_gemini_json(
        client=client,
        analyzed_content=analyzed_content,
        research_text=research_text,
        source_url=source_url,
    )

    print(
        "[TruthLens] Gemini JSON analizi tamamlandı."
    )

    # ========================================================
    # JSON PARSE
    # ========================================================

    try:

        data = json.loads(
            json_text
        )

    except json.JSONDecodeError as e:

        print(
            "[TruthLens] Gemini JSON parse hatası:"
        )

        print(
            json_text
        )

        raise HTTPException(
            status_code=502,
            detail=(
                "Gemini geçerli JSON döndürmedi. "
                f"Hata: {str(e)}"
            ),
        )

    if not isinstance(data, dict):

        raise HTTPException(
            status_code=502,
            detail=(
                "Gemini JSON cevabı obje formatında değil."
            ),
        )

    # ========================================================
    # REQUIRED FIELDS
    # ========================================================

    required_fields = [
        "score",
        "manipulation",
        "clickbait",
        "ai_probability",
        "result",
        "explanation",
        "claims",
        "context",
        "sources",
        "supporting_sources",
        "contradicting_sources",
    ]

    for field in required_fields:

        if field not in data:

            raise HTTPException(
                status_code=502,
                detail=(
                    "AI cevabında alan eksik: "
                    f"{field}"
                ),
            )

    # ========================================================
    # SCORE LIMITS
    # ========================================================

    data["score"] = safe_score(
        data["score"]
    )

    data["manipulation"] = safe_score(
        data["manipulation"]
    )

    data["clickbait"] = safe_score(
        data["clickbait"]
    )

    data["ai_probability"] = safe_score(
        data["ai_probability"]
    )

    # ========================================================
    # CLAIMS
    # ========================================================

    claims: List[str] = []

    if isinstance(
        data["claims"],
        list,
    ):

        for claim in data["claims"]:

            claim_text = str(
                claim
            ).strip()

            if claim_text:

                claims.append(
                    claim_text
                )

    # ========================================================
    # SOURCES
    # ========================================================

    clean_sources = clean_source_list(
        data["sources"]
    )

    # ========================================================
    # SUPPORTING SOURCES
    # ========================================================

    supporting_sources = clean_source_list(
        data["supporting_sources"]
    )

    # ========================================================
    # CONTRADICTING SOURCES
    # ========================================================

    contradicting_sources = (
        clean_source_list(
            data["contradicting_sources"]
        )
    )

    # ========================================================
    # FINAL RESPONSE
    # ========================================================

    return AnalysisResponse(
        score=data["score"],
        manipulation=data["manipulation"],
        clickbait=data["clickbait"],
        ai_probability=data["ai_probability"],

        result=str(
            data["result"]
        ).strip(),

        explanation=str(
            data["explanation"]
        ).strip(),

        claims=claims,

        context=str(
            data["context"]
        ).strip(),

        sources=clean_sources,

        supporting_sources=supporting_sources,

        contradicting_sources=(
            contradicting_sources
        ),
    )


# ============================================================
# RUN DIRECTLY
# ============================================================

if __name__ == "__main__":

    import uvicorn

    uvicorn.run(
        "main:app",
        host="0.0.0.0",
        port=8000,
        reload=True,
    )