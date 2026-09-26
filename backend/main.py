import os
os.environ["HF_HOME"] = "/tmp/huggingface_cache"
os.environ["TRANSFORMERS_CACHE"] = "/tmp/huggingface_cache"
import json
import re
import hashlib
import sqlite3
import uuid
import threading
import concurrent.futures
import time
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Literal, Optional, Set, Tuple
from urllib.parse import urlparse
from urllib.parse import urljoin
from io import BytesIO

import requests
from bs4 import BeautifulSoup
from dotenv import load_dotenv
from fastapi import FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field
from tavily import TavilyClient

try:
    import torch
    from transformers import AutoTokenizer, AutoModelForSequenceClassification
    from peft import PeftModel
except Exception:
    torch = None
    AutoTokenizer = None
    AutoModelForSequenceClassification = None
    PeftModel = None
    MODEL_IMPORT_ERROR = "torch/transformers/peft bağımlılıkları import edilemedi."
else:
    MODEL_IMPORT_ERROR = ""
from atproto import Client

try:
    from PIL import Image
    import pytesseract
except Exception:
    Image = None
    pytesseract = None

load_dotenv(os.path.join(os.path.dirname(__file__), ".env"))

GOOGLE_API_KEY = os.getenv("GOOGLE_API_KEY") or os.getenv("GEMINI_API_KEY")
GEMINI_MODEL = os.getenv("GEMINI_MODEL", "gemini-3.5-flash-lite")
GEMINI_API_BASE = os.getenv("GEMINI_API_BASE", "https://generativelanguage.googleapis.com/v1beta")
TOXICITY_MODEL_ID = os.getenv("TOXICITY_MODEL_ID", "Doruk2404/truthlens-toxic-lora")
TOXICITY_BASE_MODEL = os.getenv("TOXICITY_BASE_MODEL", "dbmdz/bert-base-turkish-cased")
HF_TOKEN = os.getenv("HF_TOKEN") or None
TOXICITY_MAX_LENGTH = int(os.getenv("TOXICITY_MAX_LENGTH", "256"))
INSULT_MODEL_ID = os.getenv("INSULT_MODEL_ID", "nanelimon/bert-base-turkish-offensive")
BULLYING_MODEL_ID = os.getenv("BULLYING_MODEL_ID", "nanelimon/bert-base-turkish-bullying")
HATE_MODEL_ID = os.getenv("HATE_MODEL_ID", "ctoraman/hate-speech-berturk")
AUXILIARY_MODEL_MAX_LENGTH = int(os.getenv("AUXILIARY_MODEL_MAX_LENGTH", "256"))
TAVILY_API_KEY = os.getenv("TAVILY_API_KEY")
SIGHTENGINE_API_USER = (
    os.getenv("SIGHTENGINE_API_USER")
    or os.getenv("SIGHTENGINE_USER")
    or os.getenv("SIGHTENGINE_API_KEY")
)
SIGHTENGINE_API_SECRET = (
    os.getenv("SIGHTENGINE_API_SECRET")
    or os.getenv("SIGHTENGINE_SECRET")
)

BLUESKY_HANDLE = os.getenv("BLUESKY_HANDLE")
BLUESKY_APP_PASSWORD = os.getenv("BLUESKY_APP_PASSWORD")
BLUESKY_FEED_LIMIT = int(os.getenv("BLUESKY_FEED_LIMIT", "5"))
BLUESKY_FEED_MAX_LIMIT = int(os.getenv("BLUESKY_FEED_MAX_LIMIT", "20"))
DB_PATH = os.getenv("DATABASE_PATH", os.path.join(os.path.dirname(__file__), "truthlens.db"))

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
    # Frontend mevcut sözleşmede content kullanır; teknik örneklerdeki text de kabul edilir.
    content: Optional[str] = Field(default=None, min_length=1, max_length=10000)
    text: Optional[str] = Field(default=None, min_length=1, max_length=10000)
    language: Literal["tr", "en"] = "tr"

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
    url: str = ""
    date: str = ""
    platform: str = ""
    author: str = ""
    is_likely_primary: bool = False
    primary_probability: int = 0
    match_probability: int = 0

class SourceAnalysis(BaseModel):
    source_status: str = "uncertain"
    source_probability: int = 0
    likely_original_source: str = ""
    likely_original_author: str = ""
    likely_original_url: str = ""
    likely_original_date: str = ""
    likely_original_excerpt: str = ""
    likely_original_platform: str = ""
    earliest_found_source: str = ""
    earliest_found_date: str = ""
    current_source_date: str = ""
    source_chain: List[SourceChainItem] = Field(default_factory=list)
    reasoning: str = ""

class ToxicityAnalysis(BaseModel):
    insult: int = 0
    bullying: int = 0
    hate_speech: int = 0
    targeted_person_or_group: str = "Genel"
    risk_level: str = "Düşük"
    context_note: str = "Bağlam değerlendirmesi yapılmadı."


class AuxiliaryToxicityModels(BaseModel):
    insult: Dict[str, Any] = Field(default_factory=dict)
    bullying: Dict[str, Any] = Field(default_factory=dict)
    hate_speech: Dict[str, Any] = Field(default_factory=dict)
    available: bool = False
    error: str = ""


class ImageAnalysis(BaseModel):
    image_ai_probability: int = 0
    image_is_ai: Optional[bool] = None
    image_analysis_available: bool = False
    image_analysis_reasoning: str = ""
    visible_text: str = ""
    image_toxicity: ToxicityAnalysis = Field(default_factory=ToxicityAnalysis)
    image_url: str = ""

class ImageAnalysisRequest(BaseModel):
    image_url: str = Field(min_length=5, max_length=5000)
    source_url: str = Field(default="", max_length=5000)

class ModerationDecision(BaseModel):
    """
    Toksisite skorlarını somut bir platform kararına dönüştürür.
    Kurallar deterministiktir (LLM'e bağlı değildir) -> test edilebilir,
    açıklanabilir ve tutarlıdır. Geri dönüşü olmayan aksiyonlar (kaldırma)
    her zaman insan onayına bağlanır; sistem otomatik silme yapmaz.
    """
    action: str = "izin_ver"  # izin_ver | etiketle | gizle_ve_incele | kaldirma_oner
    action_label: str = "İçeriğe izin verildi"
    reason: str = ""
    requires_human_review: bool = False
    appeal_eligible: bool = False
    aggregate_risk: int = 0

class VerificationBadge(BaseModel):
    verified: bool = False
    label: str = "TruthLens doğrulaması tamamlanmadı"
    short_label: str = "Doğrulanmadı"
    reasons: List[str] = Field(default_factory=list)


class AnalysisResponse(BaseModel):
    content_hash: str = ""
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
    toxicity_models: AuxiliaryToxicityModels = Field(default_factory=AuxiliaryToxicityModels)
    moderation: ModerationDecision = Field(default_factory=ModerationDecision)
    verification: VerificationBadge = Field(default_factory=VerificationBadge)

    claims: List[str]
    context: str

    sources: List[Source]
    supporting_sources: List[Source]
    contradicting_sources: List[Source]
    image_ai_probability: int = 0
    image_is_ai: Optional[bool] = None
    image_analysis_available: bool = False
    image_text: str = ""
    image_toxicity: ToxicityAnalysis = Field(default_factory=ToxicityAnalysis)
    image_moderation_note: str = ""
    source_analysis: SourceAnalysis = Field(default_factory=SourceAnalysis)
    # Yeni pipeline alanları; mevcut TruthLens kartlarıyla geriye dönük uyumludur.
    toxicity_label: str = "notoxic"
    toxicity_confidence: float = 0.0
    claim: str = ""
    truthfulness: str = "Kanıt yetersiz"
    truthfulness_confidence: float = 0.0
    evidence: List[dict] = Field(default_factory=list)
    toxicity_engine: str = "fallback"
    # Jüride ve hata ayıklamada provider adımlarının gerçekten çalışıp çalışmadığını gösterir.
    pipeline_status: Dict[str, object] = Field(default_factory=dict)

ANALYSIS_CACHE: Dict[str, object] = {}
LAST_TAVILY_STATUS: Dict[str, object] = {"status": "idle", "count": 0, "query": ""}


class ToxicityModelService:
    """Türkçe BERT + LoRA modelini süreç başına bir kez yükler ve yeniden kullanır."""

    def __init__(self) -> None:
        self.model = None
        self.tokenizer = None
        self.device = "cpu"
        self.available = False
        self.error = ""
        self._lock = threading.Lock()

    def load_once(self) -> bool:
        if self.available:
            return True
        with self._lock:
            if self.available:
                return True
            if not all((torch, AutoTokenizer, AutoModelForSequenceClassification, PeftModel)):
                self.error = "torch/transformers/peft bağımlılıkları kurulu değil."
                return False
            try:
                self.device = "cuda" if torch.cuda.is_available() else "cpu"
                hf_kwargs = {"token": HF_TOKEN} if HF_TOKEN else {}
                self.tokenizer = AutoTokenizer.from_pretrained(
                    TOXICITY_BASE_MODEL,
                    **hf_kwargs,
                )
                base = AutoModelForSequenceClassification.from_pretrained(
                    TOXICITY_BASE_MODEL,
                    num_labels=2,
                    **hf_kwargs,
                )
                self.model = PeftModel.from_pretrained(
                    base,
                    TOXICITY_MODEL_ID,
                    is_trainable=False,
                    **hf_kwargs,
                )
                self.model.to(self.device)
                self.model.eval()
                self.available = True
                print(
                    f"[TruthLens] FINE_TUNED_BERT_LORA ready: {TOXICITY_MODEL_ID} "
                    f"({TOXICITY_BASE_MODEL}) on {self.device}"
                )
                return True
            except Exception as exc:
                self.error = str(exc)
                self.model = None
                self.tokenizer = None
                print(f"[TruthLens] Custom toxicity model load error: {exc}")
                return False

    def predict(self, text: str) -> dict:
        if not self.load_once() or not text.strip():
            return {
                "available": False,
                "label": "notoxic",
                "confidence": 0.0,
                "error": self.error or MODEL_IMPORT_ERROR,
            }
        try:
            encoded = self.tokenizer(
                text[:10000],
                return_tensors="pt",
                truncation=True,
                max_length=TOXICITY_MAX_LENGTH,
            )
            encoded = {key: value.to(self.device) for key, value in encoded.items()}
            with torch.no_grad():
                logits = self.model(**encoded).logits
                probabilities = torch.softmax(logits, dim=-1)[0]
            toxic_index = 1
            id2label = getattr(self.model.config, "id2label", {}) or {}
            for index, label in id2label.items():
                if "toxic" in str(label).lower() or "tox" in str(label).lower():
                    toxic_index = int(index)
                    break
            toxic_probability = float(probabilities[toxic_index].item())
            label = "toxic" if toxic_probability >= 0.5 else "notoxic"
            confidence = toxic_probability if label == "toxic" else 1.0 - toxic_probability
            return {
                "available": True,
                "label": label,
                "confidence": max(0.0, min(1.0, confidence)),
                "toxic_probability": toxic_probability,
            }
        except Exception as exc:
            self.error = str(exc)
            print(f"[TruthLens] Custom toxicity inference error: {exc}")
            return {
                "available": False,
                "label": "notoxic",
                "confidence": 0.0,
                "error": self.error,
            }


class MultiClassModelService:
    def __init__(self, model_id: str, engine: str) -> None:
        self.model_id = model_id
        self.engine = engine
        self.model = None
        self.tokenizer = None
        self.device = "cpu"
        self.available = False
        self.error = ""
        self.id2label: Dict[int, str] = {}
        self._lock = threading.Lock()

    def load_once(self) -> bool:
        if self.available:
            return True
        with self._lock:
            if self.available:
                return True
            if not all((torch, AutoTokenizer, AutoModelForSequenceClassification)):
                self.error = "torch/transformers bağımlılıkları kurulu değil."
                return False
            try:
                self.device = "cuda" if torch.cuda.is_available() else "cpu"
                hf_kwargs = {"token": HF_TOKEN} if HF_TOKEN else {}
                self.tokenizer = AutoTokenizer.from_pretrained(self.model_id, **hf_kwargs)
                self.model = AutoModelForSequenceClassification.from_pretrained(self.model_id, **hf_kwargs)
                self.model.to(self.device)
                self.model.eval()
                raw_id2label = getattr(self.model.config, "id2label", {}) or {}
                self.id2label = {int(index): str(label) for index, label in raw_id2label.items()}
                self.available = True
                print(f"[TruthLens] {self.engine} ready: {self.model_id} labels={self.id2label} on {self.device}")
                return True
            except Exception as exc:
                self.error = str(exc)
                self.model = None
                self.tokenizer = None
                print(f"[TruthLens] {self.engine} load error ({self.model_id}): {exc}")
                return False

    def predict(self, text: str) -> dict:
        if not self.load_once() or not text.strip():
            return {
                "available": False,
                "engine": "fallback",
                "model_id": self.model_id,
                "raw": {},
                "error": self.error or MODEL_IMPORT_ERROR,
            }
        try:
            encoded = self.tokenizer(text[:10000], return_tensors="pt", truncation=True, max_length=AUXILIARY_MODEL_MAX_LENGTH)
            encoded = {key: value.to(self.device) for key, value in encoded.items()}
            with torch.no_grad():
                probabilities = torch.softmax(self.model(**encoded).logits[0], dim=-1)
            raw = {self.id2label.get(index, f"LABEL_{index}"): float(probabilities[index].item()) * 100 for index in range(len(probabilities))}
            predicted_index = int(torch.argmax(probabilities).item())
            return {
                "available": True,
                "engine": self.engine,
                "model_id": self.model_id,
                "label": self.id2label.get(predicted_index, f"LABEL_{predicted_index}"),
                "confidence": float(probabilities[predicted_index].item()) * 100,
                "raw": raw,
            }
        except Exception as exc:
            self.error = str(exc)
            print(f"[TruthLens] {self.engine} inference error ({self.model_id}): {exc}")
            return {
                "available": False,
                "engine": "fallback",
                "model_id": self.model_id,
                "raw": {},
                "error": self.error,
            }


TOXICITY_SERVICE = ToxicityModelService()
INSULT_SERVICE = MultiClassModelService(INSULT_MODEL_ID, "insult_model")
BULLYING_SERVICE = MultiClassModelService(BULLYING_MODEL_ID, "bullying_model")
HATE_SERVICE = MultiClassModelService(HATE_MODEL_ID, "hate_model")


def custom_text_toxicity(text: str) -> Tuple[ToxicityAnalysis, str, float, bool]:
    """Öncelik özel modele aittir; model yoksa yalnızca kontrollü fallback kullanılır."""
    prediction = TOXICITY_SERVICE.predict(text)
    if not prediction.get("available"):
        fallback = ToxicityAnalysis(
            insult=0,
            bullying=0,
            hate_speech=0,
            targeted_person_or_group="Genel",
            risk_level="Düşük",
            context_note="Genel toxicity modeli kullanılamadı; skor üretilmedi.",
        )
        return fallback, "notoxic", 0.0, False

    toxic = prediction["label"] == "toxic"
    confidence = float(prediction["confidence"])
    if toxic:
        # Model yalnızca binary is_toxic sınıflandırması yapar.
        # Confidence, insult/bullying/hate_speech olasılığı değildir; bu alanlar ayrı model
        # çıktısı olmadığı için sıfır tutulur. Moderasyon için yalnızca binary toxicity
        # etiketi ve belirsiz/orta risk bağlamı kullanılır.
        toxicity = ToxicityAnalysis(
            insult=0,
            bullying=0,
            hate_speech=0,
            targeted_person_or_group="Genel",
            risk_level="Orta",
            context_note=(
                f"Özel Türkçe BERT+LoRA modeli binary toxic sınıfı verdi; "
                f"toxicity confidence %{round(confidence * 100, 2)}. "
                "Bu değer hakaret, zorbalık veya nefret söylemi olasılığı değildir."
            ),
        )
    else:
        toxicity = ToxicityAnalysis(
            insult=0,
            bullying=0,
            hate_speech=0,
            targeted_person_or_group="Genel",
            risk_level="Düşük",
            context_note=(
                f"Özel Türkçe BERT+LoRA modeli binary notoxic sınıfı verdi; "
                f"toxicity confidence %{round(confidence * 100, 2)}."
            ),
        )
    return toxicity, prediction["label"], confidence, True


def analyze_auxiliary_toxicity(text: str, general_toxicity: ToxicityAnalysis, general_label: str, general_confidence: float, general_available: bool) -> Tuple[ToxicityAnalysis, AuxiliaryToxicityModels]:
    insult = INSULT_SERVICE.predict(text)
    bullying = BULLYING_SERVICE.predict(text)
    hate = HATE_SERVICE.predict(text)
    insult_raw = insult.get("raw", {}) or {}
    bullying_raw = bullying.get("raw", {}) or {}
    insult_score = float(insult_raw.get("INSULT", 0.0)) if insult.get("available") else 0.0
    neutral = float(bullying_raw.get("Nötr", 0.0)) if bullying.get("available") else 0.0
    bullying_score = max(0.0, 100.0 - neutral) if bullying.get("available") else 0.0
    any_model_available = general_available or insult.get("available") or bullying.get("available") or hate.get("available")
    risk = "Yüksek" if max(insult_score, bullying_score) >= 70 else "Orta" if max(insult_score, bullying_score) >= 35 else "Düşük"
    if any_model_available:
        merged = ToxicityAnalysis(
            insult=round(insult_score),
            bullying=round(bullying_score),
            hate_speech=0,
            targeted_person_or_group=general_toxicity.targeted_person_or_group,
            risk_level=risk,
            context_note=(f"Genel toxicity: {general_label} (%{round(general_confidence * 100, 2)}). "
                          "Insult ve bullying skorları ayrı modellerden; hate çıktısı raw olarak korunur.")
        )
    else:
        merged = general_toxicity
    return merged, AuxiliaryToxicityModels(
        insult={
            "score": round(insult_score, 2),
            "engine": insult.get("engine", "fallback"),
            "available": bool(insult.get("available")),
            "error": insult.get("error", ""),
            "model_id": INSULT_MODEL_ID,
            "label": insult.get("label", ""),
            "raw": insult_raw,
        },
        bullying={
            "score": round(bullying_score, 2),
            "gender_bullying": round(float(bullying_raw.get("Cinsiyetçi Zorbalık", 0.0)), 2),
            "racist_bullying": round(float(bullying_raw.get("Irkçılık", 0.0)), 2),
            "harassment": round(float(bullying_raw.get("Kızdırma/Hakaret", 0.0)), 2),
            "neutral": round(neutral, 2),
            "engine": bullying.get("engine", "fallback"),
            "available": bool(bullying.get("available")),
            "error": bullying.get("error", ""),
            "model_id": BULLYING_MODEL_ID,
            "label": bullying.get("label", ""),
            "raw": bullying_raw,
        },
        hate_speech={
            "engine": hate.get("engine", "fallback"),
            "available": bool(hate.get("available")),
            "error": hate.get("error", ""),
            "model_id": HATE_MODEL_ID,
            "label": hate.get("label", ""),
            "raw": hate.get("raw", {}) or {},
        },
        available=any_model_available,
        error="; ".join(
            part
            for part in [
                INSULT_SERVICE.error if not insult.get("available") else "",
                BULLYING_SERVICE.error if not bullying.get("available") else "",
                HATE_SERVICE.error if not hate.get("available") else "",
            ]
            if part
        ),
    )


# ============================================================
# MODERASYON KARAR MOTORU
# ============================================================
# Şeffaflık ilkesi: eşik değerleri burada sabit ve okunabilir tutulur.
# Değerlendirme scripti (evaluate_moderation.py) bu fonksiyonu doğrudan
# import ederek etiketli test seti üzerinde precision/recall/F1 ölçer.

RISK_LEVEL_SCORE = {"Düşük": 0, "Orta": 45, "Yüksek": 80, "Low": 0, "Medium": 45, "High": 80}


def decide_moderation_action(toxicity: ToxicityAnalysis, language: str = "tr") -> ModerationDecision:
    """
    Yüksek riskli hedefli saldırılar ve tehditler, "potansiyel saldırgan" seviyesine göre
    boşluk bırakmadan kaldırma önerisine alınır.

    - Severe (kaldırma): yüksek nefret, ileri düzey grup hedefleme, dehumanizasyon,
      şiddet tehdidi veya risk_level=Yüksek + hedefli saldırı.
    - Moderate (gizle_ve_incele): orta-yüksek risk, hedefli saldırı/önyargı.
    - Mild (etiketle): hafif hakaret, pasif-agresif yorum.
    - Allow (izin_ver): anlamlı toksisite sinyali yok.
    """
    risk_level_component = RISK_LEVEL_SCORE.get(toxicity.risk_level, 0)
    english = language == "en"
    target_is_generic = toxicity.targeted_person_or_group in ["Genel", "General", "", None]
    target_is_specific = not target_is_generic

    aggregate_risk = max(
        toxicity.hate_speech,
        toxicity.bullying,
        int(toxicity.insult * 0.7),
        risk_level_component,
    )

    severe_targeted_attack = (
        target_is_specific and (
            toxicity.hate_speech >= 60 or
            toxicity.bullying >= 70 or
            toxicity.insult >= 70 or
            (toxicity.risk_level in {"Yüksek", "High"} and (toxicity.hate_speech >= 45 or toxicity.bullying >= 55))
        )
    )

    # SEVERE: Kaldırma önerisi (targeted threats, hate speech, severe bullying)
    if (
        (toxicity.hate_speech >= 65 and toxicity.bullying >= 70) or
        (toxicity.hate_speech >= 75) or
        (toxicity.bullying >= 85) or
        severe_targeted_attack
    ):
        return ModerationDecision(
            action="kaldirma_oner",
            action_label="Removal recommended - human approval required" if english else "Kaldırma önerisi - insan onayı gerekli",
            reason=(
                f"Severe hate speech ({toxicity.hate_speech}/100), targeted attack, or high-risk dehumanization detected. "
                f"Target: {toxicity.targeted_person_or_group}. Automatic removal is disabled because this action is irreversible."
                if english else
                f"Ağır nefret söylemi ({toxicity.hate_speech}/100), hedefli saldırı "
                f"veya yüksek-risk dehumanizasyon tespit edildi. "
                f"Hedefi: {toxicity.targeted_person_or_group}. "
                f"Geri dönüşü olmayan bir aksiyon olduğu için otomatik silme yapılmaz."
            ),
            requires_human_review=True,
            appeal_eligible=True,
            aggregate_risk=aggregate_risk,
        )

    # MODERATE: Gizle ve incele (medium-high toxicity)
    if (
        (toxicity.hate_speech >= 35 and toxicity.hate_speech < 65) or
        (toxicity.bullying >= 45 and toxicity.bullying < 70) or
        (toxicity.insult >= 55 and target_is_specific) or
        (toxicity.risk_level in {"Yüksek", "High"} and not target_is_generic)
    ):
        return ModerationDecision(
            action="gizle_ve_incele",
            action_label="Content hidden and sent for review" if english else "İçerik gizlendi, incelemeye alındı",
            reason=(
                f"Medium-to-high risk signals: insult {toxicity.insult}/100, bullying {toxicity.bullying}/100, hate speech {toxicity.hate_speech}/100. "
                f"Target: {toxicity.targeted_person_or_group}. Moderator review is required for a final decision."
                if english else
                f"Orta-yüksek risk sinyalleri: hakaret {toxicity.insult}/100, "
                f"zorbalık {toxicity.bullying}/100, nefret söylemi {toxicity.hate_speech}/100. "
                f"Hedef: {toxicity.targeted_person_or_group}. "
                f"Nihai karar için moderatör incelemesi gerekir."
            ),
            requires_human_review=True,
            appeal_eligible=True,
            aggregate_risk=aggregate_risk,
        )

    # MILD: Etiketle (low-medium toxicity)
    if (
        (toxicity.hate_speech >= 12 and toxicity.hate_speech < 35) or
        (toxicity.bullying >= 18 and toxicity.bullying < 45) or
        (toxicity.insult >= 22 and toxicity.insult < 55) or
        toxicity.risk_level in {"Orta", "Medium"}
    ):
        return ModerationDecision(
            action="etiketle",
            action_label="Content remains available with a warning label" if english else "İçerik uyarı etiketiyle yayında kalıyor",
            reason=(
                f"Low-to-medium risk signals: insult {toxicity.insult}, bullying {toxicity.bullying}, hate speech {toxicity.hate_speech}. "
                f"The content stays available with a context label. Risk level: {toxicity.risk_level}."
                if english else
                f"Düşük-orta şiddette risk sinyali: hakaret {toxicity.insult}, "
                f"zorbalık {toxicity.bullying}, nefret söylemi {toxicity.hate_speech}. "
                f"İçerik kaldırılmadan bağlam etiketi eklenir. "
                f"Risk seviyesi: {toxicity.risk_level}"
            ),
            requires_human_review=False,
            appeal_eligible=False,
            aggregate_risk=aggregate_risk,
        )

    return ModerationDecision(
        action="izin_ver",
        action_label="Content allowed" if english else "İçeriğe izin verildi",
        reason="No significant toxicity signals were detected." if english else "Anlamlı bir toksisite sinyali tespit edilmedi.",
        requires_human_review=False,
        appeal_eligible=False,
        aggregate_risk=aggregate_risk,
    )


def merge_toxicity_signals(text_toxicity: ToxicityAnalysis, image_toxicity: ToxicityAnalysis, language: str = "tr") -> ToxicityAnalysis:
    """Metin ve görsel toksisite sinyallerini ihtiyatlı biçimde birleştirir."""
    risk_rank = {"Düşük": 0, "Low": 0, "Orta": 1, "Medium": 1, "Yüksek": 2, "High": 2}
    highest_risk = max((text_toxicity.risk_level, image_toxicity.risk_level), key=lambda level: risk_rank.get(level, 0))
    if language == "en":
        highest_risk = {"Düşük": "Low", "Orta": "Medium", "Yüksek": "High"}.get(highest_risk, highest_risk)
    return ToxicityAnalysis(
        insult=max(text_toxicity.insult, image_toxicity.insult),
        bullying=max(text_toxicity.bullying, image_toxicity.bullying),
        hate_speech=max(text_toxicity.hate_speech, image_toxicity.hate_speech),
        targeted_person_or_group=(
            image_toxicity.targeted_person_or_group
            if image_toxicity.targeted_person_or_group not in {"", "Genel", "General"}
            else text_toxicity.targeted_person_or_group
        ),
        risk_level=highest_risk,
        context_note=(
            (
                f"Text and image signals combined: insult {max(text_toxicity.insult, image_toxicity.insult)}/100, "
                f"bullying {max(text_toxicity.bullying, image_toxicity.bullying)}/100, "
                f"hate speech {max(text_toxicity.hate_speech, image_toxicity.hate_speech)}/100."
                if language == "en"
                else f"Metin ve görsel birlikte değerlendirildi. Görsel sinyali: {image_toxicity.context_note}"
            )
        ),
    )


def compute_truthlens_verification(
    result: AnalysisResponse,
    has_source_url: bool = False,
    language: str = "tr",
) -> VerificationBadge:
    """TruthLens doğrulama rozetini mevcut analiz kontrollerine göre üretir."""
    reasons: List[str] = []
    english = language == "en"

    correct_results = {"doğru", "büyük ölçüde doğru", "true", "mostly true"}
    if stable_text(result.result) not in correct_results:
        reasons.append("The truthfulness verdict is not strong enough for the badge." if english else "Doğruluk sonucu rozet için yeterince güçlü değil.")

    if result.score < 80:
        reasons.append(f"Truth score is {result.score}/100; the badge threshold is 80." if english else f"Gerçeklik skoru {result.score}/100; rozet eşiği 80.")

    if result.manipulation > 20:
        reasons.append(f"Manipulation risk is {result.manipulation}/100; the threshold is 20." if english else f"Manipülasyon riski {result.manipulation}/100; eşik 20.")

    if result.clickbait > 20:
        reasons.append(f"Clickbait risk is {result.clickbait}/100; the threshold is 20." if english else f"Clickbait riski {result.clickbait}/100; eşik 20.")

    if result.polarization_risk > 30:
        reasons.append(f"Polarization risk is {result.polarization_risk}/100; the threshold is 30." if english else f"Kutuplaşma riski {result.polarization_risk}/100; eşik 30.")

    if stable_text(result.validity) not in {"geçerli", "valid"}:
        reasons.append("The content's validity or freshness is not suitable for the badge." if english else "İçeriğin geçerlilik/güncellik durumu rozet için uygun değil.")

    toxicity = result.toxicity
    if stable_text(toxicity.risk_level) not in {"düşük", "low"}:
        reasons.append("The toxicity risk level is not low." if english else "Toksisite risk seviyesi düşük değil.")
    if max(toxicity.insult, toxicity.bullying, toxicity.hate_speech) > 20:
        reasons.append("At least one toxicity signal is above 20/100." if english else "Toksisite sinyallerinden en az biri 20/100 üzerinde.")

    if result.moderation.action != "izin_ver":
        reasons.append("The moderation decision is not 'allow'." if english else "Moderasyon kararı 'izin ver' seviyesinde değil.")

    if result.contradicting_sources:
        reasons.append("The badge was withheld because contradicting sources were found." if english else "Çelişen kaynaklar bulunduğu için rozet verilmedi.")

    if has_source_url:
        source = result.source_analysis
        if not source or source.source_probability < 70:
            reasons.append("The source chain lacks strong enough verification of a primary source." if english else "Kaynak zincirinde yeterince güçlü bir birincil kaynak doğrulaması yok.")
        if source and stable_text(source.source_status) == "uncertain":
            reasons.append("The primary source status is uncertain." if english else "Birincil kaynak durumu belirsiz.")

    if reasons:
        return VerificationBadge(
            verified=False,
            label="TruthLens verification is incomplete" if english else "TruthLens doğrulaması tamamlanmadı",
            short_label="Unverified" if english else "Doğrulanmadı",
            reasons=reasons,
        )

    return VerificationBadge(
        verified=True,
        label="TruthLens evidence review complete — this is not a guarantee of truth" if english else "TruthLens kanıt kapsamı tamamlandı — kesin doğruluk garantisi değildir",
        short_label="Evidence review complete" if english else "Kanıt kapsamı tamamlandı",
        reasons=[
            f"Truthfulness: {result.result} · truth score {result.score}/100." if english else f"Doğruluk: {result.result} · gerçeklik skoru {result.score}/100.",
            f"Freshness/validity: {result.validity} · time assessment: {result.time_validity}." if english else f"Güncellik/geçerlilik: {result.validity} · zaman değerlendirmesi: {result.time_validity}.",
            (
                f"Toxicity context: insult {toxicity.insult}%, bullying {toxicity.bullying}%, "
                f"hate speech {toxicity.hate_speech}% · risk {toxicity.risk_level}."
                if english else
                f"Toksik bağlam: hakaret %{toxicity.insult}, zorbalık %{toxicity.bullying}, "
                f"nefret dili %{toxicity.hate_speech} · risk {toxicity.risk_level}."
            ),
            f"Toxicity target/context: {toxicity.targeted_person_or_group}." if english else f"Toksisite hedefi/bağlamı: {toxicity.targeted_person_or_group}.",
            f"Manipulation {result.manipulation}% · clickbait {result.clickbait}% · polarization {result.polarization_risk}%." if english else f"Manipülasyon %{result.manipulation} · clickbait %{result.clickbait} · kutuplaşma %{result.polarization_risk}.",
            f"Moderation: {result.moderation.action_label} · aggregate risk {result.moderation.aggregate_risk}%." if english else f"Moderasyon: {result.moderation.action_label} · toplam risk %{result.moderation.aggregate_risk}.",
            "All TruthLens verification requirements were met." if english else "Tüm TruthLens doğrulama koşulları sağlandı.",
        ],
    )


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


def social_analysis_cache_key(uri: str, cid: str = "", content: str = "", language: str = "tr") -> str:
    normalized_uri = normalize_url(uri)
    normalized_cid = str(cid or "").strip().lower()
    normalized_content = stable_text(content)
    raw = f"truthlens:social:v2|{language}|{normalized_uri}|{normalized_cid}|{normalized_content}"
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


def build_social_analysis_fallback(message: str = "AI analizi şu anda beklemede.", language: str = "tr") -> dict:
    if language == "en" and message == "AI analizi şu anda beklemede.":
        message = "AI analysis is pending."
    return {
        "summary": message,
        "misinformation_risk": 0,
        "polarization": 0,
        "hate_speech": 0,
        "spam_risk": 0,
        "sentiment": "Unclear" if language == "en" else "Belirsiz",
        "reasoning": "The mini analysis could not be generated. The post remains visible." if language == "en" else "Hafif analiz şu anda üretilemedi. Gönderi gösterilmeye devam ediyor.",
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


def analyze_social_post(content: str, source_url: str = "", cid: str = "", language: str = "tr") -> dict:
    cache_key = social_analysis_cache_key(source_url, cid, content, language)
    cached = ANALYSIS_CACHE.get(cache_key)
    if isinstance(cached, dict):
        return cached

    output_language = "English" if language == "en" else "Turkish"
    prompt = f"""
Return JSON only for the following Bluesky post.
Keep it concise. Do not research the web. Write every text value in {output_language}.

Gönderi:
\"\"\"
{content[:900]}
\"\"\"

Çıktı şeması:
{{
    "summary": "a 1-2 sentence mini summary in {output_language}",
  "misinformation_risk": 0-100,
  "polarization": 0-100,
  "hate_speech": 0-100,
  "spam_risk": 0-100,
    "sentiment": "a short sentiment label in {output_language}",
    "reasoning": "a short rationale in {output_language}"
}}
"""

    try:
        raw = call_llm([{"role": "user", "content": prompt}], temperature=0.1)
        data = json.loads(raw)
        result = {
            "summary": str(data.get("summary", "TruthLens mini analysis generated." if language == "en" else "TruthLens mini analizi üretildi.")).strip(),
            "misinformation_risk": safe_score(data.get("misinformation_risk")),
            "polarization": safe_score(data.get("polarization")),
            "hate_speech": safe_score(data.get("hate_speech")),
            "spam_risk": safe_score(data.get("spam_risk")),
            "sentiment": str(data.get("sentiment", "Unclear" if language == "en" else "Belirsiz")).strip() or ("Unclear" if language == "en" else "Belirsiz"),
            "reasoning": str(data.get("reasoning", "A short rationale is unavailable." if language == "en" else "Kısa gerekçe sağlanamadı.")).strip() or ("A short rationale is unavailable." if language == "en" else "Kısa gerekçe sağlanamadı."),
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
        fallback = build_social_analysis_fallback(language=language)
        fallback["status"] = "rate_limited" if is_rate_limit_error(exc) else "error"
        fallback["reasoning"] = "The mini analysis could not be completed; the post remains visible." if language == "en" else "Mini analiz isteği şu anda tamamlanamadı; gönderi görünür durumda."
        ANALYSIS_CACHE[cache_key] = fallback
        return fallback


def attach_social_analysis(post: dict, language: str = "tr") -> dict:
    content = post.get("content", "")
    source_url = post.get("source_url", "")
    cid = post.get("cid", "")
    cache_key = social_analysis_cache_key(source_url, cid, content, language)
    cached = ANALYSIS_CACHE.get(cache_key)
    if isinstance(cached, dict):
        analysis = cached
    else:
        analysis = estimate_social_signals(content)
        if language == "en":
            analysis["sentiment"] = {"Öfke": "Anger", "Endişe": "Concern", "Heyecan": "Excitement", "Nötr": "Neutral", "Belirsiz": "Unclear"}.get(analysis.get("sentiment"), analysis.get("sentiment"))
            analysis["summary"] = "🤖 TruthLens mini analysis is pending..."
            analysis["reasoning"] = "This is a preliminary language-signal estimate; it will be updated when the full mini analysis is complete."
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


def warm_social_analysis(posts: List[dict], limit: int = 3, language: str = "tr") -> None:
    for post in posts[:limit]:
        try:
            analyze_social_post(post.get("content", ""), post.get("source_url", ""), post.get("cid", ""), language)
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


def fetch_bluesky_feed(limit: int = BLUESKY_FEED_LIMIT, language: str = "tr") -> dict:
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
                # Feed badge is granted only after the user runs the full /analyze flow.
                # The frontend updates this field for the current session when verification passes.
                "verified_by_truthlens": False,
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
            post_payload = attach_social_analysis(post_payload, language)
            posts.append(post_payload)

        uncached_posts = [post for post in posts if post.get("analysis_status") == "pending"]
        if uncached_posts:
            threading.Thread(target=warm_social_analysis, args=(uncached_posts, 3, language), daemon=True).start()

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

        summary = summarize_demo_feed(posts, language)
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
                "top_emotion": "Neutral" if language == "en" else "Nötr",
                "avg_truthlens_score": 0,
                "risk_level": "Low" if language == "en" else "Düşük",
                "highlight": "The Bluesky feed could not be loaded. Check your Bluesky credentials." if language == "en" else "Bluesky akışı alınamadı. Lütfen Bluesky kimlik bilgilerini kontrol edin.",
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


def summarize_demo_feed(posts: List[dict], language: str = "tr") -> dict:
    english = language == "en"
    if not posts:
        return {
            "top_emotion": "Neutral" if english else "Nötr",
            "avg_truthlens_score": 0,
            "risk_level": "Low" if english else "Düşük",
            "highlight": "No posts to display." if english else "Gösterilecek içerik bulunamadı.",
            "total_posts": 0,
        }

    emotion_counts: Dict[str, int] = {}
    total_score = 0

    for post in posts:
        total_score += int(post.get("truthlens_score", 0))
        emotion = str(post.get("emotion", "Neutral" if english else "Nötr")).strip() or ("Neutral" if english else "Nötr")
        emotion_counts[emotion] = emotion_counts.get(emotion, 0) + 1

    top_emotion = max(emotion_counts.items(), key=lambda item: item[1])[0]
    if english:
        top_emotion = {"Öfke": "Anger", "Endişe": "Concern", "Heyecan": "Excitement", "Nötr": "Neutral", "Belirsiz": "Unclear"}.get(top_emotion, top_emotion)
    avg_score = round(total_score / len(posts))

    if avg_score >= 70:
        risk_level = "Low" if english else "Düşük"
    elif avg_score >= 45:
        risk_level = "Medium" if english else "Orta"
    else:
        risk_level = "High" if english else "Yüksek"

    highlight = (
        ("The feed is dominated by anger and biased language, with a notable share of polarizing content." if english else "Son akışta öfke ve taraflı dil baskındır; kutuplaştırıcı içeriklerin oranı dikkat çekiyor.")
        if top_emotion in ({"Anger", "Concern"} if english else {"Öfke", "Endişe"})
        else ("The feed appears generally more neutral and lower risk." if english else "Akış genel olarak daha tarafsız ve düşük riskli görünüyor.")
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
    conn = sqlite3.connect(DB_PATH, timeout=10)
    conn.row_factory = sqlite3.Row
    try:
        conn.execute("PRAGMA journal_mode=WAL;")
        conn.execute("PRAGMA synchronous=NORMAL;")
    except Exception:
        pass
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

        CREATE TABLE IF NOT EXISTS moderation_decisions (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER DEFAULT NULL,
            content_hash TEXT NOT NULL,
            action TEXT NOT NULL,
            aggregate_risk INTEGER NOT NULL,
            reason TEXT,
            created_at TEXT NOT NULL,
            appeal_status TEXT DEFAULT NULL,
            appeal_reason TEXT DEFAULT NULL,
            appeal_created_at TEXT DEFAULT NULL
        );
        """
    )

    # Existing SQLite databases: add the new column/index without destroying data.
    columns = {
        row["name"]
        for row in conn.execute("PRAGMA table_info(moderation_decisions)").fetchall()
    }
    if "user_id" not in columns:
        conn.execute(
            "ALTER TABLE moderation_decisions ADD COLUMN user_id INTEGER DEFAULT NULL"
        )
    conn.execute(
        "CREATE INDEX IF NOT EXISTS idx_moderation_decisions_user_id "
        "ON moderation_decisions(user_id, id DESC)"
    )

    # Eski moderasyon kayitlarini ayni content_hash uzerinden
    # analysis_history icindeki kullaniciya bagla.
    conn.execute(
        """
        UPDATE moderation_decisions
        SET user_id = (
            SELECT ah.user_id
            FROM analysis_history ah
            WHERE ah.content_hash = moderation_decisions.content_hash
            ORDER BY ah.id DESC
            LIMIT 1
        )
        WHERE user_id IS NULL
          AND EXISTS (
            SELECT 1
            FROM analysis_history ah2
            WHERE ah2.content_hash = moderation_decisions.content_hash
          )
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
    now = datetime.now(timezone.utc).isoformat()
    row = conn.execute(
        """
        SELECT u.id, u.name, u.email
        FROM sessions s
        JOIN users u ON u.id = s.user_id
        WHERE s.token = ? AND s.expires_at > ?
        """,
        (token, now),
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

def log_moderation_decision(
    content_hash: str,
    moderation: "ModerationDecision",
    user_id: Optional[int] = None,
) -> None:
    conn = get_db_connection()
    conn.execute(
        """
        INSERT INTO moderation_decisions (
            user_id, content_hash, action, aggregate_risk, reason, created_at
        )
        VALUES (?, ?, ?, ?, ?, ?)
        """,
        (
            user_id,
            content_hash,
            moderation.action,
            moderation.aggregate_risk,
            moderation.reason,
            datetime.now(timezone.utc).isoformat(),
        ),
    )
    conn.commit()
    conn.close()


def submit_moderation_appeal(
    content_hash: str,
    appeal_reason: str,
    user_id: Optional[int] = None,
) -> Optional[dict]:
    conn = get_db_connection()
    row = conn.execute(
        """
        SELECT id
        FROM moderation_decisions
        WHERE content_hash = ?
          AND ((user_id = ?) OR (user_id IS NULL AND ? IS NULL))
        ORDER BY id DESC
        LIMIT 1
        """,
        (content_hash, user_id, user_id),
    ).fetchone()

    if not row:
        conn.close()
        return None

    conn.execute(
        """
        UPDATE moderation_decisions
        SET appeal_status = 'beklemede',
            appeal_reason = ?,
            appeal_created_at = ?
        WHERE id = ?
        """,
        (appeal_reason, datetime.now(timezone.utc).isoformat(), row["id"]),
    )
    conn.commit()
    conn.close()
    return {"id": row["id"], "appeal_status": "beklemede"}


init_db()


@app.on_event("startup")
def preload_custom_toxicity_model() -> None:
    # Modeller request başına değil, süreç başlangıcında bir kez yüklenir.
    TOXICITY_SERVICE.load_once()
    INSULT_SERVICE.load_once()
    BULLYING_SERVICE.load_once()
    HATE_SERVICE.load_once()


# ============================================================
# CACHE / DETERMINISTIC ANALYSIS
# ============================================================

def stable_text(value: str) -> str:
    if not value:
        return ""
    return re.sub(r"\s+", " ", value.strip()).lower()


def analysis_cache_key(content: str, source_url: Optional[str] = None, language: str = "tr") -> str:
    normalized_content = stable_text(content)
    normalized_url = (source_url or "").strip().lower()
    model_state = (
        f"tox={int(TOXICITY_SERVICE.available)}:"
        f"ins={int(INSULT_SERVICE.available)}:"
        f"bul={int(BULLYING_SERVICE.available)}:"
        f"hat={int(HATE_SERVICE.available)}"
    )
    raw = f"truthlens:v5|{language}|{normalized_url}|{normalized_content}|{model_state}"
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

LAST_GEMINI_STATUS: Dict[str, object] = {"status": "idle", "model": GEMINI_MODEL}


def gemini_generate(parts: List[dict], temperature: float = 0.2) -> str:
    """Google Gemini Developer API'ye doğrudan REST çağrısı yapar; NaraRouter yoktur."""
    global LAST_GEMINI_STATUS
    if not GOOGLE_API_KEY:
        LAST_GEMINI_STATUS = {"status": "missing_api_key", "model": GEMINI_MODEL}
        raise HTTPException(status_code=500, detail="GOOGLE_API_KEY yapılandırılmamış.")
    endpoint = f"{GEMINI_API_BASE.rstrip('/')}/models/{GEMINI_MODEL}:generateContent"
    payload = {
        "contents": [{"role": "user", "parts": parts}],
        "generationConfig": {
            "temperature": temperature,
            "responseMimeType": "application/json",
        },
    }
    try:
        response = requests.post(
            endpoint,
            params={"key": GOOGLE_API_KEY},
            json=payload,
            timeout=45,
        )
        response.raise_for_status()
        data = response.json()
        text = "".join(
            str(part.get("text", ""))
            for part in ((data.get("candidates") or [{}])[0].get("content") or {}).get("parts", [])
            if isinstance(part, dict)
        ).strip()
        if not text:
            raise RuntimeError("Gemini boş yanıt döndürdü.")
        LAST_GEMINI_STATUS = {"status": "success", "model": GEMINI_MODEL}
        return text
    except Exception as exc:
        LAST_GEMINI_STATUS = {"status": "error", "model": GEMINI_MODEL, "error": str(exc)}
        print(f"[TruthLens] Direct Gemini error: {exc}")
        raise


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

HTML_CACHE_LOCK = threading.Lock()
HTML_CACHE: Dict[str, str] = {}

def fetch_webpage(url: str) -> Optional[str]:
    url = url.strip()
    with HTML_CACHE_LOCK:
        if url in HTML_CACHE:
            return HTML_CACHE[url]

    headers = {
        "User-Agent": (
            "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
            "AppleWebKit/537.36 (KHTML, like Gecko) "
            "Chrome/139.0.0.0 Safari/537.36"
        ),
        "Accept-Language": "tr-TR,tr;q=0.9,en;q=0.8",
    }
    try:
        response = requests.get(url, headers=headers, timeout=6, allow_redirects=True)
        response.raise_for_status()
        text = response.text
        with HTML_CACHE_LOCK:
            HTML_CACHE[url] = text
        return text
    except Exception as e:
        print(f"[TruthLens] Web request error for {url}: {e}")
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

SIGHTENGINE_CACHE_LOCK = threading.Lock()
SIGHTENGINE_CACHE: Dict[str, dict] = {}

def detect_ai_image(image_url: str) -> Optional[dict]:
    if not image_url_is_reasonable(image_url):
        return None
    if not SIGHTENGINE_API_USER or not SIGHTENGINE_API_SECRET:
        return None

    image_url = image_url.strip()
    with SIGHTENGINE_CACHE_LOCK:
        if image_url in SIGHTENGINE_CACHE:
            print(f"[TruthLens] Image AI check (cached): {image_url}")
            return SIGHTENGINE_CACHE[image_url]

    t0 = time.time()
    try:
        response = requests.get(
            "https://api.sightengine.com/1.0/check.json",
            params={
                "url": image_url,
                "models": "genai",
                "api_user": SIGHTENGINE_API_USER,
                "api_secret": SIGHTENGINE_API_SECRET,
            },
            timeout=8,
        )
        response.raise_for_status()
        payload = response.json() if response.content else {}
    except Exception as exc:
        print(f"[TruthLens] Sightengine error: {exc}")
        return None

    ai_probability = 0
    is_ai = None

    type_payload = payload.get("type") if isinstance(payload.get("type"), dict) else {}
    genai_payload = payload.get("genai") if isinstance(payload.get("genai"), dict) else {}
    type_ai = type_payload.get("ai_generated")
    candidates = [
        type_ai,
        type_ai.get("prob") if isinstance(type_ai, dict) else None,
        type_ai.get("probability") if isinstance(type_ai, dict) else None,
        type_ai.get("score") if isinstance(type_ai, dict) else None,
        genai_payload.get("prob"),
        genai_payload.get("probability"),
        genai_payload.get("ai_probability"),
        genai_payload.get("ai_prob"),
        payload.get("ai_probability"),
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

    res = {
        "ai_probability": ai_probability,
        "is_ai": bool(is_ai) if is_ai is not None else None,
        "error": None,
    }
    with SIGHTENGINE_CACHE_LOCK:
        SIGHTENGINE_CACHE[image_url] = res
    dur = time.time() - t0
    print(f"[TruthLens] Image AI check: {image_url} -> {dur:.2f}s")
    return res

def image_cache_key(image_url: str, source_url: str = "") -> str:
    # Sightengine + vision + image-to-moderation sözleşmesi değişti; eski 0/fallback sonuçlarını kullanma.
    raw = f"truthlens:image:v2-sightengine-vision-moderation|{normalize_url(source_url)}|{normalize_url(image_url)}"
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()

def image_url_is_reasonable(image_url: str) -> bool:
    return bool(re.match(r"^https?://", image_url or "", re.IGNORECASE))

def ocr_image_text(image_url: str) -> str:
    """Vision LLM kullanılamadığında görsel yazısını yerel OCR ile okumayı dener."""
    if Image is None or pytesseract is None or not image_url_is_reasonable(image_url):
        return ""
    try:
        response = requests.get(image_url, timeout=8, headers={"User-Agent": "Mozilla/5.0"})
        response.raise_for_status()
        image = Image.open(BytesIO(response.content)).convert("RGB")
        return str(pytesseract.image_to_string(image, lang="tur+eng") or "").strip()[:3000]
    except Exception as exc:
        print(f"[TruthLens] OCR fallback error: {exc}")
        return ""



def analyze_image_ai_probability(image_url: str, source_url: str = "") -> dict:
    if not image_url_is_reasonable(image_url):
        return {
            "image_ai_probability": 0,
            "image_analysis_available": False,
            "image_analysis_reasoning": "Geçerli bir görsel URL'si bulunamadı.",
            "visible_text": "",
            "image_toxicity": {
                "insult": 0,
                "bullying": 0,
                "hate_speech": 0,
                "targeted_person_or_group": "Genel",
                "risk_level": "Düşük",
                "context_note": "URL geçersiz.",
            },
            "image_url": "",
        }

    cache_key = image_cache_key(image_url, source_url)
    cached = ANALYSIS_CACHE.get(cache_key)
    if isinstance(cached, dict):
        return cached

    # Step 1: Sightengine API'sini çağır (fast, accurate AI detection)
    t0_sight = time.time()
    sightengine_result = detect_ai_image(image_url)
    ai_probability_from_sightengine = sightengine_result.get("ai_probability", 0) if sightengine_result else 0
    dur_sight = time.time() - t0_sight
    print(f"[TruthLens] Sightengine AI check: {dur_sight:.2f}s → {ai_probability_from_sightengine}%")

    # LLM başarısız olsa bile OCR ile görsel metni ve argo adayı kaybetme.
    ocr_text = ocr_image_text(image_url)
    if ocr_text:
        ocr_toxicity, _ocr_model_details = analyze_auxiliary_toxicity(
            ocr_text,
            ToxicityAnalysis(context_note="OCR metni dört toxicity modeliyle değerlendirildi."),
            "notoxic",
            0.0,
            False,
        )
    else:
        ocr_toxicity = ToxicityAnalysis(context_note="Görselde okunabilir metin bulunamadı.")

    # Step 2: LLM vision model'i çağır (toksisitesi ve metin extraction için)
    prompt = """
Bu görseli sosyal medya güvenliği ve içerik moderasyonu açısından incele.
Görselde okunabilen yazı varsa aynen veya güvenli biçimde kısa bir özet olarak çıkar.
Görsel içindeki argo, hakaret, tehdit, hedefli saldırı veya nefret söylemi sinyallerini değerlendir.
Kesin hüküm verme; okunamayan metin varsa bunu açıkça belirt.
Yalnızca aşağıdaki JSON formatında yanıt ver:
{
  "image_analysis_reasoning": "Görselin güvenlik açısından kısa değerlendirmesi",
  "visible_text": "Görseldeki okunabilir metin veya boş metin",
  "image_toxicity": {
    "insult": 0-100,
    "bullying": 0-100,
    "hate_speech": 0-100,
    "targeted_person_or_group": "Genel veya hedef",
    "risk_level": "Düşük/Orta/Yüksek",
    "context_note": "Görsel metni ve güvenlik bağlamı"
  }
}
"""
    try:
        t0_llm = time.time()
        image_response = requests.get(image_url, timeout=15)
        image_response.raise_for_status()
        image_mime = image_response.headers.get("content-type", "image/jpeg").split(";", 1)[0]
        image_b64 = __import__("base64").b64encode(image_response.content).decode("ascii")
        raw = gemini_generate(
            [
                {"text": prompt.strip()},
                {"inline_data": {"mime_type": image_mime, "data": image_b64}},
            ],
            temperature=0.1,
        )
        data = json.loads(raw)
        dur_llm = time.time() - t0_llm
        print(f"[TruthLens] Direct Gemini vision: {dur_llm:.2f}s")
        
        result = {
            "image_ai_probability": ai_probability_from_sightengine,
            "image_analysis_available": True,
            "image_analysis_reasoning": str(data.get("image_analysis_reasoning", "")).strip() or f"Sightengine: %{ai_probability_from_sightengine} AI olasılığı.",
            "visible_text": str(data.get("visible_text", "") or "").strip() or ocr_text,
            "image_toxicity": merge_toxicity_signals(
                ocr_toxicity,
                ToxicityAnalysis(
                    insult=safe_score((data.get("image_toxicity") or {}).get("insult")),
                    bullying=safe_score((data.get("image_toxicity") or {}).get("bullying")),
                    hate_speech=safe_score((data.get("image_toxicity") or {}).get("hate_speech")),
                    targeted_person_or_group=str((data.get("image_toxicity") or {}).get("targeted_person_or_group") or "Genel"),
                    risk_level=str((data.get("image_toxicity") or {}).get("risk_level") or "Düşük"),
                    context_note=str((data.get("image_toxicity") or {}).get("context_note") or "Vision toksisite analizi tamamlandı."),
                ),
            ),
            "image_url": image_url,
        }
        ANALYSIS_CACHE[cache_key] = result
        return result
    except Exception as exc:
        print(f"[TruthLens] Image LLM error: {exc}")
        fallback = {
            "image_ai_probability": ai_probability_from_sightengine,
            "image_analysis_available": bool(ai_probability_from_sightengine > 0 or ocr_text),
            "image_analysis_reasoning": f"Sightengine AI tespiti: %{ai_probability_from_sightengine}. Vision analizi kullanılamadı; OCR fallback uygulandı.",
            "visible_text": ocr_text,
            "image_toxicity": ocr_toxicity.model_dump(),
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

def build_source_chain(
    source_items: List[dict],
    current_source_label: str,
    current_source_date: str,
) -> dict:
    """
    Birincil kaynak adaylarını değerlendirir.

    Amaç:
    - Platform adını değil, mümkünse doğrudan paylaşımı göstermek
    - Kaynağın URL'sini frontend'e göndermek
    - Resmi/kurumsal kaynakları önceliklendirmek
    - Olasılığı kaynak sayısından uydurmamak
    """

    candidates = []

    for item in source_items:
        url = str(item.get("url", "") or "").strip()
        title = str(item.get("source", "") or "").strip()
        date = str(item.get("date", "") or "").strip()
        platform = str(item.get("platform", "") or "").strip()

        if not url:
            continue

        score = 0

        lowered_title = title.lower()
        lowered_url = url.lower()

        # Resmi kurum / resmi site sinyalleri
        official_domains = (
            ".gov.tr",
            ".gov",
            ".bel.tr",
            ".edu.tr",
            ".mil.tr",
        )

        if any(domain in lowered_url for domain in official_domains):
            score += 45

        # Sosyal medya paylaşımı olması önemli.
        # Burada amaç platform adını değil doğrudan paylaşım URL'sini
        # kaynak olarak göstermek.
        social_domains = (
            "x.com",
            "twitter.com",
            "bsky.app",
            "threads.net",
            "facebook.com",
            "instagram.com",
            "tiktok.com",
            "nsosyal.com",
        )

        if any(domain in lowered_url for domain in social_domains):
            score += 30

        # Başlığın sadece platform adı olması kötü bir sinyal.
        generic_platform_titles = {
            "x",
            "twitter",
            "bluesky",
            "facebook",
            "instagram",
            "tiktok",
            "nsosyal",
        }

        if lowered_title in generic_platform_titles:
            score -= 20

        # Gerçek bir başlık varsa avantaj.
        if len(title) >= 25:
            score += 10

        # Tarihi bulunan kaynak daha değerlidir.
        if date:
            score += 5

        candidates.append({
            "source": title or "Birincil kaynak adayı",
            "url": url,
            "date": date,
            "platform": platform,
            "score": max(0, min(100, score)),
        })

    # Mevcut gönderiyi de aday olarak ekle
    if current_source_label:
        current_url = current_source_label if current_source_label.startswith("http") else ""

        if current_url:
            candidates.append({
                "source": "Mevcut paylaşım",
                "url": current_url,
                "date": current_source_date or "",
                "platform": get_domain(current_url),
                "score": 20,
            })

    # En yüksek puanlı aday birincil kaynak adayıdır.
    candidates.sort(
        key=lambda item: (
            item["score"],
            bool(item["date"]),
        ),
        reverse=True,
    )

    if not candidates:
        return {
            "source_status": "uncertain",
            "source_probability": 0,
            "likely_original_source": "",
            "earliest_found_source": "",
            "earliest_found_date": "",
            "current_source_date": current_source_date or "",
            "source_chain": [],
            "reasoning": "Birincil kaynak adayı bulunamadı.",
        }

    primary = candidates[0]

    # Gerçek bir "kanıt gücü" skoru.
    # Kaynak sayısından rastgele %92 üretmiyoruz.
    probability = primary["score"]

    if primary["score"] >= 75:
        status = "strong_candidate"
        reasoning = (
            "Resmi veya doğrudan paylaşım niteliği taşıyan güçlü bir "
            "birincil kaynak adayı bulundu."
        )
    elif primary["score"] >= 50:
        status = "candidate"
        reasoning = (
            "Birincil kaynak olabilecek bir aday bulundu; ancak kesin "
            "ilk paylaşım olduğu doğrulanamadı."
        )
    else:
        status = "uncertain"
        reasoning = (
            "Birincil kaynak için yeterli kanıt bulunamadı."
        )

    chain = [
        {
            "source": item["source"],
            "url": item["url"],
            "date": item["date"],
            "platform": item["platform"],
        }
        for item in candidates
    ]

    return {
        "source_status": status,
        "source_probability": probability,
        "likely_original_source": primary["source"],
        "earliest_found_source": primary["source"],
        "earliest_found_date": primary["date"],
        "current_source_date": current_source_date or "",
        "source_chain": chain,
        "reasoning": reasoning,
    }

# ============================================================
# TAVILY 
# ============================================================

TAVILY_CACHE_LOCK = threading.Lock()
TAVILY_CACHE: Dict[str, List[dict]] = {}

def search_with_tavily(query: str, max_results: int = 5) -> List[dict]:
    query_key = f"{query}|{max_results}"
    with TAVILY_CACHE_LOCK:
        if query_key in TAVILY_CACHE:
            print(f"[TruthLens] Tavily search (cached): '{query}'")
            return TAVILY_CACHE[query_key]

    t0 = time.time()
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
        with TAVILY_CACHE_LOCK:
            TAVILY_CACHE[query_key] = results
        dur = time.time() - t0
        print(f"[TruthLens] Tavily search: '{query}' -> {dur:.2f}s")
        return results
    except Exception as e:
        print(f"[TruthLens] Tavily error: {e}")
        return []

def call_llm(messages: list, temperature: float = 0.2) -> str:
    parts = []
    for message in messages:
        content = message.get("content", "") if isinstance(message, dict) else str(message)
        if isinstance(content, list):
            content = "\n".join(str(item.get("text", "")) for item in content if isinstance(item, dict))
        parts.append(str(content))
    return gemini_generate([{"text": "\n\n".join(parts)}], temperature=temperature)

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

def parse_json_object(raw: str) -> dict:
    """LLM çıktısındaki fenced JSON veya çevre metnini güvenli biçimde ayıklar."""
    raw = (raw or "").strip()
    try:
        return json.loads(raw)
    except Exception:
        match = re.search(r"\{.*\}", raw, re.DOTALL)
        if match:
            try:
                return json.loads(match.group(0))
            except Exception:
                return {}
        return {}


def extract_claim_with_gemini(content: str, language: str = "tr") -> dict:
    output_language = "English" if language == "en" else "Turkish"
    prompt = f"""
You are TruthLens AI's claim extraction module. Analyze the input in its original language.
Write the claim and claims in {output_language}. Keep search_query in the input's original language.
Return JSON only and never invent claims.
Metin:
{content[:2500]}
Şema:
{{
  "has_claim": true,
    "claim": "one verifiable main claim, or an empty string, written in {output_language}",
    "claims": ["claim 1 written in {output_language}"],
    "search_query": "a concise, specific search query in the input's original language"
}}
"""
    try:
        return parse_json_object(call_llm([{"role": "user", "content": prompt}], temperature=0.0))
    except Exception as exc:
        print(f"[TruthLens] Claim extraction fallback: {exc}")
        return {"has_claim": False, "claim": "", "claims": [], "search_query": "", "error": str(exc)}


def evidence_sources_for_claim(claim: str, source_url: Optional[str] = None) -> List[dict]:
    global LAST_TAVILY_STATUS
    if not claim.strip():
        LAST_TAVILY_STATUS = {"status": "skipped_no_claim", "count": 0, "query": ""}
        return []
    try:
        results = search_with_tavily(claim[:500], max_results=5)
    except Exception as exc:
        LAST_TAVILY_STATUS = {"status": "error", "count": 0, "query": claim[:500], "error": str(exc)}
        print(f"[TruthLens] Evidence retrieval fallback: {exc}")
        results = []
    evidence = []
    seen = set()
    for item in results:
        url = str(item.get("url", "") or "").strip()
        if not url or normalize_url(url) in seen:
            continue
        seen.add(normalize_url(url))
        title = str(item.get("title", "") or "").strip()
        content = str(item.get("content", "") or "").strip()
        evidence.append({"title": title, "url": url, "content": content})
    if source_url and normalize_url(source_url) not in seen:
        evidence.append({"title": "Mevcut paylaşım", "url": source_url, "content": ""})
    LAST_TAVILY_STATUS = {
        "status": "success" if evidence else "empty",
        "count": len(evidence),
        "query": claim[:500],
    }
    return evidence


def final_reasoning_with_gemini(content: str, claim: str, evidence: List[dict], language: str = "tr") -> dict:
    output_language = "English" if language == "en" else "Turkish"
    evidence_text = "\n".join(
        f"KAYNAK {idx}: {item.get('title', '')} | {item.get('url', '')} | {item.get('content', '')[:700]}"
        for idx, item in enumerate(evidence, 1)
    ) or "KAYNAK YOK"
    prompt = f"""
You are TruthLens AI's final evidence-based reasoning module. Write every user-facing text value in {output_language}.
Keep JSON keys, URLs, and evidence relation values in the schema language shown below.
İçerik: {content[:2500]}
Ana iddia: {claim or 'Yok'}
Tavily kanıtları (yalnızca bunları kullan; kaynak uydurma):
{evidence_text}
Yalnızca JSON döndür:
{{
    "truthfulness": "a concise truthfulness verdict in {output_language}",
  "confidence": 0.0,
    "reason": "a concise, evidence-based explanation in {output_language}",
  "supporting_urls": [],
  "contradicting_urls": [],
  "evidence": [{{"url": "", "relation": "supports / contradicts / context"}}],
  "score": 0,
  "manipulation": 0,
  "clickbait": 0,
    "emotion": "a short emotion label in {output_language}",
  "polarization_risk": 0,
    "echo_chamber": "a short social risk note in {output_language}",
    "ai_rewrite": "a neutral rewrite in {output_language}",
    "social_risk_summary": "a short social risk summary in {output_language}",
    "validity": "a validity label in {output_language}",
    "time_validity": "a short time-related note in {output_language}",
    "context": "additional context in {output_language}",
    "explanation": "an explanation in {output_language}",
    "score_breakdown": "a score breakdown in {output_language}"
}}
"""
    try:
        data = parse_json_object(call_llm([{"role": "user", "content": prompt}], temperature=0.1))
        return data or {}
    except Exception as exc:
        print(f"[TruthLens] Final reasoning fallback: {exc}")
        return {}


def run_analysis(analyzed_content: str, source_url: Optional[str] = None, language: str = "tr") -> AnalysisResponse:
    key = analysis_cache_key(analyzed_content, source_url, language)
    if key in ANALYSIS_CACHE:
        return ANALYSIS_CACHE[key]

    text_toxicity, toxicity_label, toxicity_confidence, model_available = custom_text_toxicity(analyzed_content)
    text_toxicity, auxiliary_toxicity_models = analyze_auxiliary_toxicity(
        analyzed_content, text_toxicity, toxicity_label, toxicity_confidence, model_available
    )
    claim_data = extract_claim_with_gemini(analyzed_content, language)
    has_claim = bool(claim_data.get("has_claim")) and bool(str(claim_data.get("claim", "")).strip())
    claim = str(claim_data.get("claim", "") or "").strip()
    claims = [str(item).strip() for item in claim_data.get("claims", []) if str(item).strip()]
    if claim and claim not in claims:
        claims.insert(0, claim)

    # Gemini claim JSON'u boş/yanlış döndürürse kaynak zincirini sessizce boş bırakma.
    # Metni iddia adayı olarak kullanırız; bu bir Gemini hükmü değil, açıkça fallback'tir.
    claim_fallback_used = False
    if not claim and analyzed_content.strip():
        candidate = re.sub(r"https?://\S+", "", analyzed_content).strip()
        factual_markers = ("dır", "dir", "dur", "dür", "oldu", "olacak", "arttı", "azaldı", "yüzde", "resmi", "açıklama", "tüm", "her")
        if len(candidate) >= 25 and any(marker in stable_text(candidate) for marker in factual_markers):
            claim = candidate[:500]
            claims = [claim]
            claim_fallback_used = True
            claim_data["has_claim"] = True
            claim_data["search_query"] = claim

    has_claim = bool(claim)
    evidence = evidence_sources_for_claim(
        str(claim_data.get("search_query", "") or claim),
        source_url=source_url,
    ) if has_claim else []
    final_reasoning_status = "not_needed_no_claim"
    if has_claim:
        final_data = final_reasoning_with_gemini(analyzed_content, claim, evidence, language)
        final_reasoning_status = "success" if final_data else "fallback"
    else:
        english = language == "en"
        final_data = {
        "truthfulness": "Insufficient evidence" if english else "Kanıt yetersiz",
        "confidence": 0.0,
        "reason": (
            "AI analysis is pending; claim extraction or the live model could not be reached."
            if english and claim_data.get("error")
            else "No verifiable main claim could be extracted from the text."
            if english
            else "AI analizi beklemede; claim extraction veya canlı model bağlantısı kurulamadı."
            if claim_data.get("error")
            else "Metinde web üzerinden doğrulanabilir bir ana iddia çıkarılamadı."
        ),
        "score": 50,
        "manipulation": 0,
        "clickbait": 0,
        "emotion": "Neutral" if english else "Nötr",
        "polarization_risk": 0,
        "echo_chamber": "No verifiable claim was found." if english else "Doğrulanabilir iddia bulunmadı.",
        "ai_rewrite": analyzed_content[:300],
        "social_risk_summary": "No claim was found; toxicity was assessed separately." if english else "İddia yok; içerik toksisite açısından ayrıca değerlendirildi.",
        "validity": "Unclear" if english else "Belirsiz",
        "time_validity": "No time verification was performed because no claim was found." if english else "İddia bulunmadığı için zaman doğrulaması yapılmadı.",
        "context": "The content contains no claim or claim extraction failed." if english else "İçerik iddia içermiyor veya iddia çıkarımı başarısız oldu.",
        "explanation": "No verifiable claim was found." if english else "Kanıtlanabilir bir iddia bulunamadı.",
        "score_breakdown": "No claim: safe default score of 50/100." if english else "İddia yok: 50/100 güvenli varsayılan skor.",
    }

    toxicity = text_toxicity
    moderation = decide_moderation_action(toxicity, language)
    if language == "en":
        toxicity = ToxicityAnalysis(
            **{
                **toxicity.model_dump(),
                "targeted_person_or_group": "General" if toxicity.targeted_person_or_group == "Genel" else toxicity.targeted_person_or_group,
                "risk_level": {"Düşük": "Low", "Orta": "Medium", "Yüksek": "High"}.get(toxicity.risk_level, toxicity.risk_level),
                "context_note": (
                    f"Toxicity assessment: insult {toxicity.insult}/100, bullying {toxicity.bullying}/100, "
                    f"hate speech {toxicity.hate_speech}/100."
                ),
            }
        )
    supporting_urls = {normalize_url(str(url)) for url in final_data.get("supporting_urls", []) if str(url).strip()}
    contradicting_urls = {normalize_url(str(url)) for url in final_data.get("contradicting_urls", []) if str(url).strip()}
    # Gemini relation listesi URL listelerinden daha zengin olabilir; ikisini birleştir.
    for relation_item in final_data.get("evidence", []) if isinstance(final_data.get("evidence", []), list) else []:
        if not isinstance(relation_item, dict):
            continue
        relation_url = normalize_url(str(relation_item.get("url", "")))
        relation = stable_text(str(relation_item.get("relation", "")))
        if relation_url and relation in {"supports", "support", "destekler", "destekliyor"}:
            supporting_urls.add(relation_url)
        elif relation_url and relation in {"contradicts", "contradict", "çelişir", "çelişkili"}:
            contradicting_urls.add(relation_url)
    sources = []
    supporting_sources = []
    contradicting_sources = []
    for item in evidence:
        source = Source(
            title=item.get("title", "Kanıt kaynağı") or "Kanıt kaynağı",
            url=item.get("url", ""),
            relevance=item.get("content", "")[:220] or "Tavily arama sonucu",
            reliability=50,
            reliability_reason="Tavily üzerinden getirilen aday kanıt; nihai insan doğrulaması önerilir.",
        )
        sources.append(source)
        normalized = normalize_url(source.url)
        if normalized in supporting_urls:
            supporting_sources.append(source)
        if normalized in contradicting_urls:
            contradicting_sources.append(source)

    result = str(final_data.get("truthfulness", "Kanıt yetersiz")).strip() or "Kanıt yetersiz"
    analysis_result = AnalysisResponse(
        score=safe_score(final_data.get("score"), 50),
        manipulation=safe_score(final_data.get("manipulation")),
        clickbait=safe_score(final_data.get("clickbait")),
        result=result,
        explanation=str(final_data.get("reason", final_data.get("explanation", ""))).strip(),
        score_breakdown=str(final_data.get("score_breakdown", "")).strip(),
        validity=str(final_data.get("validity", "Belirsiz")).strip(),
        emotion=str(final_data.get("emotion", "Nötr")).strip(),
        time_validity=str(final_data.get("time_validity", "")).strip(),
        polarization_risk=safe_score(final_data.get("polarization_risk")),
        echo_chamber=str(final_data.get("echo_chamber", "")).strip(),
        ai_rewrite=str(final_data.get("ai_rewrite", analyzed_content[:300])).strip(),
        social_risk_summary=str(final_data.get("social_risk_summary", "")).strip(),
        toxicity=toxicity,
        toxicity_models=auxiliary_toxicity_models,
        moderation=moderation,
        verification=VerificationBadge(),
        claims=claims,
        context=str(final_data.get("context", "")).strip(),
        sources=sources,
        supporting_sources=supporting_sources,
        contradicting_sources=contradicting_sources,
        toxicity_label=toxicity_label,
        toxicity_confidence=toxicity_confidence,
        toxicity_engine="model" if model_available else "fallback",
        claim=claim,
        truthfulness=result,
        truthfulness_confidence=safe_score(float(final_data.get("confidence", 0.0)) * 100) / 100,
        evidence=[{"title": item.get("title", ""), "url": item.get("url", ""), "relation": "supports" if normalize_url(item.get("url", "")) in supporting_urls else "contradicts" if normalize_url(item.get("url", "")) in contradicting_urls else "context"} for item in evidence],
        pipeline_status={
            "toxicity_model": "ready" if model_available else "fallback",
            "gemini_claim_extraction": "fallback_candidate" if claim_fallback_used else "success" if claim_data.get("claim") else "fallback_or_no_claim",
            "tavily": dict(LAST_TAVILY_STATUS),
            "gemini_final_reasoning": final_reasoning_status,
            "claim_detected": bool(claim),
            "message": (
                "Gemini claim çıkarımı boş döndü; metin iddia adayı olarak Tavily'e gönderildi."
                if claim_fallback_used else
                "Gemini claim çıkarımı ve final reasoning tamamlandı."
                if final_reasoning_status == "success" else
                "Doğrulanabilir claim bulunamadı veya Gemini fallback moduna geçti."
            ),
        },
    )
    analysis_result.verification = compute_truthlens_verification(analysis_result, bool(source_url), language)
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
        "engine": "Custom Turkish BERT+LoRA + Gemini reasoning + Tavily evidence",
    }

@app.get("/health")
def health():
    return {
        "status": "healthy",
        "google_gemini_configured": bool(GOOGLE_API_KEY),
        "gemini_status": dict(LAST_GEMINI_STATUS),
        "tavily_configured": bool(TAVILY_API_KEY),
        "model": GEMINI_MODEL,
        "custom_toxicity_model": {
            "available": TOXICITY_SERVICE.available,
            "base_model": TOXICITY_BASE_MODEL,
            "model_id": TOXICITY_MODEL_ID,
            "source": "huggingface_hub",
            "hf_token_configured": bool(HF_TOKEN),
            "device": TOXICITY_SERVICE.device,
            "error": TOXICITY_SERVICE.error,
            "import_error": MODEL_IMPORT_ERROR,
        },
        "auxiliary_models": {
            "insult": {"available": INSULT_SERVICE.available, "model_id": INSULT_MODEL_ID, "labels": INSULT_SERVICE.id2label, "error": INSULT_SERVICE.error, "import_error": MODEL_IMPORT_ERROR},
            "bullying": {"available": BULLYING_SERVICE.available, "model_id": BULLYING_MODEL_ID, "labels": BULLYING_SERVICE.id2label, "error": BULLYING_SERVICE.error, "import_error": MODEL_IMPORT_ERROR},
            "hate_speech": {"available": HATE_SERVICE.available, "model_id": HATE_MODEL_ID, "labels": HATE_SERVICE.id2label, "error": HATE_SERVICE.error, "import_error": MODEL_IMPORT_ERROR},
        },
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

def estimate_source_match_probability(claim_text: str, candidate_text: str) -> int:
    """İddia ile aday kaynağın konu eşleşmesini kaba bir dilsel sinyalle ölçer.

    Bu değer birincil kaynak olma ihtimali değildir. Yalnızca ilgisiz
    sonuçları kaynak zincirinden ayıklamak için kullanılır.
    """
    # Çok genel kelimeler (haber, bugün, açıklama vb.) eşleşme sinyali olarak
    # kullanılmamalı; aksi halde Tavily'nin alakasız sonuçları yüksek skor alabiliyor.
    stop_tokens = {
        "haber", "haberler", "bugün", "dün", "açıklama", "açıklaması",
        "son", "sonra", "önce", "gün", "yeni", "olan", "olarak",
        "ilgili", "hakkında", "konu", "konusu", "türkiye", "türk",
        "resmi", "resmî", "paylaşım", "paylasim", "sosyal", "medya",
        "kaynak", "başkan", "bakan", "bakanlık", "devlet", "yıl",
    }
    claim_tokens = {
        token for token in re.findall(r"[\wçğıöşüÇĞİÖŞÜ]+", (claim_text or "").lower())
        if len(token) >= 4 and token not in stop_tokens
    }
    candidate_tokens = {
        token for token in re.findall(r"[\wçğıöşüÇĞİÖŞÜ]+", (candidate_text or "").lower())
        if len(token) >= 4 and token not in stop_tokens
    }
    if not claim_tokens or not candidate_tokens:
        return 0
    overlap = len(claim_tokens & candidate_tokens)
    # Recall-style oran: aday metnindeki ortak anlamlı kelimeler arttıkça skor yükselir.
    score = round((overlap / max(1, min(len(claim_tokens), 20))) * 100)
    return max(0, min(100, score))


def analyze_source_chain(
    title: str,
    description: str,
    body: str,
    current_url: str,
    current_date: str = "",
    current_site: str = "",
) -> dict:
    t_start = time.time()

    query = extract_claims_for_source_analysis(
        title,
        description,
        body,
    )

    if not query:
        return SourceAnalysis().model_dump()

    # Step 1: Query Formulation & suspected producer analysis via LLM
    t0_q = time.time()
    prompt_query = f"""
    Aşağıdaki içeriğin konusunu ve ana iddiasını analiz et.
    Bu iddianın ilk/gerçek üreticisi olan BİRİNCİL KAYNAĞI (official site, original social media post) bulabilmek için Tavily'de aratılacak 2 adet Türkçe ve arama operatörleri içeren detaylı arama sorgusu oluştur.
    Özellikle resmî kurumlar, resmî sosyal medya hesapları (X/Twitter, Facebook, Instagram vb.) ve haber kaynaklarına odaklan.
    
    Başlık: {title}
    Açıklama: {description}
    İçerik: {body[:1000]}
    
    Yalnızca JSON formatında yanıt ver:
    {{
      "suspected_primary_producer": "Olası ilk üretici kurum/kişi adı (örn. 'Millî Eğitim Bakanlığı')",
      "search_queries": [
        "arama sorgusu 1",
        "arama sorgusu 2"
      ]
    }}
    """

    queries = []
    try:
        raw_res = call_llm([{"role": "user", "content": prompt_query}], temperature=0.1)
        data_res = json.loads(raw_res)
        queries = [q for q in data_res.get("search_queries", []) if q]
    except Exception as e:
        print(f"[TruthLens] Query formulation error: {e}")

    dur_q = time.time() - t0_q
    print(f"[TruthLens] Source chain query formulation: {dur_q:.2f}s")

    if not queries:
        queries = [query]

    # Step 2: Tavily Search and URL Scraping
    t0_tavily = time.time()
    unique_urls = set()
    raw_results = []
    
    search_queries = queries[:2]
    with concurrent.futures.ThreadPoolExecutor(max_workers=len(search_queries) or 1) as search_executor:
        search_batches = list(search_executor.map(lambda q: search_with_tavily(q, max_results=3), search_queries))
    for results in search_batches:
        for r in results:
            url = r.get("url")
            if url and url not in unique_urls:
                unique_urls.add(url)
                raw_results.append(r)
                
    if current_url and current_url not in unique_urls:
        unique_urls.add(current_url)
        raw_results.append({
            "title": title or "Mevcut Paylaşım",
            "url": current_url,
            "content": body[:800]
        })

    dur_tavily = time.time() - t0_tavily
    print(f"[TruthLens] Source chain Tavily query: {dur_tavily:.2f}s")

    t_fetch_start = time.time()

    def process_candidate(item):
        item_url = str(item.get("url", "") or "").strip()
        item_title = str(item.get("title", "") or "").strip()
        item_content = str(item.get("content", "") or "").strip()
        
        published = ""
        author = ""
        site_name = get_domain(item_url)
        
        try:
            if item_url == current_url:
                published = current_date or published
                site_name = current_site or site_name
                
            # Mevcut gönderi sayfası zaten /analyze içinde indirildi; yeniden indirme.
            if item_url == current_url and body:
                item_content = body
            else:
                html = fetch_webpage(item_url)
                if html:
                    meta = extract_page_metadata(html, item_url)
                    published = parse_datetime_value(meta.get("published_time", "")) or published
                    author = str(meta.get("author", "") or "").strip()
                    site_name = str(meta.get("site_name", "") or site_name).strip()
                    if meta.get("title"):
                        item_title = str(meta.get("title")).strip()
                    if meta.get("article_body"):
                        item_content = str(meta.get("article_body")).strip()
        except Exception as exc:
            print(f"[TruthLens] Source metadata fetching error for {item_url}: {exc}")
            
        return {
            "title": item_title,
            "url": item_url,
            "date": published,
            "platform": site_name,
            "author": author,
            "excerpt": item_content[:500]
        }

    with concurrent.futures.ThreadPoolExecutor(max_workers=10) as executor:
        candidates = list(executor.map(process_candidate, raw_results))
        
    dur_fetch = time.time() - t_fetch_start
    print(f"[TruthLens] Concurrently fetched candidate metadata ({len(raw_results)} items): {dur_fetch:.2f}s")

    if not candidates:
        candidates.append({
            "title": title or "Paylaşım",
            "url": current_url or "",
            "date": current_date or "",
            "platform": current_site or (get_domain(current_url) if current_url else ""),
            "author": "",
            "excerpt": body[:300]
        })

    # Step 3: LLM evaluation of candidates to find the primary source
    candidates_formatted = []
    for idx, c in enumerate(candidates):
        candidates_formatted.append(
            f"Aday #{idx}\n"
            f"Başlık/Kaynak Adı: {c['title']}\n"
            f"URL: {c['url']}\n"
            f"Tarih/Saat: {c['date'] or 'Belirtilmemiş'}\n"
            f"Platform: {c['platform'] or 'Belirtilmemiş'}\n"
            f"Yazar/Hesap: {c['author'] or 'Belirtilmemiş'}\n"
            f"Alıntı: {c['excerpt']}\n"
            f"---"
        )
    candidates_str = "\n".join(candidates_formatted)
    
    prompt_evaluate = f"""
    Sen TruthLens AI Türkçe birincil kaynak tespit modülüsün.
    Aşağıda incelenen iddianın içeriği ve bu konuyla ilgili internetten toplanan aday kaynaklar verilmiştir.
    
    İNCELENEN İÇERİK:
    Başlık: {title}
    Açıklama: {description}
    İçerik: {body[:1000]}
    Mevcut URL: {current_url or "Belirtilmemiş"}
    Mevcut Tarih: {current_date or "Belirtilmemiş"}
    
    ADAY KAYNAKLAR:
    {candidates_str}
    
    Lütfen bu adayları analiz et:
    1. İddianın veya haberin ilk/gerçek üreticisi (BİRİNCİL KAYNAK) olan paylaşımı veya resmi duyuruyu tespit et.
    2. Bir kurumun resmi hesabı, resmi web sitesi (.gov.tr, vb.) veya doğrudan ilgili kişinin paylaşımı her zaman haber sitelerinden ve ikincil alıntılardan daha birincil sayılmalıdır.
    3. Yayınlanma tarihlerini karşılaştır. Daha erken yayınlananlar ve doğrudan resmi açıklama yapanlar önceliklidir.
    4. Her aday için "primary_probability" (bu adayın gerçek birincil kaynak/ilk paylaşım olma ihtimali %) değerini belirle.
       - Resmi kurum/kişi paylaşımıysa ve ilk paylaşım olduğu yüksek ihtimalse yüksek bir skor (%80-%100) ver.
       - Haber sitesi, ikincil aktarıcı veya sadece alıntı yapan bir siteyse daha düşük skor ver.
       - Eğer yeterli kanıt veya tarih bilgisi yoksa veya kesin doğrulanamıyorsa orta/düşük bir olasılık skoru ver.
    5. Her aday için ayrıca "match_probability" (incelenen içerikle konu/iddia eşleşme yüzdesi) belirle.
       - İddia ile doğrudan aynı olayı, duyuruyu veya metni ele alan kaynaklar yüksek skor almalı.
       - Sadece aynı genel konuya değinen ama farklı olayları anlatan sonuçlar düşük skor almalı.
       - Alakasız sonuçlara %25'in altında skor ver.
       - Bu değer BİRİNCİL KAYNAK olma ihtimali değildir; yalnızca içerikle eşleşme değeridir.
    6. Birincil kaynak olarak seçilen adayın detaylarını belirle:
       - `likely_original_source`: BİRİNCİL PAYLAŞIMI YAPAN HESABIN/KİŞİNİN GÖRÜNÜR ADI (örn. 'Millî Eğitim Bakanlığı', 'Ahmet Yılmaz'). Buraya yalnızca platform adı (X, Facebook, Instagram, NSosyal vb.) YAZMA; haber başlığını da kaynak adı olarak kullanma.
       - `likely_original_author`: Varsa hesabın kullanıcı adı/handle'ı (örn. '@tcmeb', '@ahmetyilmaz').
       - `likely_original_url`: Bu paylaşımın veya resmi duyurunun tam URL'si (asla domain ana sayfasını vermeyin, tam path olsun, örn: 'https://x.com/tcmeb/status/123456').
       - `likely_original_date`: Paylaşım tarihi.
       - `likely_original_excerpt`: Paylaşım metninden veya duyurudan kısa bir alıntı.
       - `likely_original_platform`: Hangi platformda yapıldığı (X, Facebook, Web Sitesi, Instagram vb.).
       
    Yanıtı sadece aşağıdaki JSON formatında döndür:
    {{
      "primary_source_index": 0,
      "primary_probability": 92,
      "source_status": "strong_candidate / candidate / uncertain",
      "reasoning": "Neden bu kaynağı ve bu yüzdeyi seçtiğine dair Türkçe açıklama. Kesinlik durumunu belirt.",
      "likely_original_source": "BİRİNCİL PAYLAŞIMI YAPAN HESABIN/KİŞİNİN GÖRÜNÜR ADI",
      "likely_original_author": "@kullaniciadi veya boş",
      "likely_original_url": "Tam paylaşım URL'si",
      "likely_original_date": "Tarih bilgisi",
      "likely_original_excerpt": "Kısa alıntı",
      "likely_original_platform": "Platform adı",
      "evaluated_candidates": [
        {{
          "source": "Temizlenmiş kaynak/kurum/kişi adı (asla sadece X veya Facebook yazma)",
          "author": "@kullaniciadi veya boş",
          "platform": "Platform adı (örn. X, Facebook, Web Sitesi)",
          "date": "Tarih bilgisi",
          "url": "Tam paylaşım URL'si (path korunacak)",
          "is_likely_primary": true,
          "primary_probability": 92,
          "match_probability": 95
        }}
      ]
    }}
    """

    t0_eval = time.time()
    try:
        raw_eval = call_llm([{"role": "user", "content": prompt_evaluate}], temperature=0.1)
        data_eval = json.loads(raw_eval)
        
        evaluated = data_eval.get("evaluated_candidates", [])
        if not isinstance(evaluated, list):
            evaluated = []

        # Adayları URL üzerinden gerçek Tavily adaylarıyla eşleştir.
        evaluated_by_url = {}
        for item in evaluated:
            if not isinstance(item, dict):
                continue
            item_url = str(item.get("url") or "").strip()
            if item_url:
                evaluated_by_url[item_url] = item

        enriched_candidates = []
        claim_text = f"{title} {description} {body}"
        for idx, candidate in enumerate(candidates):
            item = evaluated_by_url.get(candidate.get("url", ""), {})
            lexical_match = estimate_source_match_probability(
                claim_text,
                f"{candidate.get('title', '')} {candidate.get('excerpt', '')}",
            )
            llm_match = safe_score(item.get("match_probability"), -1)
            if llm_match < 0:
                llm_match = lexical_match
            else:
                # LLM'nin tek başına verdiği yüksek skorla alakasız sonuçların
                # kaynak zincirine girmesini engelle. En az %25 gerçek metin
                # eşleşmesi zorunlu.
                llm_match = min(llm_match, max(0, lexical_match))
            if candidate.get("url") == current_url:
                llm_match = 100

            primary_probability = safe_score(item.get("primary_probability"), 0)
            if not primary_probability:
                primary_probability = safe_score(candidate.get("score"), 0)

            enriched_candidates.append({
                **candidate,
                "match_probability": max(0, min(100, llm_match)),
                "primary_probability": max(0, min(100, primary_probability)),
                "is_likely_primary": bool(item.get("is_likely_primary", False)),
                "evaluated_source": str(item.get("source") or "").strip(),
                "evaluated_author": str(item.get("author") or "").strip(),
                "evaluated_platform": str(item.get("platform") or "").strip(),
                "evaluated_date": str(item.get("date") or "").strip(),
                "evaluated_excerpt": str(item.get("excerpt") or "").strip(),
            })

        # Kaynak zincirine yalnızca en az %25 gerçek eşleşme sağlayan
        # adaylar girer. %25'in altındaki sonuçlar kullanıcıya gösterilmez.
        relevant_candidates = [
            c for c in enriched_candidates
            if c.get("match_probability", 0) >= 25
        ]

        # Mevcut paylaşımın kendisi her zaman ilgili adaydır; içerik eşleşmesi 100'dür.
        if current_url:
            current_candidate = next(
                (c for c in enriched_candidates if c.get("url") == current_url),
                None,
            )
            if current_candidate and current_candidate not in relevant_candidates:
                relevant_candidates.append(current_candidate)

        relevant_candidates.sort(
            key=lambda c: (
                c.get("primary_probability", 0),
                c.get("match_probability", 0),
                bool(c.get("date")),
            ),
            reverse=True,
        )
        # Kullanıcıya gereksiz kalabalık vermemek için en fazla 4 gerçekten
        # eşleşen aday göster.
        relevant_candidates = relevant_candidates[:4]

        if not relevant_candidates:
            relevant_candidates = [
                {
                    "title": title or "Mevcut paylaşım",
                    "url": current_url or "",
                    "date": current_date or "",
                    "platform": current_site or (get_domain(current_url) if current_url else ""),
                    "author": "",
                    "excerpt": body[:500],
                    "match_probability": 100 if current_url else 0,
                    "primary_probability": 0,
                    "is_likely_primary": False,
                    "evaluated_source": "",
                    "evaluated_author": "",
                    "evaluated_platform": "",
                    "evaluated_date": "",
                    "evaluated_excerpt": "",
                }
            ]

        # Birincil aday: LLM'nin seçimi ilgili adaylar arasındaysa onu kullan;
        # değilse en yüksek birincil olasılıklı ilgili kaynağa düş.
        primary_source_index = data_eval.get("primary_source_index", -1)
        selected = None
        if isinstance(primary_source_index, int) and 0 <= primary_source_index < len(candidates):
            selected_url = candidates[primary_source_index].get("url", "")
            selected = next(
                (c for c in relevant_candidates if c.get("url") == selected_url),
                None,
            )
        if selected is None:
            selected = max(
                relevant_candidates,
                key=lambda c: (c.get("primary_probability", 0), c.get("match_probability", 0)),
            )

        # Ana kaynak alanlarını LLM boş bıraktığında gerçek aday metadata'sından doldur.
        likely_original_author = str(data_eval.get("likely_original_author") or selected.get("evaluated_author") or selected.get("author") or "").strip()
        likely_original_source = str(data_eval.get("likely_original_source") or selected.get("evaluated_source") or likely_original_author or selected.get("title") or "Birincil kaynak adayı").strip()
        likely_original_url = str(data_eval.get("likely_original_url") or selected.get("url") or "").strip()
        likely_original_date = str(data_eval.get("likely_original_date") or selected.get("evaluated_date") or selected.get("date") or "").strip()
        likely_original_excerpt = str(data_eval.get("likely_original_excerpt") or selected.get("evaluated_excerpt") or selected.get("excerpt") or "").strip()
        likely_original_platform = str(data_eval.get("likely_original_platform") or selected.get("evaluated_platform") or selected.get("platform") or "").strip()

        primary_prob = safe_score(data_eval.get("primary_probability"), 0)
        if primary_prob <= 0:
            primary_prob = safe_score(selected.get("primary_probability"), 0)

        status = str(data_eval.get("source_status") or "uncertain").strip()
        if primary_prob >= 75:
            status = "strong_candidate"
        elif primary_prob >= 50:
            status = "candidate"
        else:
            status = "uncertain"

        reasoning = str(data_eval.get("reasoning") or "İçerikle eşleşen aday kaynaklar filtrelendi ve birincil aday değerlendirildi.").strip()

        source_chain_items = []
        for candidate in relevant_candidates:
            source_chain_items.append(
                SourceChainItem(
                    source=(candidate.get("evaluated_source") or candidate.get("author") or candidate.get("title") or "Kaynak"),
                    url=candidate.get("url") or "",
                    date=candidate.get("evaluated_date") or candidate.get("date") or "",
                    platform=candidate.get("evaluated_platform") or candidate.get("platform") or "",
                    author=candidate.get("evaluated_author") or candidate.get("author") or "",
                    is_likely_primary=(candidate.get("url") == selected.get("url")),
                    primary_probability=safe_score(candidate.get("primary_probability"), 0),
                    match_probability=safe_score(candidate.get("match_probability"), 0),
                )
            )

        dur_eval = time.time() - t0_eval
        print(f"[TruthLens] Source chain LLM eval: {dur_eval:.2f}s")
        print(f"[TruthLens] Total Source chain: {time.time() - t_start:.2f}s")

        return SourceAnalysis(
            source_status=status,
            source_probability=primary_prob,
            likely_original_source=likely_original_source,
            likely_original_author=likely_original_author,
            likely_original_url=likely_original_url,
            likely_original_date=likely_original_date,
            likely_original_excerpt=likely_original_excerpt,
            likely_original_platform=likely_original_platform,
            earliest_found_source=likely_original_source,
            earliest_found_date=likely_original_date,
            current_source_date=current_date,
            source_chain=source_chain_items,
            reasoning=reasoning
        ).model_dump()

    except Exception as e:
        print(f"[TruthLens] LLM evaluation error in analyze_source_chain: {e}")
        source_chain_items = []
        for c in candidates:
            source_chain_items.append(
                SourceChainItem(
                    source=c.get("author") or c.get("title") or "Aday",
                    url=c.get("url") or "",
                    date=c.get("date") or "",
                    platform=c.get("platform") or "",
                    author=c.get("author") or "",
                    is_likely_primary=False,
                    primary_probability=0,
                    match_probability=estimate_source_match_probability(
                        f"{title} {description} {body}",
                        f"{c.get('title', '')} {c.get('excerpt', '')}",
                    ),
                )
            )
        fallback_candidates = [
            item for item in source_chain_items
            if item.url and item.match_probability >= 25
        ]
        fallback_candidates.sort(
            key=lambda item: item.match_probability,
            reverse=True,
        )
        return SourceAnalysis(
            source_status="partial_error",
            source_probability=0,
            likely_original_source=(
                "Aday kaynaklar bulundu — birincil kaynak doğrulaması bekliyor"
                if fallback_candidates else "Kaynak adayı bulunamadı"
            ),
            likely_original_url=fallback_candidates[0].url if fallback_candidates else "",
            likely_original_platform=fallback_candidates[0].platform if fallback_candidates else "",
            current_source_date=current_date,
            source_chain=fallback_candidates,
            reasoning=(
                "Kaynak araması tamamlandı; ancak birincil kaynak değerlendirmesi "
                "zaman aşımı nedeniyle tamamlanamadı. Aşağıdaki bağlantılar doğrulanmış "
                "birincil kaynak değil, incelenmesi gereken aday kaynaklardır."
                if fallback_candidates
                else "Kaynak araması sırasında zaman aşımı oluştu ve gösterilebilir aday kaynak bulunamadı."
            ),
        ).model_dump()

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
    expires_at = (datetime.now(timezone.utc) + timedelta(hours=24)).isoformat()
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

@app.post("/moderation/appeal")
def moderation_appeal(payload: dict, request: Request):
    user = get_current_user_from_request(request)
    if not user:
        raise HTTPException(
            status_code=401,
            detail="İtiraz göndermek için giriş yapmalısın.",
        )

    content_hash = str(payload.get("content_hash", "")).strip()
    appeal_reason = str(payload.get("appeal_reason", "")).strip()
    if not content_hash or not appeal_reason:
        raise HTTPException(
            status_code=400,
            detail="content_hash ve appeal_reason gerekli.",
        )

    updated = submit_moderation_appeal(
        content_hash,
        appeal_reason,
        user_id=user["id"],
    )
    if not updated:
        raise HTTPException(
            status_code=404,
            detail="Bu içerik için hesabına ait bir moderasyon kararı bulunamadı.",
        )

    return {"status": "ok", **updated}


@app.get("/moderation/history")
def moderation_history(request: Request, limit: int = 50):
    user = get_current_user_from_request(request)
    if not user:
        raise HTTPException(status_code=401, detail="Oturum doğrulanamadı.")

    conn = get_db_connection()
    rows = conn.execute(
        """
        SELECT
            content_hash,
            action,
            aggregate_risk,
            reason,
            created_at,
            appeal_status,
            appeal_reason,
            appeal_created_at
        FROM moderation_decisions
        WHERE user_id = ?
        ORDER BY id DESC
        LIMIT ?
        """,
        (user["id"], max(1, min(limit, 100))),
    ).fetchall()
    conn.close()

    return {
        "items": [dict(r) for r in rows],
        "action_distribution": {
            action: sum(1 for r in rows if r["action"] == action)
            for action in {
                "izin_ver",
                "etiketle",
                "gizle_ve_incele",
                "kaldirma_oner",
            }
        },
    }


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
    t_start = time.time()
    
    original = (request_body.content or request_body.text or "").strip()
    if not original:
        raise HTTPException(status_code=400, detail="İçerik boş olamaz.")

    t_url_start = time.time()
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

    dur_url = time.time() - t_url_start
    print(f"[TruthLens] URL extraction & scraping: {dur_url:.2f}s")

    image_ai_probability = 0
    image_is_ai = None
    image_analysis_available = False
    image_text = ""
    image_toxicity = ToxicityAnalysis()
    image_moderation_note = ""
    source_analysis = SourceAnalysis()

    # Parallel execution using ThreadPoolExecutor
    with concurrent.futures.ThreadPoolExecutor(max_workers=3) as executor:
        # Submit run_analysis
        future_result = executor.submit(run_analysis, analyzed_content, source_url, request_body.language)
        
        # Submit detect_ai_image if primary_image exists
        future_image = None
        if url:
            metadata = (post.get("metadata") or {}) if "post" in locals() else {}
            primary_image = str(metadata.get("image_url", "") or "").strip()
            if primary_image:
                future_image = executor.submit(
                    analyze_image_ai_probability,
                    primary_image,
                    source_url or url,
                )
                
        # Yeni ana pipeline claim extraction -> Tavily -> final reasoning adımlarını
        # run_analysis içinde çalıştırır. Eski kaynak-zinciri LLM çağrıları burada
        # tekrar edilmez; böylece URL analizinde Gemini çağrısı iki ile sınırlıdır.
        future_source = None
            
        # Get run_analysis result
        try:
            result = future_result.result()
        except Exception as e:
            print(f"[TruthLens] run_analysis thread error: {e}")
            result = AnalysisResponse(
                score=50, manipulation=25, clickbait=20,
                result="Kanıt yetersiz", explanation="Thread hatası.",
                score_breakdown="Hata.", validity="Belirsiz", emotion="Nötr",
                time_validity="Hata.", polarization_risk=15,
                echo_chamber="Hata.", ai_rewrite="Hata.",
                social_risk_summary="Thread hatası nedeniyle analiz yapılamadı.",
                claims=[], context="Hata.",
                sources=[], supporting_sources=[], contradicting_sources=[],
                image_text="", image_toxicity=ToxicityAnalysis(),
                image_moderation_note="Hata.", source_analysis=SourceAnalysis(),
            )
        
        # Get image analysis result
        if future_image:
            try:
                image_analysis = future_image.result()
                if image_analysis:
                    image_analysis_available = bool(image_analysis.get("image_analysis_available", False))
                    image_ai_probability = safe_score(
                        image_analysis.get("image_ai_probability", image_analysis.get("ai_probability"))
                    )
                    image_is_ai = image_analysis.get("is_ai")
                    image_text = str(image_analysis.get("visible_text", "") or "").strip()
                    try:
                        image_toxicity = ToxicityAnalysis(**(image_analysis.get("image_toxicity") or {}))
                    except Exception:
                        image_toxicity = ToxicityAnalysis()
                    image_moderation_note = str(
                        image_analysis.get("image_analysis_reasoning", "") or ""
                    ).strip()
            except Exception as e:
                print(f"[TruthLens] Image analysis thread error: {e}")
                image_analysis_available = False
                
        # Get source analysis result
        if future_source:
            try:
                source_analysis = future_source.result()
            except Exception as e:
                print(f"[TruthLens] Source analysis thread error: {e}")
                source_analysis = SourceAnalysis()

    # Görseldeki argo/hakaret/nefret sinyalini metin toksisitesiyle birleştir.
    # Görsel AI olasılığı tek başına moderasyon sebebi değildir; yalnızca görsel
    # metni veya görsel güvenlik sınıfları sinyal ürettiğinde karar yükseltilir.
    # HER ZAMAN merge yapıyoruz, image_toxicity her zaman set edilmiştir
    combined_toxicity = merge_toxicity_signals(result.toxicity, image_toxicity, request_body.language)
    image_response_toxicity = image_toxicity
    if request_body.language == "en":
        image_response_toxicity = image_toxicity.model_copy(update={
            "targeted_person_or_group": "General" if image_toxicity.targeted_person_or_group == "Genel" else image_toxicity.targeted_person_or_group,
            "risk_level": {"Düşük": "Low", "Orta": "Medium", "Yüksek": "High"}.get(image_toxicity.risk_level, image_toxicity.risk_level),
            "context_note": (
                f"Image toxicity assessment: insult {image_toxicity.insult}/100, "
                f"bullying {image_toxicity.bullying}/100, hate speech {image_toxicity.hate_speech}/100."
            ),
        })
    result = result.model_copy(update={
        "toxicity": combined_toxicity,
        "toxicity_label": "toxic" if max(combined_toxicity.insult, combined_toxicity.bullying, combined_toxicity.hate_speech) > 0 else result.toxicity_label,
        "toxicity_confidence": max(result.toxicity_confidence, 0.0),
        "moderation": decide_moderation_action(combined_toxicity, request_body.language),
        "image_text": image_text,
        "image_toxicity": image_response_toxicity,
        "image_moderation_note": image_moderation_note,
    })

    # Kaynak zincirindeki doğrulanmış adayları ana destekleyen kaynaklar
    # bölümüne de aktar. Böylece alt bölüm boş kalmaz; ancak gerçek bir
    # çelişki kanıtı yoksa yapay bir "çelişkili kaynak" UYDURULMAZ.
    if url and isinstance(source_analysis, SourceAnalysis):
        chain = source_analysis.source_chain or []
        if not result.supporting_sources and chain:
            support_candidates = [c for c in chain if c.match_probability >= 25]
            support_candidates = sorted(
                support_candidates,
                key=lambda c: (c.is_likely_primary, c.primary_probability, c.match_probability),
                reverse=True,
            )[:2]
            result = result.model_copy(update={
                "supporting_sources": [
                    Source(
                        title=(c.source or "Kaynak adayı"),
                        url=c.url,
                        relevance=(
                            f"İçerikle eşleşme %{c.match_probability}; "
                            f"birincil olasılık %{c.primary_probability}."
                        ),
                        reliability=80 if c.is_likely_primary else 70,
                        reliability_reason=(
                            "Kaynak zincirinde içerikle en az %25 eşleşen aday; "
                            "LLM doğrulaması tamamlanmış olabilir veya bekliyor olabilir."
                        ),
                    )
                    for c in support_candidates
                    if c.url
                ]
            })

        # LLM değerlendirmesi timeout olsa bile Tavily’den gelen adayları boş bırakma.
        # Bunlar doğrulanmış kaynak değil, açıkça etiketlenmiş inceleme adaylarıdır.
        if not result.sources and chain:
            candidate_sources = sorted(
                [c for c in chain if c.url and c.match_probability >= 10],
                key=lambda c: (c.match_probability, c.primary_probability),
                reverse=True,
            )[:4]
            if candidate_sources:
                result = result.model_copy(update={
                    "sources": [
                        Source(
                            title=f"{c.source or c.author or 'Kaynak adayı'} — aday",
                            url=c.url,
                            relevance=f"İçerikle eşleşme %{c.match_probability}; doğrulama durumu: aday.",
                            reliability=0,
                            reliability_reason=(
                                "Tavily adayı; birincil kaynak doğrulaması tamamlanmadı."
                            ),
                        )
                        for c in candidate_sources
                    ]
                })

    # Yeni pipeline kaynakları, mevcut source_analysis kartı için deterministik
    # bir kaynak zinciri görünümüne çevrilir; ek LLM çağrısı yapılmaz.
    if url and not source_analysis.source_chain and result.sources:
        source_analysis = SourceAnalysis(
            source_status="candidate",
            source_probability=0,
            likely_original_source=result.sources[0].title,
            likely_original_url=result.sources[0].url,
            current_source_date="",
            source_chain=[
                SourceChainItem(
                    source=item.title,
                    url=item.url,
                    platform=get_domain(item.url),
                    match_probability=100 if item in result.supporting_sources else 50,
                )
                for item in result.sources
            ],
            reasoning="Kaynak zinciri, yeni claim → Tavily → Gemini kanıt akışındaki gerçek URL’lerden oluşturuldu.",
        )

    content_hash = analysis_cache_key(analyzed_content, source_url, request_body.language)
    result = result.model_copy(update={
        "content_hash": content_hash,
        "image_ai_probability": image_ai_probability,
        "image_is_ai": image_is_ai,
        "image_analysis_available": image_analysis_available,
        "image_text": image_text,
        "image_toxicity": image_response_toxicity,
        "image_moderation_note": image_moderation_note,
        "source_analysis": source_analysis if isinstance(source_analysis, SourceAnalysis) else SourceAnalysis(**source_analysis),
    })

    result = result.model_copy(update={
        "verification": compute_truthlens_verification(result, has_source_url=bool(source_url), language=request_body.language),
    })

    user = get_current_user_from_request(request)
    if not user and result.moderation.appeal_eligible:
        result = result.model_copy(update={
            "moderation": result.moderation.model_copy(update={"appeal_eligible": False}),
        })
    log_moderation_decision(
        content_hash,
        result.moderation,
        user_id=user["id"] if user else None,
    )
    if user:
        result_payload = json.loads(result.model_dump_json())
        save_analysis_history(user["id"], content_hash, source_url, result_payload)

    dur_total = time.time() - t_start
    print(f"[TruthLens] Total analyze endpoint: {dur_total:.2f}s")
    return result

@app.post("/analyze-url", response_model=AnalysisResponse)
def analyze_url(payload: dict, request: Request):
    url = str(payload.get("url", "")).strip()
    if not url:
        raise HTTPException(status_code=400, detail="URL gerekli.")
    language = payload.get("language", "tr")
    return analyze(AnalysisRequest(content=url, language=language), request)


@app.post("/nsosyal/moderation-check")
def nsosyal_moderation_check(payload: dict, request: Request):
    """NSosyal gönderi oluşturma akışının entegrasyona hazır moderasyon adapteri."""
    content = str(payload.get("content", "")).strip()
    if not content:
        raise HTTPException(status_code=400, detail="Gönderi metni gerekli.")
    if len(content) > 10000:
        raise HTTPException(status_code=422, detail="Gönderi metni 10.000 karakteri aşamaz.")

    result = analyze(AnalysisRequest(content=content, language=payload.get("language", "tr")), request)
    moderation = result.moderation
    publish_allowed = moderation.action in {"izin_ver", "etiketle"}
    publish_state = "allow_with_label" if moderation.action == "etiketle" else (
        "allow" if publish_allowed else "hold_for_human_review"
    )

    return {
        "adapter": {
            "platform": "NSosyal",
            "status": "ready_for_platform_adapter",
            "api_version": "v1",
            "contract": {
                "input": "post.content",
                "output": "moderation.action, moderation.reason, toxicity, human_review, publish_state",
                "irreversible_actions": "never_automatic",
            },
        },
        "content": content,
        "content_hash": result.content_hash,
        "toxicity": result.toxicity.model_dump(),
        "moderation": moderation.model_dump(),
        "verification": result.verification.model_dump(),
        "publish": {
            "allowed": publish_allowed,
            "state": publish_state,
            "label_required": moderation.action == "etiketle",
            "human_review_required": moderation.requires_human_review,
            "message": (
                "Gönderi NSosyal yayın akışına bırakılabilir; uyarı etiketi eklenir."
                if moderation.action == "etiketle"
                else "Gönderi yayınlanabilir."
                if moderation.action == "izin_ver"
                else "Gönderi yayın kuyruğuna alınmaz; insan moderatör incelemesi gerekir."
            ),
        },
    }


@app.get("/demo-feed")
def demo_feed(language: Literal["tr", "en"] = "tr"):
    posts = build_demo_feed()
    return {
        "posts": posts,
        "summary": summarize_demo_feed(posts, language),
    }


@app.get("/bluesky-feed")
def bluesky_feed(limit: int = BLUESKY_FEED_LIMIT, language: Literal["tr", "en"] = "tr"):
    payload = fetch_bluesky_feed(limit=limit, language=language)
    if payload.get("posts"):
        return payload

    demo_posts = build_demo_feed()
    return {
        "posts": demo_posts,
        "summary": summarize_demo_feed(demo_posts, language),
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


def require_bluesky_client() -> Client:
    if not BLUESKY_HANDLE or not BLUESKY_APP_PASSWORD:
        raise HTTPException(status_code=503, detail="Bluesky sağlayıcısı yapılandırılmamış; demo modu kullanılabilir.")
    return get_bluesky_client()


@app.get("/social/profile")
def social_profile():
    client = require_bluesky_client()
    profile = client.get_profile(actor=BLUESKY_HANDLE)
    return {
        "provider": "bluesky",
        "profile": {
            "did": str(getattr(profile, "did", "")),
            "handle": str(getattr(profile, "handle", BLUESKY_HANDLE)),
            "display_name": str(getattr(profile, "display_name", "") or ""),
            "description": str(getattr(profile, "description", "") or ""),
            "avatar": str(getattr(profile, "avatar", "") or ""),
            "followers_count": int(getattr(profile, "followers_count", 0) or 0),
            "follows_count": int(getattr(profile, "follows_count", 0) or 0),
            "posts_count": int(getattr(profile, "posts_count", 0) or 0),
        },
    }


@app.post("/social/create-post")
def social_create_post(payload: dict):
    content = str(payload.get("content", "")).strip()
    if not content:
        raise HTTPException(status_code=400, detail="Gönderi metni gerekli.")
    client = require_bluesky_client()
    response = client.send_post(text=content)
    return {
        "provider": "bluesky",
        "status": "published",
        "post": {
            "uri": str(getattr(response, "uri", "")),
            "cid": str(getattr(response, "cid", "")),
            "content": content,
        },
    }


@app.post("/social/like")
def social_like(payload: dict):
    uri = str(payload.get("uri", "")).strip()
    cid = str(payload.get("cid", "")).strip()
    if not uri or not cid:
        raise HTTPException(status_code=400, detail="uri ve cid gerekli.")
    client = require_bluesky_client()
    response = client.like(uri=uri, cid=cid)
    return {"provider": "bluesky", "status": "liked", "uri": uri, "cid": cid, "like_uri": str(getattr(response, "uri", ""))}


@app.post("/social/repost")
def social_repost(payload: dict):
    uri = str(payload.get("uri", "")).strip()
    cid = str(payload.get("cid", "")).strip()
    if not uri or not cid:
        raise HTTPException(status_code=400, detail="uri ve cid gerekli.")
    client = require_bluesky_client()
    response = client.repost(uri=uri, cid=cid)
    return {"provider": "bluesky", "status": "reposted", "uri": uri, "cid": cid, "repost_uri": str(getattr(response, "uri", ""))}


@app.post("/demo-feed/analyze")
def demo_feed_analyze(payload: dict):
    """Feed içeriğini gerçek analiz motorundan geçirir; skorlar istemciden kabul edilmez."""
    content = str(payload.get("content", "")).strip()
    if not content:
        raise HTTPException(status_code=400, detail="Analiz edilecek içerik gerekli.")

    language = payload.get("language", "tr")
    analysis = run_analysis(content, language=language)
    toxicity = analysis.toxicity.model_dump()
    post = {
        "id": payload.get("id") or f"demo-{uuid.uuid4().hex[:8]}",
        "author": payload.get("author") or "demo_user",
        "handle": payload.get("handle") or "@demo_user",
        "content": content,
        "tag": payload.get("tag") or "Genel",
        "truthlens_score": analysis.score,
        "misinformation_risk": max(0, min(100, 100 - analysis.score)),
        "manipulation": analysis.manipulation,
        "clickbait": analysis.clickbait,
        "emotion": analysis.emotion,
        "risk_level": toxicity.get("risk_level", "Belirsiz"),
        "reason": analysis.explanation,
        "toxicity": toxicity,
        "analysis_source": "TruthLens gerçek analiz motoru",
    }
    return {"post": post, "summary": summarize_demo_feed([post])}


@app.post("/analyze-image", response_model=ImageAnalysis)
def analyze_image(payload: ImageAnalysisRequest):
    image_url = payload.image_url.strip()
    source_url = payload.source_url.strip()
    if not image_url:
        raise HTTPException(status_code=400, detail="Görsel URL gerekli.")

    result = analyze_image_ai_probability(image_url, source_url)
    return ImageAnalysis(
        image_ai_probability=safe_score(result.get("image_ai_probability")),
        image_is_ai=result.get("is_ai"),
        image_analysis_available=bool(result.get("image_analysis_available", False)),
        image_analysis_reasoning=str(result.get("image_analysis_reasoning", "") or ""),
        visible_text=str(result.get("visible_text", "") or ""),
        image_toxicity=ToxicityAnalysis(**(result.get("image_toxicity") or {})),
        image_url=image_url,
    )


if __name__ == "__main__":
    import uvicorn
    uvicorn.run("main:app", host="0.0.0.0", port=8000, reload=True)
