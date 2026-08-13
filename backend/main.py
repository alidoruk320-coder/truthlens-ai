import json
import os
import re
import hashlib
import sqlite3
import uuid
import threading
import time
from datetime import datetime, timezone
from typing import Dict, List, Optional, Set, Tuple
from urllib.parse import urlparse
from urllib.parse import urljoin

import requests
from bs4 import BeautifulSoup
from dotenv import load_dotenv
from fastapi import FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field
from openai import OpenAI
from tavily import TavilyClient
from atproto import Client

load_dotenv(os.path.join(os.path.dirname(__file__), ".env"))

NARAROUTER_API_KEY = os.getenv("NARAROUTER_API_KEY")
NARAROUTER_MODEL = os.getenv("NARAROUTER_MODEL", "laguna-s-2.1")
TAVILY_API_KEY = os.getenv("TAVILY_API_KEY")
SIGHTENGINE_API_USER = os.getenv("SIGHTENGINE_API_USER")
SIGHTENGINE_API_SECRET = os.getenv("SIGHTENGINE_API_SECRET")
BLUESKY_HANDLE = os.getenv("BLUESKY_HANDLE")
BLUESKY_APP_PASSWORD = os.getenv("BLUESKY_APP_PASSWORD")
BLUESKY_FEED_LIMIT = int(os.getenv("BLUESKY_FEED_LIMIT", "5"))
BLUESKY_FEED_MAX_LIMIT = int(os.getenv("BLUESKY_FEED_MAX_LIMIT", "20"))
DB_PATH = os.path.join(os.path.dirname(__file__), "truthlens.db")

app = FastAPI(
    title="TruthLens AI API",
    description="Yapay zeka destekli bilgi doğrulama ve sosyal medya içerik analiz sistemi",
    version="3.1.0",
)

allowed_origins = os.getenv(
    "ALLOWED_ORIGINS",
    "http://localhost:3000,http://127.0.0.1:3000,http://localhost:5173,http://127.0.0.1:5173",
).split(",")
allowed_origins = [origin.strip() for origin in allowed_origins if origin.strip()]

app.add_middleware(
    CORSMiddleware,
    allow_origins=allowed_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ============================================================
# MODELS
# ============================================================

class AnalysisRequest(BaseModel):
    content: str = Field(min_length=1, max_length=10000)

class RegisterRequest(BaseModel):
    name: str = Field(min_length=1, max_length=120)
    email: str = Field(min_length=3, max_length=255)
    password: str = Field(min_length=6, max_length=80)

class LoginRequest(BaseModel):
    email: str = Field(min_length=3, max_length=255)
    password: str = Field(min_length=6, max_length=80)

class Source(BaseModel):
    title: str
    url: str
    relevance: str
    reliability: int = 0
    reliability_reason: str = ""

class SourceChainItem(BaseModel):
    source: str
    date: str

class SourceAnalysis(BaseModel):
    source_status: str = "uncertain"
    source_probability: int = 0
    likely_original_source: str = ""
    earliest_found_source: str = ""
    earliest_found_date: str = ""
    current_source_date: str = ""
    source_chain: List[SourceChainItem] = Field(default_factory=list)
    reasoning: str = ""

class ImageAnalysis(BaseModel):
    image_ai_probability: int = 0
    image_is_ai: Optional[bool] = None
    image_analysis_available: bool = False
    image_analysis_reasoning: str = ""
    image_url: str = ""

class ImageAnalysisRequest(BaseModel):
    image_url: str = Field(min_length=5, max_length=5000)
    source_url: str = Field(default="", max_length=5000)

class ToxicityAnalysis(BaseModel):
    insult: int = 0
    bullying: int = 0
    hate_speech: int = 0
    targeted_person_or_group: str = "Genel"
    risk_level: str = "Düşük"
    context_note: str = "Bağlam değerlendirmesi yapılmadı."

class AnalysisResponse(BaseModel):
    score: int
    manipulation: int
    clickbait: int

    result: str
    explanation: str
    score_breakdown: str
    validity: str
    emotion: str
    time_validity: str

    polarization_risk: int
    echo_chamber: str
    ai_rewrite: str
    social_risk_summary: str
    toxicity: ToxicityAnalysis = Field(default_factory=ToxicityAnalysis)

    claims: List[str]
    context: str

    sources: List[Source]
    supporting_sources: List[Source]
    contradicting_sources: List[Source]
    image_ai_probability: int = 0
    image_is_ai: Optional[bool] = None
    image_analysis_available: bool = False
    source_analysis: SourceAnalysis = Field(default_factory=SourceAnalysis)

ANALYSIS_CACHE: Dict[str, object] = {}


def get_bluesky_client() -> Client:
    if not BLUESKY_HANDLE or not BLUESKY_APP_PASSWORD:
        raise HTTPException(status_code=503, detail="BLUESKY_HANDLE ve BLUESKY_APP_PASSWORD tanımlı değil.")

    client = Client()
    client.login(login=BLUESKY_HANDLE, password=BLUESKY_APP_PASSWORD)
    return client


def normalize_bluesky_post(feed_item) -> dict:
    try:
        post = getattr(feed_item, "post", feed_item)
        if isinstance(post, dict):
            record = post.get("record") or {}
            text = str(record.get("text", "") or "")
            author = post.get("author") or {}
            handle = str(author.get("handle") or BLUESKY_HANDLE or "unknown.bsky.social").replace("@", "")
            author_avatar = str(author.get("avatar") or "")
            uri = str(post.get("uri") or "")
            cid = str(post.get("cid") or "")
            embed = post.get("embed") or {}
            like_count = int(post.get("like_count") or 0)
            repost_count = int(post.get("repost_count") or 0)
            reply_count = int(post.get("reply_count") or 0)
        else:
            record = getattr(post, "record", None)
            text = str(getattr(record, "text", "") if record else "")
            author = getattr(post, "author", None)
            handle = str(getattr(author, "handle", None) or BLUESKY_HANDLE or "unknown.bsky.social").replace("@", "")
            author_avatar = str(getattr(author, "avatar", "") or "")
            uri = str(getattr(post, "uri", "") or "")
            cid = str(getattr(post, "cid", "") or "")
            embed = getattr(post, "embed", {}) or {}
            like_count = int(getattr(post, "like_count", 0) or 0)
            repost_count = int(getattr(post, "repost_count", 0) or 0)
            reply_count = int(getattr(post, "reply_count", 0) or 0)

        image_urls: List[str] = []
        if isinstance(embed, dict):
            images = embed.get("images") or []
            for image in images:
                if isinstance(image, dict):
                    full_size = image.get("fullsize") or image.get("image") or image.get("thumb")
                    if full_size:
                        image_urls.append(str(full_size))
        elif hasattr(embed, "images"):
            for image in getattr(embed, "images", []) or []:
                if hasattr(image, "fullsize"):
                    image_urls.append(str(image.fullsize))
                elif hasattr(image, "image"):
                    image_urls.append(str(image.image))

        engagement = {
            "likes": like_count,
            "reposts": repost_count,
            "replies": reply_count,
        }

        return {
            "id": uri,
            "author": handle,
            "handle": f"@{handle}",
            "avatar": author_avatar,
            "content": str(text).strip(),
            "tag": "Bluesky",
            "source_url": uri,
            "cid": cid,
            "image_urls": image_urls,
            "engagement": engagement,
        }
    except Exception:
        return {
            "id": "unknown",
            "author": "unknown",
            "handle": "@unknown",
            "avatar": "",
            "content": "",
            "tag": "Bluesky",
            "source_url": "",
            "cid": "",
            "image_urls": [],
            "engagement": {"likes": 0, "reposts": 0, "replies": 0},
        }


def social_analysis_cache_key(uri: str, cid: str = "", content: str = "") -> str:
    normalized_uri = normalize_url(uri)
    normalized_cid = str(cid or "").strip().lower()
    normalized_content = stable_text(content)
    raw = f"truthlens:social:v1|{normalized_uri}|{normalized_cid}|{normalized_content}"
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def parse_retry_after(exc: Exception) -> Optional[int]:
    response = getattr(exc, "response", None)
    headers = getattr(response, "headers", None)
    if headers:
        retry_after = headers.get("retry-after") or headers.get("Retry-After")
        if retry_after:
            try:
                return max(1, int(float(retry_after)))
            except Exception:
                return None
    return None


def is_rate_limit_error(exc: Exception) -> bool:
    message = str(exc).lower()
    return "429" in message or "rate limit" in message or "too many requests" in message


def build_social_analysis_fallback(message: str = "AI analizi şu anda beklemede.") -> dict:
    return {
        "summary": message,
        "misinformation_risk": 0,
        "polarization": 0,
        "hate_speech": 0,
        "spam_risk": 0,
        "sentiment": "Belirsiz",
        "reasoning": "Hafif analiz şu anda üretilemedi. Gönderi gösterilmeye devam ediyor.",
        "status": "pending",
    }


def estimate_social_signals(content: str) -> dict:
    text = stable_text(content)
    length = len(text)

    sensational_terms = (
        "şok", "son dakika", "acil", "paylaş", "açıklandı", "ortaya çıktı",
        "kesin", "tam olarak", "asla", "herkes", "hiçbir", "kanıtlandı"
    )
    uncertainty_terms = (
        "iddia", "görünüşe göre", "muhtemelen", "sanırım", "belki",
        "olabilir", "tahmin", "söylenti"
    )
    conflict_terms = (
        "karşı taraf", "hain", "rezil", "utanç", "yalan", "istifa",
        "saldırı", "nefret", "düşman", "suçlu", "aptal"
    )
    spam_terms = (
        "link", "tıkla", "hemen", "kampanya", "indirim", "para kazan",
        "bedava", "çekiliş", "promo"
    )

    sensational_hits = sum(1 for term in sensational_terms if term in text)
    uncertainty_hits = sum(1 for term in uncertainty_terms if term in text)
    conflict_hits = sum(1 for term in conflict_terms if term in text)
    spam_hits = sum(1 for term in spam_terms if term in text)

    misinformation_risk = min(85, max(10, 18 + sensational_hits * 12 + uncertainty_hits * 6 + (0 if length > 180 else 8)))
    polarization = min(90, max(5, 10 + conflict_hits * 15 + sensational_hits * 4))
    hate_speech = min(90, max(0, conflict_hits * 18))
    spam_risk = min(90, max(0, spam_hits * 20 + (8 if "!" in content else 0)))

    if conflict_hits >= 2:
        sentiment = "Öfke"
    elif uncertainty_hits >= 2:
        sentiment = "Endişe"
    elif sensational_hits >= 2:
        sentiment = "Heyecan"
    elif length < 80:
        sentiment = "Nötr"
    else:
        sentiment = "Belirsiz"

    truthlens_score = max(0, min(100, 100 - misinformation_risk))
    return {
        "summary": "🤖 TruthLens analiz ediliyor...",
        "misinformation_risk": misinformation_risk,
        "polarization": polarization,
        "hate_speech": hate_speech,
        "spam_risk": spam_risk,
        "sentiment": sentiment,
        "reasoning": "Bu değerler kısa bir dil sinyali tahminidir; tam mini analiz tamamlandığında güncellenecek.",
        "truthlens_score": truthlens_score,
    }


def analyze_social_post(content: str, source_url: str = "", cid: str = "") -> dict:
    cache_key = social_analysis_cache_key(source_url, cid, content)
    cached = ANALYSIS_CACHE.get(cache_key)
    if isinstance(cached, dict):
        return cached

    prompt = f"""
Aşağıdaki Bluesky gönderisi için yalnızca JSON döndür.
Çok kısa düşün. Web araştırması yapma.

Gönderi:
\"\"\"
{content[:900]}
\"\"\"

Çıktı şeması:
{{
  "summary": "1-2 cümlelik Türkçe mini özet",
  "misinformation_risk": 0-100,
  "polarization": 0-100,
  "hate_speech": 0-100,
  "spam_risk": 0-100,
  "sentiment": "Nötr / Öfke / Endişe / Ümit / Korku / Diğer",
  "reasoning": "Kısa Türkçe gerekçe"
}}
"""

    try:
        raw = call_llm([{"role": "user", "content": prompt}], temperature=0.1)
        data = json.loads(raw)
        result = {
            "summary": str(data.get("summary", "TruthLens mini analizi üretildi.")).strip(),
            "misinformation_risk": safe_score(data.get("misinformation_risk")),
            "polarization": safe_score(data.get("polarization")),
            "hate_speech": safe_score(data.get("hate_speech")),
            "spam_risk": safe_score(data.get("spam_risk")),
            "sentiment": str(data.get("sentiment", "Belirsiz")).strip() or "Belirsiz",
            "reasoning": str(data.get("reasoning", "Kısa gerekçe sağlanamadı.")).strip() or "Kısa gerekçe sağlanamadı.",
            "status": "ready",
        }
        ANALYSIS_CACHE[cache_key] = result
        return result
    except Exception as exc:
        print(f"[TruthLens] Social LLM error: {exc}")
        if is_rate_limit_error(exc):
            retry_after = parse_retry_after(exc)
            if retry_after:
                time.sleep(min(retry_after, 2))
        fallback = build_social_analysis_fallback()
        fallback["status"] = "rate_limited" if is_rate_limit_error(exc) else "error"
        fallback["reasoning"] = "Mini analiz isteği şu anda tamamlanamadı; gönderi görünür durumda."
        ANALYSIS_CACHE[cache_key] = fallback
        return fallback


def attach_social_analysis(post: dict) -> dict:
    content = post.get("content", "")
    source_url = post.get("source_url", "")
    cid = post.get("cid", "")
    cache_key = social_analysis_cache_key(source_url, cid, content)
    cached = ANALYSIS_CACHE.get(cache_key)
    if isinstance(cached, dict):
        analysis = cached
    else:
        analysis = estimate_social_signals(content)
        analysis["cache_key"] = cache_key
        analysis["analysis_status"] = "pending"
    return {
        **post,
        "analysis_status": analysis.get("status", "pending"),
        "summary": analysis.get("summary") or "🤖 TruthLens analiz ediliyor...",
        "misinformation_risk": analysis.get("misinformation_risk", 0),
        "polarization": analysis.get("polarization", 0),
        "hate_speech": analysis.get("hate_speech", 0),
        "spam_risk": analysis.get("spam_risk", 0),
        "sentiment": analysis.get("sentiment", "Belirsiz"),
        "reasoning": analysis.get("reasoning", "🤖 TruthLens analiz ediliyor..."),
        "truthlens_score": analysis.get("truthlens_score", max(0, min(100, 100 - int(analysis.get("misinformation_risk", 0))))),
        "ai": {
            "summary": analysis.get("summary") or "🤖 TruthLens analiz ediliyor...",
            "misinformation_risk": analysis.get("misinformation_risk", 0),
            "polarization": analysis.get("polarization", 0),
            "hate_speech": analysis.get("hate_speech", 0),
            "spam_risk": analysis.get("spam_risk", 0),
            "sentiment": analysis.get("sentiment", "Belirsiz"),
            "reasoning": analysis.get("reasoning", "🤖 TruthLens analiz ediliyor..."),
            "truthlens_score": analysis.get("truthlens_score", 0),
        },
    }


def warm_social_analysis(posts: List[dict], limit: int = 3) -> None:
    for post in posts[:limit]:
        try:
            analyze_social_post(post.get("content", ""), post.get("source_url", ""), post.get("cid", ""))
        except Exception:
            continue


def warm_image_analysis(posts: List[dict], limit: int = 2) -> None:
    warmed = 0
    for post in posts:
        if warmed >= limit:
            break
        image_urls = post.get("image_urls") or []
        if not image_urls:
            continue
        try:
            analyze_image_ai_probability(str(image_urls[0]), str(post.get("source_url", "")))
            warmed += 1
        except Exception:
            continue


def fetch_bluesky_feed(limit: int = BLUESKY_FEED_LIMIT) -> dict:
    try:
        limit = max(1, min(limit, BLUESKY_FEED_MAX_LIMIT))
        client = get_bluesky_client()
        timeline = client.get_timeline(limit=limit)
        posts: List[dict] = []

        for item in getattr(timeline, "feed", []) or []:
            normalized = normalize_bluesky_post(item)
            if not normalized["content"]:
                continue

            estimated = estimate_social_signals(normalized["content"])

            post_payload = {
                **normalized,
                "truthlens_score": estimated.get("truthlens_score", 0),
                "misinformation_risk": estimated.get("misinformation_risk", 0),
                "polarization": estimated.get("polarization", 0),
                "hate_speech": estimated.get("hate_speech", 0),
                "spam_risk": estimated.get("spam_risk", 0),
                "sentiment": estimated.get("sentiment", "Belirsiz"),
                "summary": estimated.get("summary", "🤖 TruthLens analiz ediliyor..."),
                "manipulation": max(0, min(100, estimated.get("polarization", 0))),
                "clickbait": max(0, min(100, estimated.get("spam_risk", 0))),
                "emotion": estimated.get("sentiment", "Belirsiz"),
                "risk_level": "Beklemede",
                "reason": "🤖 TruthLens mini analizi sırada.",
                "toxicity": {
                    "insult": 0,
                    "bullying": 0,
                    "hate_speech": 0,
                    "targeted_person_or_group": "Genel",
                    "risk_level": "Düşük",
                    "context_note": "Mini analiz henüz tamamlanmadı.",
                },
            }
            post_payload = attach_social_analysis(post_payload)
            posts.append(post_payload)

        uncached_posts = [post for post in posts if post.get("analysis_status") == "pending"]
        if uncached_posts:
            threading.Thread(target=warm_social_analysis, args=(uncached_posts, 3), daemon=True).start()

        image_posts = [post for post in posts if post.get("image_urls")]
        if image_posts:
            threading.Thread(target=warm_image_analysis, args=(image_posts, 2), daemon=True).start()

        for post in posts:
            image_urls = post.get("image_urls") or []
            if image_urls:
                image_url = str(image_urls[0])
                cached_image = ANALYSIS_CACHE.get(image_cache_key(image_url, str(post.get("source_url", ""))))
                if isinstance(cached_image, dict):
                    post["image_ai_probability"] = cached_image.get("image_ai_probability", 0)
                    post["image_analysis_available"] = cached_image.get("image_analysis_available", False)
                    post["image_analysis_reasoning"] = cached_image.get("image_analysis_reasoning", "")
                else:
                    post["image_ai_probability"] = 0
                    post["image_analysis_available"] = True
                    post["image_analysis_reasoning"] = "Görsel AI analizi sırada."
            else:
                post["image_ai_probability"] = 0
                post["image_analysis_available"] = False
                post["image_analysis_reasoning"] = ""

        summary = summarize_demo_feed(posts)
        return {
            "posts": posts,
            "summary": summary,
            "provider": "bluesky",
        }
    except HTTPException:
        raise
    except Exception as exc:
        print(f"[TruthLens] Bluesky feed error: {exc}")
        return {
            "posts": build_demo_feed(),
            "summary": {
                "top_emotion": "Nötr",
                "avg_truthlens_score": 0,
                "risk_level": "Düşük",
                "highlight": "Bluesky akışı alınamadı. Lütfen Bluesky kimlik bilgilerini kontrol edin.",
                "total_posts": 0,
            },
            "provider": "demo-fallback",
            "warning": str(exc),
        }


def build_demo_feed() -> List[dict]:
    return [
        {
            "id": "feed-1",
            "author": "selin_aktas",
            "handle": "@selin_aktas",
            "content": "Şehirdeki yeni sağlık kampanyası, herkesin aşısı olduktan sonra tam bir güvenlik sağlıyor. Bu yüzden her şeyi doğru kabul etmek gerekiyor.",
            "tag": "Sağlık",
            "truthlens_score": 42,
            "manipulation": 78,
            "clickbait": 68,
            "emotion": "Öfke",
            "risk_level": "Yüksek",
            "reason": "Kesinlik vurgusu ve bağlamdan kopuk güven telkinleri içeriyor.",
            "toxicity": {
                "insult": 12,
                "bullying": 8,
                "hate_speech": 4,
                "targeted_person_or_group": "Genel",
                "risk_level": "Düşük",
                "context_note": "Hakaret içermeyen ancak güveni abartıcı bir dil kullanıyor."
            },
        },
        {
            "id": "feed-2",
            "author": "duru_analiz",
            "handle": "@duru_analiz",
            "content": "Dün gece yaşanan olayın ardından belediye yetkilileri sessiz kalıyor; bu, herkesin güvenlik sorununu görmezden geldiğinin işaretidir.",
            "tag": "Güvenlik",
            "truthlens_score": 58,
            "manipulation": 53,
            "clickbait": 49,
            "emotion": "Endişe",
            "risk_level": "Orta",
            "reason": "Duygusal bağlam mevcut ama olayın gerçek nedeni için kanıt eksik.",
            "toxicity": {
                "insult": 10,
                "bullying": 5,
                "hate_speech": 3,
                "targeted_person_or_group": "Genel",
                "risk_level": "Düşük",
                "context_note": "Yargı taşıyor ancak doğrudan nefret dili barındırmıyor."
            },
        },
        {
            "id": "feed-3",
            "author": "aylin_tasarim",
            "handle": "@aylin_tasarim",
            "content": "Bu videoda herkesin sadece tek bir siyasi görüşü savunduğunu iddia ediyorum; karşı tarafın hiç konuşma hakkı yok.",
            "tag": "Siyaset",
            "truthlens_score": 31,
            "manipulation": 83,
            "clickbait": 72,
            "emotion": "Öfke",
            "risk_level": "Yüksek",
            "reason": "Şiddetli taraflı dil, tek taraflı çıkarım ve kutuplaştırıcı ifade taşıyor.",
            "toxicity": {
                "insult": 44,
                "bullying": 31,
                "hate_speech": 18,
                "targeted_person_or_group": "Belirli bir grup",
                "risk_level": "Orta",
                "context_note": "Gruba yönelik ayrımcılık içeren ve ötekileştiren bir söylem taşıyor."
            },
        },
        {
            "id": "feed-4",
            "author": "mert_icin",
            "handle": "@mert_icin",
            "content": "Ekip, yeni sistemin test sonuçlarını paylaştı; ilk veriler en düşük hata oranını gösterdiğini ortaya koyuyor.",
            "tag": "Teknoloji",
            "truthlens_score": 82,
            "manipulation": 24,
            "clickbait": 18,
            "emotion": "Nötr",
            "risk_level": "Düşük",
            "reason": "Daha nesnel ifade dili taşıyor ve kesin sonuç iddiası yok.",
            "toxicity": {
                "insult": 0,
                "bullying": 0,
                "hate_speech": 0,
                "targeted_person_or_group": "Genel",
                "risk_level": "Düşük",
                "context_note": "Nötr ve tarafsız dil kullanıyor."
            },
        },
    ]


def summarize_demo_feed(posts: List[dict]) -> dict:
    if not posts:
        return {
            "top_emotion": "Nötr",
            "avg_truthlens_score": 0,
            "risk_level": "Düşük",
            "highlight": "Gösterilecek içerik bulunamadı.",
            "total_posts": 0,
        }

    emotion_counts: Dict[str, int] = {}
    total_score = 0

    for post in posts:
        total_score += int(post.get("truthlens_score", 0))
        emotion = str(post.get("emotion", "Nötr")).strip() or "Nötr"
        emotion_counts[emotion] = emotion_counts.get(emotion, 0) + 1

    top_emotion = max(emotion_counts.items(), key=lambda item: item[1])[0]
    avg_score = round(total_score / len(posts))

    if avg_score >= 70:
        risk_level = "Düşük"
    elif avg_score >= 45:
        risk_level = "Orta"
    else:
        risk_level = "Yüksek"

    highlight = (
        "Son akışta öfke ve taraflı dil baskındır; kutuplaştırıcı içeriklerin oranı dikkat çekiyor."
        if top_emotion in {"Öfke", "Endişe"}
        else "Akış genel olarak daha tarafsız ve düşük riskli görünüyor."
    )

    return {
        "top_emotion": top_emotion,
        "avg_truthlens_score": avg_score,
        "risk_level": risk_level,
        "highlight": highlight,
        "total_posts": len(posts),
    }

# ============================================================
# AUTH / DB LAYER
# ============================================================

def get_db_connection() -> sqlite3.Connection:
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def init_db() -> None:
    conn = get_db_connection()
    conn.executescript(
        """
        CREATE TABLE IF NOT EXISTS users (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL,
            email TEXT NOT NULL UNIQUE,
            password_hash TEXT NOT NULL,
            created_at TEXT NOT NULL
        );

        CREATE TABLE IF NOT EXISTS sessions (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL,
            token TEXT NOT NULL UNIQUE,
            created_at TEXT NOT NULL,
            expires_at TEXT NOT NULL,
            FOREIGN KEY(user_id) REFERENCES users(id)
        );

        CREATE TABLE IF NOT EXISTS analysis_history (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL,
            content_hash TEXT NOT NULL,
            source_url TEXT,
            created_at TEXT NOT NULL,
            result_json TEXT NOT NULL,
            FOREIGN KEY(user_id) REFERENCES users(id)
        );
        """
    )
    conn.commit()
    conn.close()


def hash_password(password: str) -> str:
    return hashlib.sha256(password.strip().encode("utf-8")).hexdigest()


def create_token() -> str:
    return uuid.uuid4().hex


def get_token_from_header(auth_header: Optional[str]) -> Optional[str]:
    if not auth_header:
        return None
    if not auth_header.startswith("Bearer "):
        return None
    return auth_header.split(" ", 1)[1].strip()


def get_current_user_from_request(request: Request) -> Optional[dict]:
    token = get_token_from_header(request.headers.get("authorization"))
    if not token:
        return None

    conn = get_db_connection()
    row = conn.execute(
        "SELECT u.id, u.name, u.email FROM sessions s JOIN users u ON u.id = s.user_id WHERE s.token = ?",
        (token,),
    ).fetchone()
    conn.close()

    if not row:
        return None

    return {
        "id": row["id"],
        "name": row["name"],
        "email": row["email"],
    }


def save_analysis_history(user_id: int, content_hash: str, source_url: Optional[str], result_payload: dict) -> None:
    conn = get_db_connection()
    conn.execute(
        """
        INSERT INTO analysis_history (user_id, content_hash, source_url, created_at, result_json)
        VALUES (?, ?, ?, ?, ?)
        """,
        (
            user_id,
            content_hash,
            source_url or "",
            datetime.now(timezone.utc).isoformat(),
            json.dumps(result_payload, ensure_ascii=False),
        ),
    )
    conn.commit()
    conn.close()

init_db()

# ============================================================
# CACHE / DETERMINISTIC ANALYSIS
# ============================================================

def stable_text(value: str) -> str:
    if not value:
        return ""
    return re.sub(r"\s+", " ", value.strip()).lower()


def analysis_cache_key(content: str, source_url: Optional[str] = None) -> str:
    normalized_content = stable_text(content)
    normalized_url = (source_url or "").strip().lower()
    raw = f"truthlens:v3|{normalized_url}|{normalized_content}"
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def infer_time_validity_and_validity(content: str, llm_validity: str, llm_time_validity: str) -> Tuple[str, str]:
    current_year = datetime.now(timezone.utc).year
    years = re.findall(r"\b(19\d{2}|20\d{2}|21\d{2})\b", content)
    year_values = [int(y) for y in years]

    event_indicators = [
        "deprem", "sarsıntı", "olay", "oldu", "yaşandı", "çarpışma",
        "felaket", "salgın", "havalimanı", "karar", "yapıldı", "açıklama"
    ]

    has_event_indicator = any(ind in stable_text(content) for ind in event_indicators)

    if year_values:
        event_year = max(year_values)
        if event_year < current_year:
            return (
                "Güncelliğini yitirmiş" if llm_validity.strip().lower() != "yanlış" else "Belirsiz",
                f"İçerik {event_year} yılına ait tarihli/olay bazlı ifadeler içeriyor; güncel olarak doğrulanması beklenmez ve geçmiş bir zaman dilimidir."
            )
        if event_year == current_year:
            return (
                "Geçerli",
                f"İçerik {event_year} yılı için tanımlanmış ve güncel bağlam kullanıyor."
            )
        return (
            "Belirsiz",
            f"İçerik yalnızca {event_year} yılına işaret ediyor; bu doğrulama için zaman denetimi ve güncel kanıt gerekir."
        )

    if has_event_indicator:
        return (
            "Belirsiz",
            "İçerik zaman bilgisi içermiyor; olayın gerçekleşme tarihi veya güncel olduğu bağlamı net değil. Tahmini zaman: güncel olay için tarihleme gerekiyor."
        )

    return (
        str(llm_validity).strip() or "Belirsiz",
        str(llm_time_validity).strip() or "İçerik için zaman geçerliliği çıkarılamadı."
    )


# ============================================================
# CLIENTS
# ============================================================

def get_llm_client() -> OpenAI:
    if not NARAROUTER_API_KEY:
        raise HTTPException(status_code=500, detail="NARAROUTER_API_KEY yapılandırılmamış.")
    return OpenAI(
        api_key=NARAROUTER_API_KEY,
        base_url="https://router.bynara.id/v1",
    )

def get_tavily_client() -> TavilyClient:
    if not TAVILY_API_KEY:
        raise HTTPException(status_code=500, detail="TAVILY_API_KEY yapılandırılmamış.")
    return TavilyClient(api_key=TAVILY_API_KEY)

# ============================================================
# URL & PAGE EXTRACTION
# ============================================================

def extract_url(text: str) -> Optional[str]:
    if not text:
        return None
    markdown_match = re.search(r"\[[^\]]*\]\((https?://[^)\s]+)\)", text, re.IGNORECASE)
    if markdown_match:
        return markdown_match.group(1).strip()
    match = re.search(r'https?://[^\s<>"\']+', text, re.IGNORECASE)
    if not match:
        return None
    url = match.group(0).strip().rstrip(".,;:!?)]}\"'" )
    return url

def is_nsosyal_url(url: str) -> bool:
    return bool(re.match(r"^https?://(?:www\.)?nsosyal\.com/", url, re.IGNORECASE))

def is_nsosyal_post_url(url: str) -> bool:
    return bool(re.match(r"^https?://(?:www\.)?nsosyal\.com/post/[0-9]+(?:/)?(?:\?.*)?$", url, re.IGNORECASE))

def fetch_webpage(url: str) -> Optional[str]:
    headers = {
        "User-Agent": (
            "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
            "AppleWebKit/537.36 (KHTML, like Gecko) "
            "Chrome/139.0.0.0 Safari/537.36"
        ),
        "Accept-Language": "tr-TR,tr;q=0.9,en;q=0.8",
    }
    try:
        response = requests.get(url, headers=headers, timeout=15, allow_redirects=True)
        response.raise_for_status()
        return response.text
    except Exception as e:
        print(f"[TruthLens] Web request error: {e}")
        return None

def get_json_ld_objects(soup: BeautifulSoup) -> List[dict]:
    objects = []
    for script in soup.find_all("script", type="application/ld+json"):
        content = (script.string or script.get_text() or "").strip()
        if not content:
            continue
        try:
            data = json.loads(content)
            if isinstance(data, dict):
                objects.append(data)
                graph = data.get("@graph")
                if isinstance(graph, list):
                    objects.extend([i for i in graph if isinstance(i, dict)])
            elif isinstance(data, list):
                objects.extend([i for i in data if isinstance(i, dict)])
        except Exception:
            continue
    return objects

def extract_nsosyal_social_media_post(soup: BeautifulSoup, requested_url: str) -> Optional[dict]:
    requested_post_id = None
    id_match = re.search(r"/post/([0-9]+)", requested_url, re.IGNORECASE)
    if id_match:
        requested_post_id = id_match.group(1)

    for obj in get_json_ld_objects(soup):
        obj_type = obj.get("@type")
        is_social = (isinstance(obj_type, list) and "SocialMediaPosting" in obj_type) or obj_type == "SocialMediaPosting"
        if not is_social:
            continue

        if requested_post_id:
            obj_url = str(obj.get("url", ""))
            obj_id = str(obj.get("@id", ""))
            if requested_post_id not in obj_url and requested_post_id not in obj_id:
                continue

        article_body = obj.get("articleBody")
        if not article_body or len(str(article_body).strip()) < 20:
            continue

        author = obj.get("author")
        if isinstance(author, dict):
            author = author.get("name", "")

        return {
            "text": str(article_body).strip(),
            "title": obj.get("headline"),
            "author": author,
            "datePublished": obj.get("datePublished"),
            "method": "json-ld-socialmediaposting",
        }
    return None

def get_meta_content(soup: BeautifulSoup, property_name: Optional[str] = None, name: Optional[str] = None) -> Optional[str]:
    tag = None
    if property_name:
        tag = soup.find("meta", attrs={"property": property_name})
    if not tag and name:
        tag = soup.find("meta", attrs={"name": name})
    if tag and tag.get("content"):
        return tag["content"].strip()
    return None

def extract_page_content(html: str, url: str) -> dict:
    soup = BeautifulSoup(html, "html.parser")

    social_post = extract_nsosyal_social_media_post(soup, url)
    if social_post:
        return {
            "success": True,
            "text": social_post["text"],
            "title": social_post.get("title"),
            "method": social_post["method"],
            "author": social_post.get("author"),
        }

    og_description = get_meta_content(soup, property_name="og:description")
    if og_description and len(og_description) >= 20:
        return {
            "success": True,
            "text": og_description[:20000],
            "title": get_meta_content(soup, property_name="og:title"),
            "method": "opengraph",
        }

    twitter_description = get_meta_content(soup, name="twitter:description")
    if twitter_description and len(twitter_description) >= 20:
        return {
            "success": True,
            "text": twitter_description[:20000],
            "title": get_meta_content(soup, name="twitter:title"),
            "method": "twitter",
        }

    meta_description = get_meta_content(soup, name="description")
    if meta_description and len(meta_description) >= 20:
        title = soup.title.string.strip() if soup.title and soup.title.string else None
        return {
            "success": True,
            "text": meta_description[:20000],
            "title": title,
            "method": "description",
        }

    for element in soup.find_all(["script", "style", "noscript", "svg", "iframe", "nav", "footer"]):
        element.decompose()

    page_text = re.sub(r"\s+", " ", soup.get_text(" ", strip=True)).strip()
    if len(page_text) >= 80:
        title = soup.title.string.strip() if soup.title and soup.title.string else None
        return {
            "success": True,
            "text": page_text[:20000],
            "title": title,
            "method": "html",
        }

    return {"success": False, "text": "", "method": "failed"}

def get_post_content(url: str) -> dict:
    if is_nsosyal_url(url) and not is_nsosyal_post_url(url):
        return {"success": False, "text": "", "reason": "NSosyal URL'si bir gönderi URL'si değil."}

    html = fetch_webpage(url)
    if not html:
        return {"success": False, "text": "", "reason": "Gönderi sayfasına erişilemedi."}

    result = extract_page_content(html, url)
    if not result["success"] or len(result["text"].strip()) < 20:
        return {"success": False, "text": "", "reason": "Sayfadan okunabilir gönderi içeriği alınamadı."}

    metadata = extract_page_metadata(html, url)

    return {
        "success": True,
        "text": result["text"].strip(),
        "title": result.get("title"),
        "method": result.get("method"),
        "reason": "",
        "metadata": metadata,
    }

def extract_page_metadata(html: str, url: str) -> dict:
    soup = BeautifulSoup(html, "html.parser")
    canonical = ""
    canonical_tag = soup.find("link", attrs={"rel": lambda v: v and "canonical" in str(v).lower()})
    if canonical_tag and canonical_tag.get("href"):
        canonical = urljoin(url, canonical_tag["href"].strip())

    title = ""
    if soup.title and soup.title.string:
        title = soup.title.string.strip()
    title = get_meta_content(soup, property_name="og:title") or title

    description = get_meta_content(soup, property_name="og:description") or get_meta_content(soup, name="description") or ""
    image_url = get_meta_content(soup, property_name="og:image") or get_meta_content(soup, name="twitter:image") or ""
    article_author = get_meta_content(soup, property_name="article:author") or get_meta_content(soup, name="author") or ""
    published_time = get_meta_content(soup, property_name="article:published_time") or get_meta_content(soup, property_name="og:updated_time") or ""
    site_name = get_meta_content(soup, property_name="og:site_name") or get_domain(url)

    if not published_time:
        for obj in get_json_ld_objects(soup):
            if obj.get("datePublished"):
                published_time = str(obj.get("datePublished"))
                break

    article_body = ""
    social_post = extract_nsosyal_social_media_post(soup, url)
    if social_post:
        article_body = social_post.get("text", "")
        if social_post.get("title") and not title:
            title = str(social_post.get("title", "")).strip()

    return {
        "title": title,
        "description": description,
        "canonical_url": canonical,
        "image_url": image_url,
        "author": article_author,
        "published_time": published_time,
        "site_name": site_name,
        "article_body": article_body,
    }

def extract_primary_image_url(url: str) -> str:
    html = fetch_webpage(url)
    if not html:
        return ""
    metadata = extract_page_metadata(html, url)
    return str(metadata.get("image_url", "") or "").strip()

def detect_ai_image(image_url: str) -> Optional[dict]:
    if not image_url_is_reasonable(image_url):
        return None
    if not SIGHTENGINE_API_USER or not SIGHTENGINE_API_SECRET:
        return None

    try:
        response = requests.get(
            "https://api.sightengine.com/1.0/check.json",
            params={
                "url": image_url,
                "models": "genai",
                "api_user": SIGHTENGINE_API_USER,
                "api_secret": SIGHTENGINE_API_SECRET,
            },
            timeout=20,
        )
        response.raise_for_status()
        payload = response.json() if response.content else {}
    except Exception as exc:
        print(f"[TruthLens] Sightengine error: {exc}")
        return None

    ai_probability = 0
    is_ai = None

    candidates = [
        payload.get("type", {}).get("ai_generated") if isinstance(payload.get("type"), dict) else None,
        payload.get("genai", {}).get("prob") if isinstance(payload.get("genai"), dict) else None,
        payload.get("genai", {}).get("ai_probability") if isinstance(payload.get("genai"), dict) else None,
        payload.get("genai", {}).get("ai_prob") if isinstance(payload.get("genai"), dict) else None,
    ]

    for value in candidates:
        if isinstance(value, (int, float)):
            numeric = float(value)
            if 0 <= numeric <= 1:
                numeric *= 100
            ai_probability = max(ai_probability, int(max(0, min(100, round(numeric)))))

    genai = payload.get("genai")
    if isinstance(genai, dict):
        for key in ("is_ai", "ai_generated", "classification"):
            value = genai.get(key)
            if isinstance(value, bool):
                is_ai = value
                break
            if isinstance(value, str):
                lowered = value.strip().lower()
                if lowered in {"ai", "ai-generated", "ai_generated", "generated"}:
                    is_ai = True
                    break
                if lowered in {"not-ai", "not ai", "human", "real", "non-ai"}:
                    is_ai = False
                    break

    if is_ai is None and ai_probability > 0:
        is_ai = ai_probability >= 50

    return {
        "ai_probability": ai_probability,
        "is_ai": bool(is_ai) if is_ai is not None else None,
        "error": None,
    }

def image_cache_key(image_url: str, source_url: str = "") -> str:
    raw = f"truthlens:image:v1|{normalize_url(source_url)}|{normalize_url(image_url)}"
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()

def image_url_is_reasonable(image_url: str) -> bool:
    return bool(re.match(r"^https?://", image_url or "", re.IGNORECASE))

def analyze_image_ai_probability(image_url: str, source_url: str = "") -> dict:
    if not image_url_is_reasonable(image_url):
        return {
            "image_ai_probability": 0,
            "image_analysis_available": False,
            "image_analysis_reasoning": "Geçerli bir görsel URL'si bulunamadı.",
            "image_url": "",
        }

    cache_key = image_cache_key(image_url, source_url)
    cached = ANALYSIS_CACHE.get(cache_key)
    if isinstance(cached, dict):
        return cached

    prompt = """
Bu görsel için yalnızca JSON döndür.
Görselin AI ile üretilmiş ya da ciddi şekilde AI ile değiştirilmiş olma ihtimalini tahmin et.
Kesin hüküm verme. Kısa, ihtiyatlı ve Türkçe yaz.

JSON:
{
  "image_ai_probability": 0-100,
  "image_analysis_available": true,
  "image_analysis_reasoning": "Kısa açıklama"
}
"""
    try:
        client = get_llm_client()
        completion = client.chat.completions.create(
            model=NARAROUTER_MODEL,
            messages=[
                {
                    "role": "user",
                    "content": [
                        {"type": "text", "text": prompt.strip()},
                        {"type": "image_url", "image_url": {"url": image_url}},
                    ],
                }
            ],
            temperature=0.1,
            response_format={"type": "json_object"},
        )
        raw = completion.choices[0].message.content or ""
        data = json.loads(raw)
        result = {
            "image_ai_probability": safe_score(data.get("image_ai_probability")),
            "image_analysis_available": bool(data.get("image_analysis_available", True)),
            "image_analysis_reasoning": str(data.get("image_analysis_reasoning", "")).strip() or "Görsel analizi tamamlandı.",
            "image_url": image_url,
        }
        ANALYSIS_CACHE[cache_key] = result
        return result
    except Exception as exc:
        print(f"[TruthLens] Image LLM error: {exc}")
        fallback = {
            "image_ai_probability": 0,
            "image_analysis_available": False,
            "image_analysis_reasoning": "Görsel analizi şu anda kullanılamıyor.",
            "image_url": image_url,
        }
        ANALYSIS_CACHE[cache_key] = fallback
        return fallback

def extract_claims_for_source_analysis(title: str, description: str, body: str) -> str:
    parts = [title, description, body]
    text = " ".join([part for part in parts if part]).strip()
    return re.sub(r"\s+", " ", text)[:250]

def parse_datetime_value(value: str) -> str:
    if not value:
        return ""
    return str(value).strip()

def build_source_chain(source_items: List[dict], current_source_label: str, current_source_date: str) -> dict:
    chain = []
    earliest = None
    for item in source_items:
        label = item.get("source", "")
        date = item.get("date", "")
        chain.append({"source": label, "date": date})
        if date and (earliest is None or date < earliest.get("date", "")):
            earliest = {"source": label, "date": date}

    if current_source_date:
        chain.append({"source": current_source_label, "date": current_source_date})
        if earliest is None or current_source_date < earliest.get("date", ""):
            earliest = {"source": current_source_label, "date": current_source_date}

    if earliest is None:
        earliest = {"source": "", "date": ""}

    source_probability = 0
    source_status = "uncertain"
    likely_original_source = earliest["source"] or ""
    if chain:
        source_probability = min(92, 55 + max(0, len(chain) - 1) * 8)
        if likely_original_source and likely_original_source != current_source_label:
            source_status = "derived"
        elif current_source_label:
            source_status = "original"

    reasoning = "Bulunabilen en eski kaynaklar kronolojik olarak sıralandı; kesin ilk kaynak iddiası yapılmadı."
    return {
        "source_status": source_status,
        "source_probability": source_probability,
        "likely_original_source": likely_original_source,
        "earliest_found_source": earliest["source"] or "",
        "earliest_found_date": earliest["date"] or "",
        "current_source_date": current_source_date or "",
        "source_chain": chain,
        "reasoning": reasoning,
    }

def analyze_source_chain(title: str, description: str, body: str, current_url: str, current_date: str = "", current_site: str = "") -> dict:
    query = extract_claims_for_source_analysis(title, description, body)
    if not query:
        return SourceAnalysis().model_dump()

    research = search_with_tavily(query, max_results=5)
    chain_items = []
    current_label = current_site or get_domain(current_url) or "Kullanıcının verdiği URL"
    current_date_value = parse_datetime_value(current_date)

    for item in research:
        item_url = item.get("url", "")
        item_title = item.get("title", "") or get_domain(item_url) or "Kaynak"
        published = ""
        try:
            html = fetch_webpage(item_url)
            if html:
                meta = extract_page_metadata(html, item_url)
                published = parse_datetime_value(meta.get("published_time", ""))
        except Exception:
            published = ""
        chain_items.append({
            "source": item_title,
            "date": published or "",
        })

    built = build_source_chain(chain_items, current_label, current_date_value)
    return built

# ============================================================
# TAVILY + GROQ
# ============================================================

def search_with_tavily(query: str, max_results: int = 5) -> List[dict]:
    client = get_tavily_client()
    try:
        response = client.search(
            query=query,
            search_depth="basic",
            max_results=max_results,
            include_answer=False,
        )
        results = []
        for item in response.get("results", []):
            results.append({
                "title": item.get("title", ""),
                "url": item.get("url", ""),
                "content": (item.get("content") or "")[:800],
            })
        return results
    except Exception as e:
        print(f"[TruthLens] Tavily error: {e}")
        return []

def call_llm(messages: list, temperature: float = 0.2) -> str:
    client = get_llm_client()
    try:
        completion = client.chat.completions.create(
            model=NARAROUTER_MODEL,
            messages=messages,
            temperature=temperature,
            response_format={"type": "json_object"},
        )
        return completion.choices[0].message.content or ""
    except Exception as e:
        print(f"[TruthLens] NaraRouter error: {e}")
        raise HTTPException(status_code=502, detail=f"NaraRouter hatası: {str(e)}")

def safe_score(value, default: int = 0) -> int:
    try:
        return max(0, min(100, int(value)))
    except Exception:
        return default

def get_domain(url: str) -> str:
    try:
        return urlparse(url).netloc.lower().strip()
    except Exception:
        return ""


def source_domain_looks_low_quality(url: str, title: str = "") -> Tuple[bool, str]:
    host = get_domain(url)
    if not host:
        return True, "URL alan adı okunamadı."

    lowered_host = host.lower()
    lowered_title = (title or "").lower()

    listing_domains = (
        "sahibinden.com",
        "sahibinden.com.tr",
        "emlak.com",
        "hepsiemlak.com",
        "ziraatemlak.com",
    )

    listing_terms = (
        "ilan",
        "satılık",
        "kiralık",
        "emlak",
        "konut",
        "daire",
        "ev fiyat",
    )

    if any(blocked in lowered_host for blocked in listing_domains):
        return True, "İlan / emlak / alışveriş platformu. Bu destekleyici veri kaynağı olarak uygun değil."

    if any(term in lowered_title for term in listing_terms):
        return True, "Başlık ilan veya satış bağlamı taşıyor. Analiz için uygun olmayan içerik türü."

    if any(term in lowered_host for term in ("facebook.com", "instagram.com", "x.com", "tiktok.com")):
        return True, "Sosyal medya profili veya sosyal paylaşım platformu. Doğrulama kaynağı olmaktan uzaktır."

    return False, ""


def adjust_source_reliability(url: str, title: str, reliability: int = 50) -> Tuple[int, str]:
    host = get_domain(url)
    low_reliability = reliability

    if not host:
        return 0, "URL alan adı bulunamadı."

    if "wikipedia.org" in host:
        return 88, "Vikipedi gibi genel bilgi sayfası; bağlam ve kaynak olarak kullanılabilir."
    if any(domain in host for domain in ("gov.tr", "gov", "bloomberg.com", "reuters.com", "apnews.com", "bbc.com", "bbc.co.uk", "nytimes.com", "washingtonpost.com", "theguardian.com", "dw.com")):
        return 90, "Niteliği yüksek haber veya resmi veri kaynağı."
    if any(domain in host for domain in ("trthaber.com", "aa.com.tr", "hurriyet.com.tr", "cnnturk.com", "milliyet.com.tr", "ntv.com.tr", "sozcu.com.tr", "t24.com.tr")):
        return 80, "Yerel haber kaynağı; doğrulanabilir görünüm taşıyor."
    if any(domain in host for domain in ("blogspot.com", "medium.com", "substack.com")):
        return 50, "Kişisel yayın veya yorum platformu. Güven oranı düşüktür."

    if low_reliability < 25:
        return 25, "Kaynak güvenilirlik sinyali zayıf."

    return max(0, min(100, reliability)), "Kaynak, ara bulgu dizisi içinde değerlendirildi."


def normalize_url(url: str) -> str:
    if not url:
        return ""
    try:
        return url.strip().rstrip("/").lower()
    except Exception:
        return ""


def filter_sources_against_research_urls(source_list, research_urls: Set[str]) -> List[Source]:
    allowed = []
    for source in source_list:
        source_url = getattr(source, "url", "")
        source_url_normalized = normalize_url(source_url)
        if not source_url_normalized:
            continue
        if source_url_normalized in research_urls:
            allowed.append(source)
    return allowed


def clean_source_list(source_list) -> List[Source]:
    clean_sources = []
    seen_urls = set()
    if not isinstance(source_list, list):
        return clean_sources

    for source in source_list:
        if not isinstance(source, dict):
            continue
        title = str(source.get("title", "")).strip()
        source_url = str(source.get("url", "")).strip()
        relevance = str(source.get("relevance", "")).strip()
        reliability_reason = str(source.get("reliability_reason", "")).strip()

        if not title or not re.match(r"^https?://", source_url, re.IGNORECASE):
            continue

        normalized = source_url.rstrip("/").lower()
        if normalized in seen_urls:
            continue
        seen_urls.add(normalized)

        is_low_quality, low_reason = source_domain_looks_low_quality(source_url, title)
        if is_low_quality:
            print(f"[TruthLens] Source filtered: {source_url} :: {low_reason}")
            continue

        try:
            reliability = int(source.get("reliability", 50))
        except Exception:
            reliability = 50
        reliability = max(0, min(100, reliability))

        reliability, source_reliability_reason = adjust_source_reliability(
            source_url,
            title,
            reliability,
        )

        if not reliability_reason:
            reliability_reason = source_reliability_reason

        if reliability <= 0:
            continue

        clean_sources.append(Source(
            title=title,
            url=source_url,
            relevance=relevance,
            reliability=reliability,
            reliability_reason=reliability_reason,
        ))
    return clean_sources

# ============================================================
# ANA ANALİZ
# ============================================================

def run_analysis(analyzed_content: str, source_url: Optional[str] = None) -> AnalysisResponse:
    key = analysis_cache_key(analyzed_content, source_url)
    if key in ANALYSIS_CACHE:
        return ANALYSIS_CACHE[key]

    analyzed_excerpt = analyzed_content[:350]
    prompt = f"""
Sen TruthLens AI adlı Türkçe bilgi doğrulama sistemisin.
Sadece JSON döndür. Kısa, güvenli ve ihtiyatlı ol.

İçerik:
\"\"\"
{analyzed_excerpt}
\"\"\"

Kaynak URL: {source_url or "Yok"}

Kurallar:
- Aşırı uzun açıklama yazma.
- Kaynak uydurma. sources boş olabilir.
- Sağladığın skorlar risk tahminidir, kesin hüküm değildir.

JSON formatı:
{{
  "score": 0-100,
  "manipulation": 0-100,
  "clickbait": 0-100,
  "result": "Doğru / Yanıltıcı / Yanlış / Kanıt yetersiz / Kısmen doğru / Büyük ölçüde doğru",
  "explanation": "Kısa Türkçe açıklama.",
  "score_breakdown": "Kısa puan kırılımı.",
  "validity": "Geçerli / Güncelliğini yitirmiş / Belirsiz",
  "emotion": "Nötr / Korku / Öfke / Ümit / Manipülatif / Endişe / Heyecan / Diğer",
  "time_validity": "Kısa zaman/geçerlilik notu.",
  "polarization_risk": 0-100,
  "echo_chamber": "Kısa risk notu.",
  "ai_rewrite": "Kısa tarafsız yeniden yazım.",
  "social_risk_summary": "Kısa sosyal risk özeti.",
  "toxicity": {{
    "insult": 0-100,
    "bullying": 0-100,
    "hate_speech": 0-100,
    "targeted_person_or_group": "Genel",
    "risk_level": "Düşük / Orta / Yüksek",
    "context_note": "Kısa bağlam notu."
  }},
  "claims": [],
  "context": "Ek bağlam gerekmiyor.",
  "sources": [],
  "supporting_sources": [],
  "contradicting_sources": []
}}
"""
    final_raw = call_llm([{"role": "user", "content": prompt}], temperature=0.1)
    try:
        data = json.loads(final_raw)
    except Exception:
        raise HTTPException(status_code=502, detail="LLM JSON döndürmedi.")

    data["validity"], data["time_validity"] = infer_time_validity_and_validity(
        analyzed_content,
        str(data.get("validity", "Belirsiz")).strip(),
        str(data.get("time_validity", "Tarihsel geçerlilik bilgisi çıkarılamadı.")).strip(),
    )

    raw_sources = clean_source_list(data.get("sources", []))
    raw_supporting_sources = clean_source_list(data.get("supporting_sources", []))
    raw_contradicting_sources = clean_source_list(data.get("contradicting_sources", []))
    sources = raw_sources
    supporting_sources = raw_supporting_sources
    contradicting_sources = raw_contradicting_sources

    toxicity_data = data.get("toxicity") or {}
    toxicity = ToxicityAnalysis(
        insult=safe_score(toxicity_data.get("insult")),
        bullying=safe_score(toxicity_data.get("bullying")),
        hate_speech=safe_score(toxicity_data.get("hate_speech")),
        targeted_person_or_group=str(toxicity_data.get("targeted_person_or_group", "Genel")).strip() or "Genel",
        risk_level=str(toxicity_data.get("risk_level", "Düşük")).strip() or "Düşük",
        context_note=str(toxicity_data.get("context_note", "Bağlam değerlendirmesi yapılmadı.")).strip() or "Bağlam değerlendirmesi yapılmadı.",
    )

    analysis_result = AnalysisResponse(
        score=safe_score(data.get("score")),
        manipulation=safe_score(data.get("manipulation")),
        clickbait=safe_score(data.get("clickbait")),
        result=str(data.get("result", "")).strip(),
        explanation=str(data.get("explanation", "")).strip(),
        score_breakdown=str(data.get("score_breakdown", "")).strip(),
        validity=str(data.get("validity", "Belirsiz")).strip(),
        emotion=str(data.get("emotion", "Nötr")).strip(),
        time_validity=str(data.get("time_validity", "Tarihsel geçerlilik bilgisi çıkarılamadı.")).strip(),
        polarization_risk=safe_score(data.get("polarization_risk")),
        echo_chamber=str(data.get("echo_chamber", "Tek yönlü içerik tüketim riski belirsiz.")).strip(),
        ai_rewrite=str(data.get("ai_rewrite", "Bu paylaşım için daha tarafsız öneri üretilemedi.")).strip(),
        social_risk_summary=str(data.get("social_risk_summary", "Sosyal etki analizi yapılamadı.")).strip(),
        toxicity=toxicity,
        claims=[str(c).strip() for c in data.get("claims", []) if str(c).strip()],
        context=str(data.get("context", "Ek bağlam gerekmiyor.")).strip(),
        sources=sources,
        supporting_sources=supporting_sources,
        contradicting_sources=contradicting_sources,
    )

    ANALYSIS_CACHE[key] = analysis_result
    return analysis_result

# ============================================================
# ENDPOINTS
# ============================================================

@app.get("/")
def root():
    return {
        "status": "online",
        "service": "TruthLens AI",
        "version": "3.1.0",
        "engine": "NaraRouter + Tavily",
    }

@app.get("/health")
def health():
    return {
        "status": "healthy",
        "nararouter_configured": bool(NARAROUTER_API_KEY),
        "tavily_configured": bool(TAVILY_API_KEY),
        "model": NARAROUTER_MODEL,
    }

@app.post("/register")
def register(request: RegisterRequest):
    conn = get_db_connection()
    existing = conn.execute("SELECT id FROM users WHERE email = ?", (request.email.strip().lower(),)).fetchone()
    if existing:
        conn.close()
        raise HTTPException(status_code=409, detail="Bu e-posta adresi zaten kayıtlı.")

    created_at = datetime.now(timezone.utc).isoformat()
    conn.execute(
        "INSERT INTO users (name, email, password_hash, created_at) VALUES (?, ?, ?, ?)",
        (request.name.strip(), request.email.strip().lower(), hash_password(request.password), created_at),
    )
    conn.commit()
    user_id = conn.execute("SELECT id FROM users WHERE email = ?", (request.email.strip().lower(),)).fetchone()["id"]
    token = create_token()
    expires_at = (datetime.now(timezone.utc).isoformat())
    conn.execute(
        "INSERT INTO sessions (user_id, token, created_at, expires_at) VALUES (?, ?, ?, ?)",
        (user_id, token, created_at, expires_at),
    )
    conn.commit()
    conn.close()

    return {
        "status": "ok",
        "token": token,
        "user": {
            "id": user_id,
            "name": request.name.strip(),
            "email": request.email.strip().lower(),
        },
    }

@app.post("/login")
def login(request: LoginRequest):
    conn = get_db_connection()
    row = conn.execute(
        "SELECT id, name, email FROM users WHERE email = ? AND password_hash = ?",
        (request.email.strip().lower(), hash_password(request.password)),
    ).fetchone()

    if not row:
        conn.close()
        raise HTTPException(status_code=401, detail="E-posta veya şifre yanlış.")

    token = create_token()
    created_at = datetime.now(timezone.utc).isoformat()
    expires_at = created_at
    conn.execute(
        "INSERT INTO sessions (user_id, token, created_at, expires_at) VALUES (?, ?, ?, ?)",
        (row["id"], token, created_at, expires_at),
    )
    conn.commit()
    conn.close()

    return {
        "status": "ok",
        "token": token,
        "user": {
            "id": row["id"],
            "name": row["name"],
            "email": row["email"],
        },
    }

@app.get("/me")
def me(request: Request):
    user = get_current_user_from_request(request)
    if not user:
        raise HTTPException(status_code=401, detail="Oturum doğrulanamadı.")
    return {"user": user}

@app.get("/history")
def history(request: Request):
    user = get_current_user_from_request(request)
    if not user:
        raise HTTPException(status_code=401, detail="Oturum doğrulanamadı.")

    conn = get_db_connection()
    rows = conn.execute(
        "SELECT content_hash, source_url, created_at, result_json FROM analysis_history WHERE user_id = ? ORDER BY id DESC LIMIT 20",
        (user["id"],),
    ).fetchall()
    conn.close()

    return {
        "items": [
            {
                "content_hash": r["content_hash"],
                "source_url": r["source_url"],
                "created_at": r["created_at"],
                "result": json.loads(r["result_json"]),
            }
            for r in rows
        ]
    }

@app.post("/analyze", response_model=AnalysisResponse)
def analyze(request_body: AnalysisRequest, request: Request):
    original = request_body.content.strip()
    if not original:
        raise HTTPException(status_code=400, detail="İçerik boş olamaz.")

    url = extract_url(original)
    analyzed_content = original
    source_url = None
    post = {}

    if url:
        source_url = url
        print(f"[TruthLens] URL bulundu: {url}")
        post = get_post_content(url)
        if not post["success"]:
            raise HTTPException(
                status_code=422,
                detail=f"Gönderinin içeriğine erişilemedi. Nedeni: {post['reason']}",
            )
        analyzed_content = post["text"]
        print(f"[TruthLens] İçerik alındı ({post.get('method')}), uzunluk: {len(analyzed_content)}")

    result = run_analysis(analyzed_content, source_url)

    image_ai_probability = 0
    image_is_ai = None
    image_analysis_available = False
    source_analysis = SourceAnalysis()

    if url:
        metadata = (post.get("metadata") or {}) if "post" in locals() else {}
        primary_image = str(metadata.get("image_url", "") or "").strip()
        if primary_image:
            image_analysis_available = True
            image_analysis = detect_ai_image(primary_image)
            if image_analysis:
                image_ai_probability = safe_score(image_analysis.get("ai_probability"))
                image_is_ai = image_analysis.get("is_ai")

        source_analysis = analyze_source_chain(
            title=str((metadata.get("title") or post.get("title") or "") if "post" in locals() else ""),
            description=str(metadata.get("description", "") or ""),
            body=analyzed_content,
            current_url=source_url or url,
            current_date=str(metadata.get("published_time", "") or ""),
            current_site=str(metadata.get("site_name", "") or ""),
        )

    result = result.model_copy(update={
        "image_ai_probability": image_ai_probability,
        "image_is_ai": image_is_ai,
        "image_analysis_available": image_analysis_available,
        "source_analysis": source_analysis if isinstance(source_analysis, SourceAnalysis) else SourceAnalysis(**source_analysis),
    })

    user = get_current_user_from_request(request)
    if user:
        content_hash = analysis_cache_key(analyzed_content, source_url)
        result_payload = json.loads(result.model_dump_json())
        save_analysis_history(user["id"], content_hash, source_url, result_payload)

    return result

@app.post("/analyze-url", response_model=AnalysisResponse)
def analyze_url(payload: dict, request: Request):
    url = str(payload.get("url", "")).strip()
    if not url:
        raise HTTPException(status_code=400, detail="URL gerekli.")
    return analyze(AnalysisRequest(content=url), request)


@app.get("/demo-feed")
def demo_feed():
    posts = build_demo_feed()
    return {
        "posts": posts,
        "summary": summarize_demo_feed(posts),
    }


@app.get("/bluesky-feed")
def bluesky_feed(limit: int = BLUESKY_FEED_LIMIT):
    payload = fetch_bluesky_feed(limit=limit)
    if payload.get("posts"):
        return payload

    demo_posts = build_demo_feed()
    return {
        "posts": demo_posts,
        "summary": summarize_demo_feed(demo_posts),
        "provider": "demo-fallback",
        "warning": payload.get("warning") or "Bluesky live akışı alınamadı, demo akış gösteriliyor.",
    }


@app.get("/bluesky-status")
def bluesky_status():
    return {
        "configured": bool(BLUESKY_HANDLE and BLUESKY_APP_PASSWORD),
        "handle": bool(BLUESKY_HANDLE),
        "password_configured": bool(BLUESKY_APP_PASSWORD),
        "provider": "bluesky" if bool(BLUESKY_HANDLE and BLUESKY_APP_PASSWORD) else "demo",
    }


@app.post("/demo-feed/analyze")
def demo_feed_analyze(payload: dict):
    content = str(payload.get("content", "")).strip()
    if not content:
        raise HTTPException(status_code=400, detail="Analiz edilecek içerik gerekli.")

    post = {
        "id": payload.get("id") or f"demo-{uuid.uuid4().hex[:8]}",
        "author": payload.get("author") or "demo_user",
        "handle": payload.get("handle") or "@demo_user",
        "content": content,
        "tag": payload.get("tag") or "Genel",
        "truthlens_score": max(0, min(100, int(payload.get("truthlens_score", 60)))),
        "manipulation": max(0, min(100, int(payload.get("manipulation", 42)))),
        "clickbait": max(0, min(100, int(payload.get("clickbait", 31)))),
        "emotion": payload.get("emotion") or "Nötr",
        "risk_level": payload.get("risk_level") or "Orta",
        "reason": payload.get("reason") or "Bağlam ve risk değerlendirmesi hazırlandı.",
        "toxicity": payload.get("toxicity") or {
            "insult": 0,
            "bullying": 0,
            "hate_speech": 0,
            "targeted_person_or_group": "Genel",
            "risk_level": "Düşük",
            "context_note": "Bağlam değerlendirmesi hazırlandı."
        },
    }
    return {"post": post, "summary": summarize_demo_feed([post])}


@app.post("/analyze-image", response_model=ImageAnalysis)
def analyze_image(payload: ImageAnalysisRequest):
    image_url = payload.image_url.strip()
    source_url = payload.source_url.strip()
    if not image_url:
        raise HTTPException(status_code=400, detail="Görsel URL gerekli.")

    result = detect_ai_image(image_url)
    if not result:
        return ImageAnalysis(
            image_ai_probability=0,
            image_is_ai=None,
            image_url=image_url,
        )
    return ImageAnalysis(
        image_ai_probability=safe_score(result.get("ai_probability")),
        image_is_ai=result.get("is_ai"),
        image_url=image_url,
    )


if __name__ == "__main__":
    import uvicorn
    uvicorn.run("main:app", host="0.0.0.0", port=8000, reload=True)
