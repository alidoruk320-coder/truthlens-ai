"use client";

import { useEffect, useState } from "react";

interface Source {
  title: string;
  url: string;
  relevance: string;
  reliability?: number;
  reliability_reason?: string;
}

interface ToxicityResult {
  insult: number;
  bullying: number;
  hate_speech: number;
  targeted_person_or_group: string;
  risk_level: string;
  context_note: string;
}
interface AuxiliaryToxicityModels {
  insult?: { score?: number; engine?: string; available?: boolean; error?: string; raw?: Record<string, number> };
  bullying?: { score?: number; gender_bullying?: number; racist_bullying?: number; harassment?: number; neutral?: number; engine?: string; available?: boolean; error?: string; raw?: Record<string, number> };
  hate_speech?: { engine?: string; available?: boolean; error?: string; raw?: Record<string, number> };
}

interface ModerationResult {
  action: "izin_ver" | "etiketle" | "gizle_ve_incele" | "kaldirma_oner";
  action_label: string;
  reason: string;
  requires_human_review: boolean;
  appeal_eligible: boolean;
  aggregate_risk: number;
}

interface VerificationBadge {
  verified: boolean;
  label: string;
  short_label: string;
  reasons?: string[];
}

interface ModerationHistoryItem {
  content_hash: string;
  action: "izin_ver" | "etiketle" | "gizle_ve_incele" | "kaldirma_oner";
  aggregate_risk: number;
  reason: string;
  created_at: string;
  appeal_status?: string | null;
  appeal_reason?: string | null;
  appeal_created_at?: string | null;
}

interface AnalysisResult {
  content_hash?: string;
  score: number;
  manipulation: number;
  clickbait: number;
  result: string;
  explanation: string;
  score_breakdown: string;
  validity: string;
  emotion: string;
  time_validity: string;
  polarization_risk: number;
  echo_chamber: string;
  ai_rewrite: string;
  social_risk_summary: string;
  toxicity?: ToxicityResult;
  toxicity_models?: AuxiliaryToxicityModels;
  moderation?: ModerationResult;
  verification?: VerificationBadge;
  claims: string[];
  context: string;
  sources: Source[];
  supporting_sources: Source[];
  contradicting_sources: Source[];
  image_ai_probability?: number;
  image_analysis_available?: boolean;
  image_analysis_reasoning?: string;
  image_text?: string;
  image_toxicity?: ToxicityResult;
  image_moderation_note?: string;
  toxicity_label?: "toxic" | "notoxic";
  toxicity_confidence?: number;
  toxicity_engine?: "model" | "fallback";
  claim?: string;
  truthfulness?: string;
  truthfulness_confidence?: number;
  evidence?: { title: string; url: string; relation: string }[];
  pipeline_status?: {
    toxicity_model?: string;
    gemini_claim_extraction?: string;
    tavily?: { status?: string; count?: number; query?: string; error?: string };
    gemini_final_reasoning?: string;
    claim_detected?: boolean;
    message?: string;
  };
  source_analysis?: {
    source_status?: string;
    source_probability?: number;
    likely_original_source?: string;
    likely_original_author?: string;
    likely_original_url?: string;
    likely_original_date?: string;
    likely_original_excerpt?: string;
    likely_original_platform?: string;
    earliest_found_source?: string;
    earliest_found_date?: string;
    current_source_date?: string;
    source_chain?: {
      source: string;
      url?: string;
      date: string;
      platform?: string;
      author?: string;
      is_likely_primary?: boolean;
      primary_probability?: number;
      match_probability?: number;
    }[];
    reasoning?: string;
  };
}

interface NsosyalModerationCheck {
  adapter: {
    platform: string;
    status: string;
    api_version: string;
    contract: { input: string; output: string; irreversible_actions: string };
  };
  content: string;
  content_hash: string;
  toxicity: ToxicityResult;
  moderation: ModerationResult;
  verification: VerificationBadge;
  publish: {
    allowed: boolean;
    state: string;
    label_required: boolean;
    human_review_required: boolean;
    message: string;
  };
}

interface FeedPost {
  id: string;
  author: string;
  handle: string;
  avatar: string;
  content: string;
  tag: string;
  source_url?: string;
  cid?: string;
  image_urls?: string[];
  engagement?: {
    likes?: number;
    reposts?: number;
    replies?: number;
  };
  analysis_status?: string;
  truthlens_score?: number;
  misinformation_risk?: number;
  polarization?: number;
  hate_speech?: number;
  spam_risk?: number;
  sentiment?: string;
  summary?: string;
  reason?: string;
  risk_level?: string;
  manipulation?: number;
  clickbait?: number;
  emotion?: string;
  ai?: {
    summary?: string;
    misinformation_risk?: number;
    polarization?: number;
    hate_speech?: number;
    spam_risk?: number;
    sentiment?: string;
    reasoning?: string;
  };
  image_ai_probability?: number;
  image_analysis_available?: boolean;
  image_analysis_reasoning?: string;
  verification?: VerificationBadge;
  verified_by_truthlens?: boolean;
}

type InputMode = "text" | "url";

export default function Home() {
  const [mode, setMode] = useState<InputMode>("text");

  const [content, setContent] = useState("");
  const [url, setUrl] = useState("");

  const [result, setResult] = useState<AnalysisResult | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");
  const [token, setToken] = useState<string | null>(null);
  const [authMode, setAuthMode] = useState<"login" | "register">("login");
  const [name, setName] = useState("");
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [user, setUser] = useState<{name: string; email: string} | null>(null);
  const [history, setHistory] = useState<any[]>([]);
  const [demoFeed, setDemoFeed] = useState<FeedPost[]>([]);
  const [demoSummary, setDemoSummary] = useState<any>(null);
  const [feedOpen, setFeedOpen] = useState(false);
  const [feedSource, setFeedSource] = useState<"live" | "demo">("live");
  const [feedRefreshing, setFeedRefreshing] = useState(false);
  const [feedLimit, setFeedLimit] = useState(5);
  const [sourceChainOpen, setSourceChainOpen] = useState(false);
  const [appealReason, setAppealReason] = useState("");
  const [appealSent, setAppealSent] = useState(false);
  const [appealSending, setAppealSending] = useState(false);
  // URL analizinde yüksek riskli içerik ilk etapta gizlenir; kullanıcı isterse görüntülemeyi açar.
  const [urlModerationOverride, setUrlModerationOverride] = useState(false);
  const [moderationHistory, setModerationHistory] = useState<ModerationHistoryItem[]>([]);
  const [moderationHistoryLoading, setModerationHistoryLoading] = useState(false);
  const [moderationHistoryError, setModerationHistoryError] = useState("");
  const [nsosyalDraft, setNsosyalDraft] = useState("");
  const [nsosyalCheck, setNsosyalCheck] = useState<NsosyalModerationCheck | null>(null);
  const [nsosyalChecking, setNsosyalChecking] = useState(false);
  const [nsosyalPublished, setNsosyalPublished] = useState(false);
  const [socialView, setSocialView] = useState<"home" | "liked" | "profile" | "settings">("home");
  const [likedPostIds, setLikedPostIds] = useState<Set<string>>(new Set());
  const [socialActionStatus, setSocialActionStatus] = useState("");
  const API_BASE_URL = process.env.NEXT_PUBLIC_API_BASE_URL || "http://127.0.0.1:8000";
  const insultModel = result?.toxicity_models?.insult;
  const bullyingModel = result?.toxicity_models?.bullying;
  const hateModel = result?.toxicity_models?.hate_speech;
  const insultScoreText = typeof insultModel?.score === "number" ? `${insultModel.score.toFixed(2)}%` : Object.keys(insultModel?.raw ?? {}).length > 0 ? "Model kullanılamadı" : "Model kullanılamadı";
  const bullyingScoreText = typeof bullyingModel?.score === "number" ? `${bullyingModel.score.toFixed(2)}%` : Object.keys(bullyingModel?.raw ?? {}).length > 0 ? "Model kullanılamadı" : "Model kullanılamadı";
  const hateRawEntries = Object.entries(hateModel?.raw ?? {});
  const hateLabelDisplay: Record<string, string> = {
    LABEL_0: "Nötr / normal içerik",
    LABEL_1: "Saldırgan / aşağılayıcı içerik",
    LABEL_2: "Nefret söylemi",
  };

  const safetyScore = result?.score ?? 0;
  const riskTrend = user ? Math.max(0, Math.min(100, Math.round(100 - safetyScore))) : 0;
  const trustQuality = user ? (result?.score ?? Math.round((history.length * 100) / Math.max(history.length + 1, 1))) : 0;
  const hasSourceAnalysis = Boolean(
    result?.source_analysis &&
      ((result.source_analysis.likely_original_source && result.source_analysis.likely_original_source.length > 0) ||
        (result.source_analysis.source_chain && result.source_analysis.source_chain.length > 0) ||
        (result.source_analysis.source_probability && result.source_analysis.source_probability > 0))
  );



  async function fetchCurrentUser(activeToken: string) {
    try {
      const meResponse = await fetch(`${API_BASE_URL}/me`, {
        headers: {
          Authorization: `Bearer ${activeToken}`,
        },
      });

      if (meResponse.ok) {
        const meData = await meResponse.json();
        setUser(meData.user);
        await fetchHistory(activeToken);
        await fetchModerationHistory(activeToken);
      } else {
        window.localStorage.removeItem("truthlens_token");
        setToken(null);
        setUser(null);
      }
    } catch (err) {
      console.error("Kullanıcı profili alınamadı", err);
    }
  }

  async function fetchHistory(activeToken: string) {
    try {
      const historyResponse = await fetch(`${API_BASE_URL}/history`, {
        headers: {
          Authorization: `Bearer ${activeToken}`,
        },
      });

      if (historyResponse.ok) {
        const historyData = await historyResponse.json();
        setHistory(historyData.items || []);
      }
    } catch (err) {
      console.error("Geçmiş alınamadı", err);
    }
  }
  useEffect(() => {
    const storedToken = window.localStorage.getItem("truthlens_token");
    if (storedToken) {
      setToken(storedToken);
      void fetchCurrentUser(storedToken);
    }
  }, []);

  async function fetchModerationHistory(activeToken: string) {
    setModerationHistoryLoading(true);
    setModerationHistoryError("");

    try {
      const response = await fetch(`${API_BASE_URL}/moderation/history?limit=50`, {
        headers: { Authorization: `Bearer ${activeToken}` },
      });
      const data = await response.json();

      if (!response.ok) {
        throw new Error(data?.detail || "Moderasyon geçmişi alınamadı.");
      }

      setModerationHistory(Array.isArray(data?.items) ? data.items : []);
    } catch (err) {
      console.error("Moderasyon geçmişi alınamadı", err);
      setModerationHistoryError(
        err instanceof Error ? err.message : "Moderasyon geçmişi alınamadı."
      );
    } finally {
      setModerationHistoryLoading(false);
    }
  }


  async function analyzeContent() {
    const value = content.trim();

    if (!value) {
      setError("Lütfen analiz edilecek bir içerik gir.");
      return;
    }

    await sendAnalysis("/analyze", {
      content: value,
    });
  }

  async function analyzeUrl() {
    const value = url.trim();

    if (!value) {
      setError("Lütfen analiz edilecek bir bağlantı gir.");
      return;
    }

    try {
      new URL(value);
    } catch {
      setError(
        "Geçerli bir bağlantı gir. Örneğin: https://nsosyal.com/post/..."
      );
      return;
    }

    await sendAnalysis("/analyze-url", {
      url: value,
    });
  }

  async function handleAuthSubmit() {
    const payload = {
      name,
      email,
      password,
    };

    const endpoint = authMode === "register" ? "/register" : "/login";

    try {
      const response = await fetch(`${API_BASE_URL}${endpoint}`, {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
        },
        body: JSON.stringify(authMode === "register" ? payload : { email, password }),
      });

      const data = await response.json();

      if (!response.ok) {
        throw new Error(data?.detail || "Kimlik doğrulama başarısız.");
      }

      if (data?.token) {
        const nextToken = data.token;
        setToken(nextToken);
        setUser(data.user);
        window.localStorage.setItem("truthlens_token", nextToken);
        await fetchHistory(nextToken);
        await fetchModerationHistory(nextToken);
      }

      setError("");
    } catch (err) {
      setError(err instanceof Error ? err.message : "Giriş işlemi başarısız.");
    }
  }

  async function openDemoFeed() {
    setFeedOpen(true);
    setError("");
    setFeedLimit(5);

    try {
      const liveResponse = await fetch(`${API_BASE_URL}/bluesky-feed?limit=5`);
      const liveData = await liveResponse.json();

      if (!liveResponse.ok) {
        throw new Error(liveData?.detail || "Canlı akış yüklenemedi.");
      }

      const posts = Array.isArray(liveData?.posts) ? liveData.posts : [];
      setDemoFeed(posts);
      setDemoSummary(liveData?.summary || null);
      setFeedSource(liveData?.provider === "bluesky" ? "live" : "demo");

      if (posts.length === 0) {
        const fallbackResponse = await fetch(`${API_BASE_URL}/demo-feed`);
        const fallbackData = await fallbackResponse.json();

        if (fallbackResponse.ok) {
          setDemoFeed(fallbackData.posts || []);
          setDemoSummary(fallbackData.summary || null);
          setFeedSource("demo");
        }
      }
    } catch (err) {
      console.error(err);

      try {
        const fallbackResponse = await fetch(`${API_BASE_URL}/demo-feed`);
        const fallbackData = await fallbackResponse.json();

        if (fallbackResponse.ok) {
          setDemoFeed(fallbackData.posts || []);
          setDemoSummary(fallbackData.summary || null);
          setFeedSource("demo");
          return;
        }
      } catch {
        // no-op, main error below handles it
      }

      setError(err instanceof Error ? err.message : "Sosyal akış yüklenemedi.");
    }
  }

  async function loadMoreFeed() {
    const nextLimit = Math.min(20, feedLimit + 5);
    if (nextLimit === feedLimit) {
      return;
    }

    setFeedRefreshing(true);
    setError("");

    try {
      const liveResponse = await fetch(`${API_BASE_URL}/bluesky-feed?limit=${nextLimit}`);
      const liveData = await liveResponse.json();

      if (!liveResponse.ok) {
        throw new Error(liveData?.detail || "Daha fazla gönderi yüklenemedi.");
      }

      const posts = Array.isArray(liveData?.posts) ? liveData.posts : [];
      setDemoFeed(posts);
      setDemoSummary(liveData?.summary || null);
      setFeedSource(liveData?.provider === "bluesky" ? "live" : "demo");
      setFeedLimit(nextLimit);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Daha fazla gönderi yüklenemedi.");
    } finally {
      setFeedRefreshing(false);
    }
  }

  async function checkNsosyalPost() {
    const draft = nsosyalDraft.trim();
    if (!draft) {
      setError("NSosyal gönderisi için bir metin yaz.");
      return;
    }

    setNsosyalChecking(true);
    setNsosyalCheck(null);
    setNsosyalPublished(false);
    setError("");
    try {
      const response = await fetch(`${API_BASE_URL}/nsosyal/moderation-check`, {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
          ...(token ? { Authorization: `Bearer ${token}` } : {}),
        },
        body: JSON.stringify({ content: draft }),
      });
      const data = await response.json();
      if (!response.ok) throw new Error(data?.detail || "NSosyal moderasyon ön kontrolü başarısız.");
      setNsosyalCheck(data as NsosyalModerationCheck);
    } catch (err) {
      setError(err instanceof Error ? err.message : "NSosyal moderasyon ön kontrolü başarısız.");
    } finally {
      setNsosyalChecking(false);
    }
  }

  async function publishToBluesky() {
    if (!nsosyalCheck?.publish.allowed) return;
    try {
      const response = await fetch(`${API_BASE_URL}/social/create-post`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ content: nsosyalCheck.content }),
      });
      const data = await response.json();
      if (!response.ok) throw new Error(data?.detail || "Bluesky gönderisi oluşturulamadı.");
      setSocialActionStatus("Gönderi Bluesky’ye başarıyla gönderildi.");
      setNsosyalPublished(true);
    } catch (err) {
      setSocialActionStatus(err instanceof Error ? err.message : "Bluesky gönderisi oluşturulamadı.");
    }
  }

  function publishNsosyalDemoPost() {
    if (!nsosyalCheck?.publish.allowed) return;
    const check = nsosyalCheck;
    const demoPost: FeedPost = {
      id: `nsosyal-${Date.now()}`,
      author: user?.name || "truthlens_demo",
      handle: user ? `@${user.email.split("@")[0]}` : "@truthlens_demo",
      avatar: "",
      content: check.content,
      tag: "NSosyal Demo",
      analysis_status: "ready",
      truthlens_score: Math.max(0, 100 - check.toxicity.hate_speech),
      misinformation_risk: 0,
      polarization: check.toxicity.bullying,
      hate_speech: check.toxicity.hate_speech,
      sentiment: check.toxicity.context_note,
      reason: check.moderation.reason,
      risk_level: check.toxicity.risk_level,
      verification: check.verification,
      verified_by_truthlens: Boolean(check.verification.verified),
      ai: {
        summary: "NSosyal gönderisi TruthLens moderasyon adapterinden geçti.",
        hate_speech: check.toxicity.hate_speech,
        polarization: check.toxicity.bullying,
        reasoning: check.moderation.reason,
      },
    };
    setDemoFeed((current) => [demoPost, ...current]);
    setFeedSource("demo");
    setNsosyalPublished(true);
  }

  async function toggleSocialLike(post: FeedPost) {
    const alreadyLiked = likedPostIds.has(post.id);
    setSocialActionStatus("");
    if (!alreadyLiked && post.cid && post.id.startsWith("at://")) {
      try {
        const response = await fetch(`${API_BASE_URL}/social/like`, {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ uri: post.id, cid: post.cid }),
        });
        const data = await response.json();
        if (!response.ok) throw new Error(data?.detail || "Beğeni gönderilemedi.");
        setSocialActionStatus("Beğeni Bluesky’ye gönderildi.");
      } catch (err) {
        setSocialActionStatus(err instanceof Error ? err.message : "Beğeni gönderilemedi.");
        return;
      }
    }
    setLikedPostIds((current) => {
      const next = new Set(current);
      if (alreadyLiked) next.delete(post.id); else next.add(post.id);
      return next;
    });
  }

  async function repostSocialPost(post: FeedPost) {
    if (!post.cid || !post.id.startsWith("at://")) {
      setSocialActionStatus("Bu demo gönderisi yerel akışta yeniden paylaşıldı.");
      setDemoFeed((current) => [post, ...current]);
      return;
    }
    try {
      const response = await fetch(`${API_BASE_URL}/social/repost`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ uri: post.id, cid: post.cid }),
      });
      const data = await response.json();
      if (!response.ok) throw new Error(data?.detail || "Yeniden paylaşım gönderilemedi.");
      setSocialActionStatus("Yeniden paylaşım Bluesky’ye gönderildi.");
    } catch (err) {
      setSocialActionStatus(err instanceof Error ? err.message : "Yeniden paylaşım gönderilemedi.");
    }
  }

  function startSocialReply(post: FeedPost) {
    setSocialView("home");
    setNsosyalDraft(`@${post.handle.replace(/^@/, "")} `);
    setSocialActionStatus("Yanıt taslağı hazırlandı; moderasyondan geçirerek yayınlayabilirsin.");
  }

  async function sendAnalysis(
    endpoint: string,
    body: Record<string, string>
  ): Promise<AnalysisResult | null> {
    let analysisData: AnalysisResult | null = null;
    setLoading(true);
    setError("");
    setResult(null);
    setAppealReason("");
    setAppealSent(false);
    setUrlModerationOverride(false);

    try {
      const response = await fetch(
        `${API_BASE_URL}${endpoint}`,
        {
          method: "POST",
          headers: {
            "Content-Type": "application/json",
            ...(token ? { Authorization: `Bearer ${token}` } : {}),
          },
          body: JSON.stringify(body),
        }
      );

      const data = await response.json();
      analysisData = data as AnalysisResult;

      if (!response.ok) {
        throw new Error(
          data?.detail || "Analiz isteği başarısız oldu."
        );
      }

      const nestedInsult = data?.toxicity_models?.insult?.raw?.INSULT;
      const nestedBullying = data?.toxicity_models?.bullying?.score;
      const mappedData: AnalysisResult = {
        ...data,
        toxicity: data?.toxicity
          ? {
              ...data.toxicity,
              insult: typeof nestedInsult === "number" ? nestedInsult : data.toxicity.insult,
              bullying: typeof nestedBullying === "number" ? nestedBullying : data.toxicity.bullying,
            }
          : data.toxicity,
      };
      console.info("[TruthLens] /analyze toxicity mapping", {
        general: { label: data?.toxicity_label, confidence: data?.toxicity_confidence, engine: data?.toxicity_engine },
        insult: data?.toxicity_models?.insult?.raw,
        bullying: data?.toxicity_models?.bullying?.raw,
        hate_speech: data?.toxicity_models?.hate_speech?.raw,
        mapped_ui: mappedData.toxicity,
      });
      setResult(mappedData);

      if (token) {
        const historyResponse = await fetch(`${API_BASE_URL}/history`, {
          headers: {
            Authorization: `Bearer ${token}`,
          },
        });

        if (historyResponse.ok) {
          const historyData = await historyResponse.json();
          setHistory(historyData.items || []);
        }
      }
    } catch (err) {
      console.error(err);

      if (err instanceof Error) {
        const message = err.message;
        if (message.includes("Gönderinin içeriğine erişilemedi") || message.includes("okunabilir gönderi içeriği")) {
          setError(
            "Bu sosyal medya gönderisinin metnine erişilemedi. Hesap gizli olabilir veya platform dış erişimi engelliyor olabilir. Gönderi metnini buraya yapıştırabilir ya da doğrudan görsel URL’sini Görsel Analizi alanında deneyebilirsin."
          );
        } else {
          setError(message);
        }
      } else {
        setError(
          "Analiz sırasında bir hata oluştu. Backend'in çalıştığından emin ol."
        );
      }
      return null;
    } finally {
      setLoading(false);
    }

    return analysisData;
  }

  async function submitAppeal() {
    if (!result?.content_hash || !result.moderation?.appeal_eligible || !appealReason.trim()) return;
    setAppealSending(true);
    try {
      const response = await fetch(`${API_BASE_URL}/moderation/appeal`, {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
          ...(token ? { Authorization: `Bearer ${token}` } : {}),
        },
        body: JSON.stringify({ content_hash: result.content_hash, appeal_reason: appealReason.trim() }),
      });
      const data = await response.json();
      if (!response.ok) throw new Error(data?.detail || "İtiraz gönderilemedi.");
      setAppealSent(true);
      setAppealReason("");
      if (token) await fetchModerationHistory(token);
    } catch (err) {
      setError(err instanceof Error ? err.message : "İtiraz gönderilemedi.");
    } finally {
      setAppealSending(false);
    }
  }

  function handleAnalyze() {
    if (mode === "text") {
      analyzeContent();
    } else if (mode === "url") {
      analyzeUrl();
    }
  }

  function switchMode(newMode: InputMode) {
    setMode(newMode);
    setError("");
    setResult(null);
    setSourceChainOpen(false);
    setUrlModerationOverride(false);
  }

  return (
    <main className="min-h-screen bg-slate-950 px-4 py-12 text-white">
      <div className="mx-auto max-w-5xl">

        {/* AUTH BAR */}
        <section className="mb-8 rounded-2xl border border-slate-800 bg-slate-900 p-5">
          <div className="flex flex-wrap items-center justify-between gap-4">
            <div>
              <div className="text-xs font-semibold uppercase tracking-[0.2em] text-slate-500">
                TruthLens Oturumu
              </div>
              <div className="mt-2 text-sm text-slate-300">
                {user ? `Merhaba, ${user.name}` : "Misafir kullanıcı"}
              </div>
            </div>

            <div className="flex items-center gap-3">
              {user ? (
                <button
                  onClick={() => {
                    setUser(null);
                    setToken(null);
                    setHistory([]);
                    setModerationHistory([]);
                    setModerationHistoryError("");
                    window.localStorage.removeItem("truthlens_token");
                  }}
                  className="rounded-xl border border-slate-700 px-4 py-2 text-sm font-semibold text-slate-300 hover:bg-slate-800"
                >
                  Çıkış
                </button>
              ) : (
                <div className="flex gap-2">
                  <button
                    onClick={() => setAuthMode("login")}
                    className={`rounded-xl px-4 py-2 text-sm font-semibold ${authMode === "login" ? "bg-blue-600 text-white" : "border border-slate-700 text-slate-300"}`}
                  >
                    Giriş
                  </button>
                  <button
                    onClick={() => setAuthMode("register")}
                    className={`rounded-xl px-4 py-2 text-sm font-semibold ${authMode === "register" ? "bg-blue-600 text-white" : "border border-slate-700 text-slate-300"}`}
                  >
                    Kayıt
                  </button>
                </div>
              )}
            </div>
          </div>

          {!user && (
            <div className="mt-5 grid grid-cols-1 gap-3 md:grid-cols-4">
              {authMode === "register" && (
                <input
                  value={name}
                  onChange={(e) => setName(e.target.value)}
                  className="rounded-xl border border-slate-700 bg-slate-950 px-4 py-3 text-white outline-none placeholder:text-slate-600"
                  placeholder="Ad soyad"
                />
              )}

              <input
                value={email}
                onChange={(e) => setEmail(e.target.value)}
                className="rounded-xl border border-slate-700 bg-slate-950 px-4 py-3 text-white outline-none placeholder:text-slate-600"
                placeholder="e-posta"
              />

              <input
                value={password}
                onChange={(e) => setPassword(e.target.value)}
                type="password"
                className="rounded-xl border border-slate-700 bg-slate-950 px-4 py-3 text-white outline-none placeholder:text-slate-600"
                placeholder="şifre"
              />

              <button
                onClick={handleAuthSubmit}
                className="rounded-xl bg-blue-600 px-5 py-3 font-semibold hover:bg-blue-500"
              >
                {authMode === "register" ? "Kayıt ol" : "Giriş yap"}
              </button>
            </div>
          )}
        </section>

        {/* HEADER */}
        <div className="mb-12 text-center">

          <div className="mb-5 inline-flex items-center gap-2 rounded-full border border-slate-700 bg-slate-900 px-4 py-2 text-sm text-slate-300">
            <span className="h-2 w-2 rounded-full bg-green-400" />
            TruthLens AI
          </div>

          <h1 className="text-4xl font-bold tracking-tight md:text-6xl">
            Gerçeği,
            <span className="text-blue-400">
              {" "}yapay zekâ ile{" "}
            </span>
            analiz et.
          </h1>

          <p className="mx-auto mt-5 max-w-2xl text-slate-400">
            Sosyal medya gönderilerini, haberleri ve iddiaları
            analiz et. Güvenilirlik, manipülasyon, clickbait ve
            içerikteki önemli bağlamı incele.
          </p>

          <div className="mt-8 flex justify-center">
            <button
              onClick={openDemoFeed}
              className="rounded-xl bg-gradient-to-r from-blue-600 to-cyan-500 px-6 py-3 font-semibold text-white shadow-lg shadow-blue-500/20 transition hover:brightness-110"
            >
              🔍 Sosyal Medyada Dene
            </button>
          </div>

        </div>

        {/* INPUT CARD */}
        <section className="rounded-2xl border border-slate-800 bg-slate-900 p-6 shadow-xl">

          {/* MODE TABS */}
          <div className="mb-6 grid grid-cols-2 gap-2 rounded-xl bg-slate-950 p-1">

            <button
              onClick={() => switchMode("text")}
              className={`rounded-lg px-4 py-3 text-sm font-semibold transition ${
                mode === "text"
                  ? "bg-blue-600 text-white"
                  : "text-slate-400 hover:bg-slate-900 hover:text-white"
              }`}
            >
              📝 Metin Analizi
            </button>

            <button
              onClick={() => switchMode("url")}
              className={`rounded-lg px-4 py-3 text-sm font-semibold transition ${
                mode === "url"
                  ? "bg-blue-600 text-white"
                  : "text-slate-400 hover:bg-slate-900 hover:text-white"
              }`}
            >
              🔗 Link Analizi
            </button>

          </div>

          {/* TEXT MODE */}
          {mode === "text" && (
            <>
              <label className="mb-3 block text-sm font-medium text-slate-300">
                Analiz etmek istediğin içeriği yapıştır
              </label>

              <textarea
                value={content}
                onChange={(e) => setContent(e.target.value)}
                placeholder="Örneğin: NASA, Ay'ın Dünya'ya yaklaşmaya başladığını ve 2030 yılında Dünya'ya çarpacağını açıkladı."
                maxLength={10000}
                className="min-h-48 w-full resize-y rounded-xl border border-slate-700 bg-slate-950 p-4 text-white outline-none placeholder:text-slate-600 focus:border-blue-500"
              />

              <div className="mt-4 flex items-center justify-between gap-4">

                <span className="text-sm text-slate-500">
                  {content.length} / 10000 karakter
                </span>

                <button
                  onClick={handleAnalyze}
                  disabled={loading}
                  className="rounded-xl bg-blue-600 px-6 py-3 font-semibold transition hover:bg-blue-500 disabled:cursor-not-allowed disabled:opacity-50"
                >
                  {loading
                    ? "Analiz ediliyor..."
                    : "Analiz Et"}
                </button>

              </div>
            </>
          )}

          {/* URL MODE */}
          {mode === "url" && (
            <>
              <label className="mb-3 block text-sm font-medium text-slate-300">
                Analiz etmek istediğin gönderinin bağlantısını yapıştır
              </label>

              <div className="relative">

                <input
                  type="url"
                  value={url}
                  onChange={(e) => setUrl(e.target.value)}
                  onKeyDown={(e) => {
                    if (e.key === "Enter") {
                      handleAnalyze();
                    }
                  }}
                  placeholder="https://nsosyal.com/post/..."
                  className="w-full rounded-xl border border-slate-700 bg-slate-950 px-4 py-4 pr-14 text-white outline-none placeholder:text-slate-600 focus:border-blue-500"
                />

                <div className="pointer-events-none absolute right-4 top-1/2 -translate-y-1/2 text-xl">
                  🔗
                </div>

              </div>

              <div className="mt-3 rounded-xl border border-blue-900/50 bg-blue-950/20 p-4 text-sm text-slate-400">

                <p>
                  <span className="font-semibold text-blue-400">
                    Nasıl çalışır?
                  </span>
                </p>

                <p className="mt-1">
                  Gönderinin bağlantısını bırak. TruthLens AI,
                  sayfadaki içeriği inceleyerek iddiaları,
                  bağlamı ve güvenilir kaynakları araştırır.
                </p>

              </div>

              <div className="mt-4 flex justify-end">

                <button
                  onClick={handleAnalyze}
                  disabled={loading}
                  className="rounded-xl bg-blue-600 px-6 py-3 font-semibold transition hover:bg-blue-500 disabled:cursor-not-allowed disabled:opacity-50"
                >
                  {loading
                    ? "Gönderi inceleniyor..."
                    : "Linki Analiz Et"}
                </button>

              </div>
            </>
          )}

          {/* ERROR */}
          {error && (
            <div className="mt-4 rounded-xl border border-red-900 bg-red-950/40 p-4 text-red-300">
              {error}
            </div>
          )}

        </section>

        {/* SOCIAL TRUST LAYER */}
        <section className="mt-8 grid grid-cols-1 gap-4 md:grid-cols-2 lg:grid-cols-5">

          <div className="rounded-2xl border border-slate-800 bg-slate-900 p-5">
            <div className="mb-3 flex items-center gap-2">
              <span className="text-lg"></span>
              <span className="text-sm font-semibold text-slate-300">Context AI</span>
            </div>
            <p className="text-sm leading-6 text-slate-500">
              Zaman, bağlam ve olay uyumsuzluğunu çözümler.
            </p>
          </div>

          <div className="rounded-2xl border border-slate-800 bg-slate-900 p-5">
            <div className="mb-3 flex items-center gap-2">
              <span className="text-lg"></span>
              <span className="text-sm font-semibold text-slate-300">Yankı Odası</span>
            </div>
            <p className="text-sm leading-6 text-slate-500">
              Kullanıcı profili ve okuma geçmişini tek görüşlü akış riskiyle eşleştirir.
            </p>
          </div>

          <div className="rounded-2xl border border-slate-800 bg-slate-900 p-5">
            <div className="mb-3 flex items-center gap-2">
              <span className="text-lg"></span>
              <span className="text-sm font-semibold text-slate-300">Kutuplaştırma Ölçer</span>
            </div>
            <p className="text-sm leading-6 text-slate-500">
              İçerik dilindeki kutuplaştırma ve duygusal etkilenme ihtimalini ölçer.
            </p>
          </div>

          <div className="rounded-2xl border border-slate-800 bg-slate-900 p-5">
            <div className="mb-3 flex items-center gap-2">
              <span className="text-lg"></span>
              <span className="text-sm font-semibold text-slate-300">AI Yeniden Yazım</span>
            </div>
            <p className="text-sm leading-6 text-slate-500">
              Paylaşım öncesi tarafsızlaştırılmış metin önerir.
            </p>
          </div>

          <div className="rounded-2xl border border-slate-800 bg-slate-900 p-5">
            <div className="mb-3 flex items-center gap-2">
              <span className="text-lg"></span>
              <span className="text-sm font-semibold text-slate-300">İnsan Denetimi</span>
            </div>
            <p className="text-sm leading-6 text-slate-500">
              Riskli içeriklerde otomatik silme yerine insan incelemesini öne çıkarır.
            </p>
          </div>

        </section>

        {/* HISTORY / PROFILE PANEL */}
        {user && (
          <section className="mt-8 rounded-2xl border border-slate-800 bg-slate-900 p-6">
            <div className="mb-4 flex items-center justify-between">
              <div>
                <div className="text-xs font-bold uppercase tracking-[0.28em] text-slate-500">
                  Kullanıcı Belleği
                </div>
                <h2 className="mt-2 text-2xl font-bold text-white">
                  Son analiz geçmişi
                </h2>
              </div>
              <span className="rounded-full border border-blue-500/40 bg-blue-500/10 px-4 py-2 text-xs font-bold uppercase text-blue-300">
                {user.email}
              </span>
            </div>

            <div className="grid grid-cols-1 gap-3">
              {history.length === 0 && (
                <div className="rounded-xl border border-slate-800 bg-slate-950 p-4 text-sm text-slate-500">
                  Henüz kayıtlı analiz bulunmuyor.
                </div>
              )}

              {history.map((item, index) => (
                <div key={`${item.content_hash}-${index}`} className="rounded-xl border border-slate-800 bg-slate-950 p-4">
                  <div className="mb-2 flex items-center justify-between">
                    <div className="text-sm font-semibold text-slate-300">
                      {item.source_url || "Metin analizi"}
                    </div>
                    <div className="text-xs text-slate-500">
                      {new Date(item.created_at).toLocaleString()}
                    </div>
                  </div>
                  <div className="text-sm text-slate-400">
                    {item.result?.result || "Analiz sonucu mevcut"}
                  </div>
                </div>
              ))}
            </div>
          </section>
        )}

        {/* MODERATION / APPEAL HISTORY */}
        {user && (
          <section className="mt-8 rounded-2xl border border-slate-800 bg-slate-900 p-6">
            <div className="mb-4 flex flex-col gap-3 md:flex-row md:items-center md:justify-between">
              <div>
                <div className="text-xs font-bold uppercase tracking-[0.28em] text-slate-500">
                  Şeffaflık ve itiraz
                </div>
                <h2 className="mt-2 text-2xl font-bold text-white">
                  Moderasyon ve itiraz geçmişi
                </h2>
                <p className="mt-1 text-sm text-slate-500">
                  Bu hesap için verilen moderasyon kararları ve gönderilen itirazlar burada tutulur.
                </p>
              </div>
              <button
                onClick={() => token && fetchModerationHistory(token)}
                disabled={moderationHistoryLoading}
                className="rounded-xl border border-blue-500/40 bg-blue-500/10 px-4 py-2 text-sm font-semibold text-blue-200 hover:bg-blue-500/20 disabled:cursor-not-allowed disabled:opacity-50"
              >
                {moderationHistoryLoading ? "Yükleniyor..." : "Yenile"}
              </button>
            </div>

            {moderationHistoryError && (
              <div className="mb-4 rounded-xl border border-red-900 bg-red-950/40 p-4 text-sm text-red-300">
                {moderationHistoryError}
              </div>
            )}

            {moderationHistory.length === 0 && !moderationHistoryLoading ? (
              <div className="rounded-xl border border-slate-800 bg-slate-950 p-4 text-sm text-slate-500">
                Henüz bu hesap için moderasyon kaydı bulunmuyor.
              </div>
            ) : (
              <div className="space-y-3">
                {moderationHistory.map((item, index) => {
                  const labels: Record<string, string> = {
                    izin_ver: "İçeriğe izin verildi",
                    etiketle: "Uyarı etiketi",
                    gizle_ve_incele: "Gizle ve incele",
                    kaldirma_oner: "Kaldırma önerisi",
                  };

                  const appealLabel =
                    item.appeal_status === "beklemede"
                      ? "İtiraz beklemede"
                      : item.appeal_status
                        ? `İtiraz: ${item.appeal_status}`
                        : "İtiraz gönderilmedi";

                  return (
                    <div
                      key={`${item.content_hash}-${index}`}
                      className="rounded-xl border border-slate-800 bg-slate-950 p-4"
                    >
                      <div className="flex flex-col gap-3 md:flex-row md:items-start md:justify-between">
                        <div>
                          <div className="font-semibold text-white">
                            {labels[item.action] || item.action}
                          </div>
                          <div className="mt-1 text-xs text-slate-500">
                            {new Date(item.created_at).toLocaleString("tr-TR")}
                          </div>
                        </div>
                        <div className="rounded-full border border-blue-500/30 bg-blue-500/10 px-3 py-1 text-xs font-bold text-blue-300">
                          Risk: {item.aggregate_risk}%
                        </div>
                      </div>

                      <p className="mt-3 text-sm leading-6 text-slate-400">
                        {item.reason}
                      </p>

                      <div className="mt-3">
                        <span className="rounded-full border border-slate-700 bg-slate-900 px-3 py-1.5 text-xs text-slate-400">
                          {appealLabel}
                        </span>
                      </div>

                      {item.appeal_reason && (
                        <div className="mt-3 rounded-xl border border-amber-500/20 bg-amber-500/5 p-3">
                          <div className="text-xs font-semibold uppercase tracking-[0.18em] text-amber-400">
                            Gönderdiğin itiraz
                          </div>
                          <p className="mt-1 text-sm leading-6 text-slate-300">
                            {item.appeal_reason}
                          </p>
                          {item.appeal_created_at && (
                            <div className="mt-2 text-xs text-slate-600">
                              {new Date(item.appeal_created_at).toLocaleString("tr-TR")}
                            </div>
                          )}
                        </div>
                      )}
                    </div>
                  );
                })}
              </div>
            )}
          </section>
        )}

        {/* ADMIN / LIVE DASHBOARD PANEL */}
        <section className="mt-8 rounded-2xl border border-slate-800 bg-slate-900 p-6">

          <div className="mb-4 flex items-center justify-between">
            <div>
              <div className="text-xs font-bold uppercase tracking-[0.28em] text-slate-500">
                Sosyal Güven Metrikleri
              </div>
              <h2 className="mt-2 text-2xl font-bold text-white">
                TruthLens Sosyal Güven Konsolu
              </h2>
            </div>
            <span className="rounded-full border border-emerald-500/40 bg-emerald-500/10 px-4 py-2 text-xs font-bold uppercase text-emerald-300">
              {user ? "Çevrimiçi" : "Misafir"}
            </span>
          </div>

          <div className="grid grid-cols-1 gap-4 md:grid-cols-4">

            <div className="rounded-xl border border-slate-800 bg-slate-950 p-4">
              <div className="text-xs font-semibold uppercase tracking-[0.2em] text-slate-500">
                Risk Eğilimi
              </div>
              <div className="mt-2 text-3xl font-bold text-amber-300">
                {user ? `+${riskTrend}%` : "--"}
              </div>
              <div className="mt-1 text-xs text-slate-600">
                {user ? "Bu kullanıcı için anlık risk" : "Oturum bekleniyor"}
              </div>
            </div>

            <div className="rounded-xl border border-slate-800 bg-slate-950 p-4">
              <div className="text-xs font-semibold uppercase tracking-[0.2em] text-slate-500">
                İnsan Denetimi
              </div>
              <div className="mt-2 text-3xl font-bold text-amber-300">
                {result?.moderation?.requires_human_review ? "Gerekli" : result ? "Gerekmiyor" : "--"}
              </div>
              <div className="mt-1 text-xs text-slate-600">
                {result ? "Son analizdeki moderasyon kararı" : "Analiz bekleniyor"}
              </div>
            </div>

            <div className="rounded-xl border border-slate-800 bg-slate-950 p-4">
              <div className="text-xs font-semibold uppercase tracking-[0.2em] text-slate-500">
                Son Analiz Güven Skoru
              </div>
              <div className="mt-2 text-3xl font-bold text-emerald-300">
                {result ? `${trustQuality}%` : "--"}
              </div>
              <div className="mt-1 text-xs text-slate-600">
                {result ? "Son analizdeki gerçeklik skoru" : "Analiz bekleniyor"}
              </div>
            </div>

            <div className="rounded-xl border border-slate-800 bg-slate-950 p-4">
              <div className="text-xs font-semibold uppercase tracking-[0.2em] text-slate-500">
                Kayıtlı Analiz
              </div>
              <div className="mt-2 text-3xl font-bold text-blue-300">
                {user ? history.length : "--"}
              </div>
              <div className="mt-1 text-xs text-slate-600">
                {user ? "Bu hesapta saklanan analiz" : "Oturum bekleniyor"}
              </div>
            </div>

          </div>

        </section>

        {/* ECHO CHAMBER PROFILE PANEL */}
        <section className="mt-8 rounded-2xl border border-slate-800 bg-slate-900 p-6">

          <div className="mb-4 flex items-center justify-between">
            <div>
              <div className="text-xs font-bold uppercase tracking-[0.28em] text-slate-500">
                Kullanıcı İstihbaratı
              </div>
              <h2 className="mt-2 text-2xl font-bold text-white">
                Yankı Odası Algılayıcısı
              </h2>
            </div>
            <span className="rounded-full border border-blue-500/40 bg-blue-500/10 px-4 py-2 text-xs font-bold uppercase text-blue-300">
                {user ? "Risk: Orta" : "Misafir"}
            </span>
          </div>

          {user ? (
            <div className="grid grid-cols-1 gap-4 md:grid-cols-3">

              <div className="rounded-xl border border-slate-800 bg-slate-950 p-4">
                <div className="mb-2 text-xs font-semibold uppercase tracking-[0.2em] text-slate-500">
                  Profil
                </div>
                <div className="text-sm font-bold text-white">
                  {user.name || "TruthLens Kullanıcısı"}
                </div>
                <div className="mt-2 text-xs text-slate-500">
                  {history.length > 0
                    ? `${history.length} kayıtlı analiz bulundu.`
                    : "Henüz kişisel akış kaydı yok."}
                </div>
              </div>

              <div className="rounded-xl border border-slate-800 bg-slate-950 p-4">
                <div className="mb-2 text-xs font-semibold uppercase tracking-[0.2em] text-slate-500">
                  Okuma Geçmişi
                </div>
                <div className="text-sm text-slate-400">
                  {history.length > 0
                    ? `${history.length} içerik · ${Math.max(0, history.length - 1)} mevcut analiz akışı`
                    : "Kayıtlı içerik geçmişi yok"}
                </div>
              </div>

              <div className="rounded-xl border border-slate-800 bg-slate-950 p-4">
                <div className="mb-2 text-xs font-semibold uppercase tracking-[0.2em] text-slate-500">
                  Öneri
                </div>
                <div className="text-sm leading-6 text-slate-400">
                  {history.length > 0
                    ? "Geçmiş akışına göre farklı kaynaklardan bağlam kontrolü önerilir."
                    : "Farklı bakış açıları için oturum açıp analiz yapın."}
                </div>
              </div>

            </div>
          ) : (
            <div className="rounded-xl border border-slate-800 bg-slate-950 p-4 text-sm text-slate-500">
              Kayıtlı kullanıcı profili bulunmuyor. Oturum açınca echo chamber geçmişi ve profil akışı burada görünür.
            </div>
          )}

        </section>

        {/* LOADING */}
        {loading && (
          <div className="mt-8 rounded-2xl border border-slate-800 bg-slate-900 p-8 text-center">

            <div className="mx-auto mb-4 h-8 w-8 animate-spin rounded-full border-4 border-slate-700 border-t-blue-500" />

            <h2 className="font-semibold">
              {mode === "url"
                ? "Gönderi analiz ediliyor..."
                : "İçerik analiz ediliyor..."}
            </h2>

            <p className="mt-2 text-sm text-slate-500">
              İddialar, bağlam ve güvenilir kaynaklar araştırılıyor.
            </p>

          </div>
        )}

        {/* RESULT */}
        {result && !loading && (
          <section className={`relative mt-8 space-y-6 ${
            mode === "url" &&
            result.moderation &&
            (result.moderation.action === "gizle_ve_incele" || result.moderation.action === "kaldirma_oner") &&
            !urlModerationOverride
              ? "overflow-hidden"
              : ""
          }`}>

            {mode === "url" &&
              result.moderation &&
              (result.moderation.action === "gizle_ve_incele" || result.moderation.action === "kaldirma_oner") &&
              !urlModerationOverride && (
                <div className="absolute inset-0 z-20 flex min-h-[520px] items-start justify-center bg-slate-950/90 p-6 pt-10 backdrop-blur-sm">
                  <div className="sticky top-8 w-full max-w-2xl rounded-2xl border border-amber-500/30 bg-slate-900 p-7 text-center shadow-2xl">
                    <div className="mx-auto flex h-14 w-14 items-center justify-center rounded-full border border-amber-500/30 bg-amber-500/10 text-2xl">⚠️</div>
                    <div className="mt-4 text-xs font-bold uppercase tracking-[0.22em] text-amber-400">TruthLens içerik güvenliği</div>
                    <h2 className="mt-2 text-2xl font-bold text-white">Bu içerik geçici olarak gizlendi</h2>
                    <p className="mx-auto mt-3 max-w-xl text-sm leading-6 text-slate-400">
                      TruthLens, URL'den alınan gönderide inceleme gerektiren bir risk tespit etti. İçeriği görüntülemek için aşağıdaki seçeneği kullanabilirsin.
                    </p>
                    <div className="mt-5 rounded-xl border border-slate-800 bg-slate-950 p-4 text-left">
                      <div className="text-xs uppercase tracking-[0.18em] text-slate-500">Önerilen işlem</div>
                      <div className="mt-2 font-semibold text-white">{result.moderation.action_label}</div>
                      <div className="mt-2 text-sm leading-6 text-slate-400">{result.moderation.reason}</div>
                    </div>
                    <div className="mt-5 flex flex-col justify-center gap-3 sm:flex-row">
                      <button type="button" onClick={() => setUrlModerationOverride(true)} className="rounded-xl bg-blue-600 px-5 py-3 text-sm font-semibold text-white transition hover:bg-blue-500">Yine de görüntüle</button>
                      <button type="button" onClick={() => setResult(null)} className="rounded-xl border border-slate-700 bg-slate-950 px-5 py-3 text-sm font-semibold text-slate-300 transition hover:border-slate-500">İçeriği gizli tut</button>
                    </div>
                    {result.moderation.requires_human_review && (
                      <div className="mt-4 text-xs text-slate-500">İnsan incelemesi öneriliyor. Otomatik silme yapılmaz.</div>
                    )}
                  </div>
                </div>
              )}

            <div className={
              mode === "url" &&
              result.moderation &&
              (result.moderation.action === "gizle_ve_incele" || result.moderation.action === "kaldirma_oner") &&
              !urlModerationOverride
                ? "pointer-events-none select-none blur-sm"
                : ""
            }>

            {/* SCORE */}
            <div className="rounded-2xl border border-slate-800 bg-slate-900 p-8 text-center">

              <div className="flex flex-wrap items-center justify-center gap-3">
                <p className="text-sm uppercase tracking-widest text-slate-500">
                  Gerçeklik Skoru
                </p>
                {result.verification?.verified && (
                  <span
                    title={result.verification.label}
                    className="inline-flex items-center gap-1.5 rounded-full border border-emerald-400/40 bg-emerald-400/10 px-3 py-1.5 text-xs font-bold text-emerald-300"
                  >
                    <span aria-hidden="true">✓</span>
                    Kanıt kapsamı tamamlandı
                  </span>
                )}
              </div>

              <div className="mt-3 text-7xl font-bold text-blue-400">
                {result.score}
                <span className="text-3xl text-slate-500">
                  /100
                </span>
              </div>

              <p className="mt-4 text-lg font-medium">
                {result.result}
              </p>

              {result.verification && (
                <div className={`mx-auto mt-5 max-w-2xl rounded-xl border p-4 text-left ${
                  result.verification.verified
                    ? "border-emerald-500/30 bg-emerald-500/5"
                    : "border-slate-800 bg-slate-950/70"
                }`}>
                  <div className="text-xs font-bold uppercase tracking-[0.18em] text-slate-500">
                    TruthLens rozet açıklaması
                  </div>
                  <div className="mt-2 text-sm font-semibold text-slate-200">
                    {result.verification.verified
                      ? "Bu içerik TruthLens'in doğruluk, güncellik, toksik bağlam ve risk kontrollerinin tamamından geçti."
                      : "Bu içerik doğrulama rozetinin tüm koşullarını geçmedi."}
                  </div>
                  {result.verification.reasons && result.verification.reasons.length > 0 && (
                    <ul className="mt-3 space-y-1.5 text-xs leading-5 text-slate-400">
                      {result.verification.reasons.map((reason, index) => (
                        <li key={index}>• {reason}</li>
                      ))}
                    </ul>
                  )}
                </div>
              )}

            </div>

            {/* METRICS */}
            <div className="grid grid-cols-1 gap-4 md:grid-cols-3">

              <Metric
                title="Manipülasyon Riski"
                value={result.manipulation}
              />

              <Metric
                title="Clickbait Riski"
                value={result.clickbait}
              />

            </div>

            {/* STATUS ROW */}
            <div className="grid grid-cols-1 gap-4 md:grid-cols-3">

              <div className="rounded-2xl border border-slate-800 bg-slate-900 p-5">
                <div className="mb-2 text-xs font-semibold uppercase tracking-[0.2em] text-slate-500">
                  Geçerlilik
                </div>
                <span className="inline-flex rounded-full border border-emerald-500/40 bg-emerald-500/10 px-4 py-2 text-sm font-semibold text-emerald-300">
                  {result.validity}
                </span>
              </div>

              <div className="rounded-2xl border border-slate-800 bg-slate-900 p-5">
                <div className="mb-2 text-xs font-semibold uppercase tracking-[0.2em] text-slate-500">
                  Duygusal Ton
                </div>
                <span className="inline-flex rounded-full border border-violet-500/40 bg-violet-500/10 px-4 py-2 text-sm font-semibold text-violet-300">
                  {result.emotion}
                </span>
              </div>

              <div className="rounded-2xl border border-slate-800 bg-slate-900 p-5">
                <div className="mb-2 text-xs font-semibold uppercase tracking-[0.2em] text-slate-500">
                  Sonuç
                </div>
                <span className="inline-flex rounded-full border border-blue-500/40 bg-blue-500/10 px-4 py-2 text-sm font-semibold text-blue-300">
                  {result.result}
                </span>
              </div>

            </div>

            <Card title="Zaman ve geçerlilik analizi">
              <p className="leading-7 text-slate-300">
                {result.time_validity}
              </p>
            </Card>

            {result.toxicity && (
              <Card title="Bağlamsal toksisite analizi">
                <div className="mb-4 flex flex-wrap items-center gap-2">
                  <span className="rounded-full border border-cyan-500/30 bg-cyan-500/10 px-3 py-1.5 text-xs font-semibold text-cyan-200">
                    {result.toxicity_engine === "model" ? "Fine-tuned BERT + LoRA" : "Fallback (model unavailable)"}: {result.toxicity_label === "toxic" ? "toxic" : "notoxic"}
                  </span>
                  <span className="rounded-full border border-slate-700 bg-slate-900 px-3 py-1.5 text-xs text-slate-300">
                    Binary model confidence: %{((result.toxicity_confidence ?? 0) * 100).toFixed(2)}
                  </span>
                  <span className="text-xs text-slate-500">Kalibre edilmiş kesinlik değildir.</span>
                </div>
                <p className="mb-4 text-xs text-slate-500">General toxicity binary BERT+LoRA’dan gelir. Hakaret ve zorbaca davranış ayrı auxiliary modellerden; nefret dili ise mapping uydurulmadan raw LABEL olasılıklarıyla gösterilir.</p>
                <div className="grid grid-cols-1 gap-4 md:grid-cols-3">
                  <div className="rounded-xl border border-slate-800 bg-slate-950 p-4">
                    <div className="text-xs uppercase tracking-[0.2em] text-slate-500">Hakaret</div>
                    <div className="mt-2 text-2xl font-bold text-red-300">
                      {insultScoreText}
                    </div>
                    <div className="mt-2 text-xs text-slate-500">Kaynak: {insultModel?.engine ?? "fallback"}</div>
                  </div>
                  <div className="rounded-xl border border-slate-800 bg-slate-950 p-4">
                    <div className="text-xs uppercase tracking-[0.2em] text-slate-500">Zorbaca davranış</div>
                    <div className="mt-2 text-2xl font-bold text-orange-300">
                      {bullyingScoreText}
                    </div>
                    <div className="mt-2 text-xs text-slate-500">Kaynak: {bullyingModel?.engine ?? "fallback"}</div>
                  </div>
                  <div className="rounded-xl border border-slate-800 bg-slate-950 p-4">
                    <div className="text-xs uppercase tracking-[0.2em] text-slate-500">Nefret dili · raw</div>
                    <div className="mt-2 space-y-1 text-sm font-semibold text-amber-300">
                      {hateRawEntries.length > 0
                        ? hateRawEntries.map(([label, value]) => <div key={label}>{hateLabelDisplay[label] ?? label}: {Number(value).toFixed(2)}%</div>)
                        : <div>Model kullanılamadı</div>}
                    </div>
                    <div className="mt-2 text-xs text-slate-500">Kaynak: {hateModel?.engine ?? "fallback"}</div>
                    <div className="mt-1 text-[11px] leading-5 text-slate-600">Not: Bu adlar modelin sınıf etiketlerine karşılık gelen kullanıcı dostu açıklamalardır.</div>
                  </div>
                </div>

                <div className="mt-4 rounded-xl border border-slate-800 bg-slate-950 p-4 text-sm text-slate-300">
                  <div className="mb-2 text-xs uppercase tracking-[0.2em] text-slate-500">Hedef / bağlam</div>
                  <div className="font-semibold text-white">{result.toxicity.targeted_person_or_group}</div>
                  <div className="mt-2 text-xs uppercase tracking-[0.2em] text-slate-500">Risk seviyesi</div>
                  <div className="mt-1 inline-flex rounded-full border border-red-500/30 bg-red-500/10 px-3 py-1 text-xs font-bold text-red-300">
                    {result.toxicity.risk_level}
                  </div>
                  <p className="mt-3 leading-6 text-slate-400">{result.toxicity.context_note}</p>
                </div>
              </Card>
            )}

            {result.toxicity_models && (
              <Card title="Ayrı toxicity modelleri">
                <div className="grid grid-cols-1 gap-3 md:grid-cols-3">
                  <div className="rounded-xl border border-slate-800 bg-slate-950 p-3 text-xs text-slate-300"><div className="font-semibold text-white">Insult Model</div><div className="mt-1">Skor: {result.toxicity_models.insult?.available ? `%${(result.toxicity_models.insult?.score ?? 0).toFixed(2)}` : "Model kullanılamadı"}</div><div className="mt-1 text-slate-500">{result.toxicity_models.insult?.available ? (result.toxicity_models.insult?.engine ?? "unknown") : "fallback"}</div>{result.toxicity_models.insult?.error && <div className="mt-1 text-slate-600">{result.toxicity_models.insult.error}</div>}</div>
                  <div className="rounded-xl border border-slate-800 bg-slate-950 p-3 text-xs text-slate-300"><div className="font-semibold text-white">Bullying Model</div><div className="mt-1">Skor: {result.toxicity_models.bullying?.available ? `%${(result.toxicity_models.bullying?.score ?? 0).toFixed(2)}` : "Model kullanılamadı"}</div><div className="mt-1 text-slate-500">Nötr: %{(result.toxicity_models.bullying?.neutral ?? 0).toFixed(2)}</div><div className="mt-1 text-slate-500">Cinsiyetçi: %{(result.toxicity_models.bullying?.gender_bullying ?? 0).toFixed(2)}</div><div className="mt-1 text-slate-500">Irkçılık: %{(result.toxicity_models.bullying?.racist_bullying ?? 0).toFixed(2)}</div><div className="mt-1 text-slate-500">Kızdırma/Hakaret: %{(result.toxicity_models.bullying?.harassment ?? 0).toFixed(2)}</div><div className="mt-1 text-slate-500">{result.toxicity_models.bullying?.available ? (result.toxicity_models.bullying?.engine ?? "unknown") : "fallback"}</div>{result.toxicity_models.bullying?.error && <div className="mt-1 text-slate-600">{result.toxicity_models.bullying.error}</div>}</div>
                  <div className="rounded-xl border border-slate-800 bg-slate-950 p-3 text-xs text-slate-300"><div className="font-semibold text-white">Hate Speech Model</div>{result.toxicity_models.hate_speech?.available ? Object.entries(result.toxicity_models.hate_speech?.raw ?? {}).map(([label, value]) => <div key={label} className="mt-1 text-slate-500">{hateLabelDisplay[label] ?? label}: %{Number(value).toFixed(2)}</div>) : <div className="mt-1 text-slate-500">Model kullanılamadı</div>}<div className="mt-1 text-slate-500">{result.toxicity_models.hate_speech?.available ? (result.toxicity_models.hate_speech?.engine ?? "unknown") : "fallback"}</div><div className="mt-1 text-[11px] leading-5 text-slate-600">Not: Bu etiketler modelin sınıf açıklamalarıdır; ham `LABEL_*` isimleri kullanıcı dostu biçime çevrilmiştir.</div>{result.toxicity_models.hate_speech?.error && <div className="mt-1 text-slate-600">{result.toxicity_models.hate_speech.error}</div>}</div>
                </div>
              </Card>
            )}

            {result.moderation && (
              <Card title="Moderasyon kararı">
                <div className="rounded-xl border border-slate-800 bg-slate-950 p-5">
                  <div className="flex flex-col gap-4 md:flex-row md:items-center md:justify-between">
                    <div>
                      <div className="text-xs uppercase tracking-[0.2em] text-slate-500">Önerilen platform aksiyonu</div>
                      <div className="mt-2 text-2xl font-bold text-white">{result.moderation.action_label}</div>
                      <p className="mt-2 leading-6 text-slate-400">{result.moderation.reason}</p>
                    </div>
                    <div className="shrink-0 rounded-xl border border-blue-500/30 bg-blue-500/10 px-4 py-3 text-center">
                      <div className="text-xs uppercase tracking-[0.2em] text-slate-500">Toplam risk</div>
                      <div className="mt-1 text-3xl font-extrabold text-blue-300">{result.moderation.aggregate_risk}%</div>
                    </div>
                  </div>
                  <div className="mt-4 flex flex-wrap gap-2 text-xs">
                    <span className="rounded-full border border-slate-700 bg-slate-900 px-3 py-1.5 text-slate-300">{result.moderation.requires_human_review ? "İnsan incelemesi gerekli" : "Otomatik ön değerlendirme"}</span>
                    {result.moderation.appeal_eligible && <span className="rounded-full border border-amber-500/30 bg-amber-500/10 px-3 py-1.5 text-amber-300">İtiraza açık</span>}
                  </div>
                  {result.image_toxicity && (Math.max(result.image_toxicity.insult, result.image_toxicity.bullying, result.image_toxicity.hate_speech) > 0 || result.image_text) && (
                    <div className="mt-4 rounded-xl border border-orange-500/40 bg-orange-500/10 p-4 text-sm text-orange-100">
                      <div className="font-bold text-orange-200">Görsel kaynaklı moderasyon sinyali</div>
                      <p className="mt-2 leading-6">Görseldeki metin/güvenlik sinyali metin analizine eklenerek moderasyon kararına dahil edildi.</p>
                      {result.image_text && <p className="mt-2 rounded-lg border border-orange-500/20 bg-slate-950/40 p-2 text-xs text-orange-100">Görselde okunan metin: “{result.image_text}”</p>}
                      <div className="mt-3 grid grid-cols-3 gap-2 text-xs">
                        <span className="rounded-lg bg-slate-950/40 p-2">Hakaret: %{result.image_toxicity.insult}</span>
                        <span className="rounded-lg bg-slate-950/40 p-2">Zorbalık: %{result.image_toxicity.bullying}</span>
                        <span className="rounded-lg bg-slate-950/40 p-2">Nefret: %{result.image_toxicity.hate_speech}</span>
                      </div>
                      <p className="mt-2 text-xs text-orange-200">{result.image_toxicity.context_note}</p>
                    </div>
                  )}
                  {result.moderation.appeal_eligible && (
                    <div className="mt-5 border-t border-slate-800 pt-5">
                      <div className="text-sm font-semibold text-slate-200">Bu moderasyon kararına itiraz et</div>
                      <p className="mt-1 text-xs text-slate-500">Sistem otomatik silme yapmaz; itiraz insan incelemesi için kaydedilir.</p>
                      {appealSent ? (
                        <div className="mt-3 rounded-xl border border-emerald-500/30 bg-emerald-500/10 p-3 text-sm text-emerald-300">İtirazın kaydedildi ve inceleme sırasına alındı.</div>
                      ) : (
                        <div className="mt-3 flex flex-col gap-3 md:flex-row">
                          <input value={appealReason} onChange={(e) => setAppealReason(e.target.value)} placeholder="Neden yanlış olduğunu düşündüğünü yaz..." className="min-w-0 flex-1 rounded-xl border border-slate-700 bg-slate-900 px-4 py-3 text-sm text-white outline-none focus:border-blue-500" />
                          <button onClick={submitAppeal} disabled={appealSending || !appealReason.trim()} className="rounded-xl bg-blue-600 px-5 py-3 text-sm font-semibold text-white hover:bg-blue-500 disabled:cursor-not-allowed disabled:opacity-50">{appealSending ? "Gönderiliyor..." : "İtiraz Gönder"}</button>
                        </div>
                      )}
                    </div>
                  )}
                </div>
              </Card>
            )}

            {/* SOCIAL RISK CARDS */}
            <div className="grid grid-cols-1 gap-4 lg:grid-cols-2">

              <Card title="Polarizasyon riski">
                <div className="flex items-end justify-between">
                  <span className="text-4xl font-bold text-amber-300">
                    {result.polarization_risk}%
                  </span>
                  <span className="rounded-full border border-amber-500/40 bg-amber-500/10 px-3 py-1 text-xs font-semibold text-amber-300">
                    Kutuplaştırma
                  </span>
                </div>
              </Card>

              <Card title="Yankı Odası">
                <p className="leading-7 text-slate-300">
                  {result.echo_chamber}
                </p>
              </Card>

            </div>

            {/* EXPLANATION */}
            <Card title="Neden?">

              <p className="leading-7 text-slate-300">
                {result.explanation}
              </p>

            </Card>

            {/* SCORE BREAKDOWN */}
            <Card title="Puan kırılımı">

              <p className="leading-7 text-slate-300">
                {result.score_breakdown}
              </p>

            </Card>

            {/* SOCIAL RISK SUMMARY */}
            <Card title="Sosyal risk özeti">

              <p className="leading-7 text-slate-300">
                {result.social_risk_summary}
              </p>

            </Card>

            {/* AI REWRITE */}
            <Card title="AI paylaşım önerisi">

              <div className="rounded-xl border border-emerald-500/30 bg-emerald-500/10 p-4 text-slate-200">
                {result.ai_rewrite}
              </div>

            </Card>

            <Card title="Görsel Analizi">
              <div className="space-y-3">
                <div className="text-sm text-slate-400">
                  AI Görsel İhtimali
                </div>
                <div className="text-3xl font-bold text-cyan-300">
                  {result?.image_analysis_available ? `${result.image_ai_probability ?? 0}/100` : "Kullanılamadı"}
                </div>
                <p className="leading-7 text-slate-300">
                  {result?.image_moderation_note || result?.image_analysis_reasoning || "Sightengine/vision görsel analizi bu içerik için kullanılamadı; bu durum görselin AI olmadığı anlamına gelmez."}
                </p>
                {result?.image_text && (
                  <div className="mt-3 rounded-lg border border-blue-500/20 bg-slate-950/40 p-3 text-sm text-slate-200">
                    <div className="text-xs text-blue-400 mb-1">Görselde okunan metin:</div>
                    <div>"{result.image_text}"</div>
                  </div>
                )}
              </div>
            </Card>

            {result.pipeline_status && (
              <Card title="AI pipeline durumu">
                <div className="grid grid-cols-1 gap-3 md:grid-cols-4">
                  <div className="rounded-xl border border-slate-800 bg-slate-950 p-4">
                    <div className="text-xs uppercase tracking-[0.16em] text-slate-500">BERT+LoRA toxicity</div>
                    <div className="mt-2 font-semibold text-cyan-300">{result.pipeline_status.toxicity_model || "bilinmiyor"}</div>
                  </div>
                  <div className="rounded-xl border border-slate-800 bg-slate-950 p-4">
                    <div className="text-xs uppercase tracking-[0.16em] text-slate-500">Gemini claim</div>
                    <div className="mt-2 font-semibold text-violet-300">{result.pipeline_status.gemini_claim_extraction || "bilinmiyor"}</div>
                  </div>
                  <div className="rounded-xl border border-slate-800 bg-slate-950 p-4">
                    <div className="text-xs uppercase tracking-[0.16em] text-slate-500">Tavily evidence</div>
                    <div className="mt-2 font-semibold text-amber-300">{result.pipeline_status.tavily?.status || "bilinmiyor"} · {result.pipeline_status.tavily?.count ?? 0} kaynak</div>
                  </div>
                  <div className="rounded-xl border border-slate-800 bg-slate-950 p-4">
                    <div className="text-xs uppercase tracking-[0.16em] text-slate-500">Gemini final</div>
                    <div className="mt-2 font-semibold text-emerald-300">{result.pipeline_status.gemini_final_reasoning || "bilinmiyor"}</div>
                  </div>
                </div>
                <p className="mt-3 rounded-xl border border-slate-800 bg-slate-950 p-4 text-sm text-slate-400">
                  {result.pipeline_status.message || "Pipeline durumu mevcut değil."}
                </p>
              </Card>
            )}

            {result?.source_analysis && (
              <Card title="Kaynak Zinciri">
                <div className="space-y-4">
                  <div className="grid grid-cols-1 gap-3 md:grid-cols-2">
                    <div className="rounded-xl border border-slate-800 bg-slate-950 p-4">
                      <div className="text-xs uppercase tracking-[0.2em] text-slate-500 mb-2">
                        Muhtemel birincil paylaşım hesabı
                      </div>
                      <div className="text-lg font-bold text-white">
                        {result.source_analysis.likely_original_source || result.source_analysis.likely_original_author || "Belirlenemedi"}
                      </div>
                      {result.source_analysis.likely_original_author && (
                        <div className="text-sm text-blue-400 font-mono mt-0.5">
                          {result.source_analysis.likely_original_author}
                        </div>
                      )}
                      {result.source_analysis.likely_original_excerpt && (
                        <div className="mt-3 text-sm text-slate-300 italic border-l-2 border-slate-800 pl-3 py-1">
                          “{result.source_analysis.likely_original_excerpt}”
                        </div>
                      )}
                      {result.source_analysis.likely_original_date && (
                        <div className="mt-2 text-xs text-slate-500">
                          {result.source_analysis.likely_original_date}
                        </div>
                      )}
                      {result.source_analysis.likely_original_url && (
                        <div className="mt-3">
                          <a
                            href={result.source_analysis.likely_original_url}
                            target="_blank"
                            rel="noopener noreferrer"
                            className="inline-block rounded-lg bg-blue-600 hover:bg-blue-700 px-3 py-1.5 text-xs font-semibold text-white transition-colors"
                          >
                            Paylaşımı Gör →
                          </a>
                        </div>
                      )}
                    </div>
                    <div className="rounded-xl border border-slate-800 bg-slate-950 p-4 flex flex-col justify-between">
                      <div>
                        <div className="text-xs uppercase tracking-[0.2em] text-slate-500">
                          BİRİNCİL KAYNAK ADAY SKORU
                        </div>
                        <div className="mt-2 text-3xl font-extrabold text-emerald-400">
                          {result.source_analysis.source_probability ?? 0}%
                        </div>
                      </div>
                      {result.source_analysis.likely_original_platform && (
                        <div className="mt-4 text-xs text-slate-500 font-medium">
                          Platform: <span className="text-slate-300 font-semibold">{result.source_analysis.likely_original_platform}</span>
                        </div>
                      )}
                    </div>
                  </div>

                  <div className="rounded-xl border border-slate-800 bg-slate-950 p-4 text-sm text-slate-300">
                    <div className="mb-2 text-xs uppercase tracking-[0.2em] text-slate-500">Durum</div>
                    {result.source_analysis.source_status === "partial_error" ? (
                      <>
                        <div className="mb-2 font-semibold text-amber-200">Kısmi kaynak sonucu — birincil doğrulama bekliyor</div>
                        <div>{result.source_analysis.reasoning || "Kaynak değerlendirmesi tamamlanamadı; aday bağlantılar aşağıda gösteriliyor."}</div>
                      </>
                    ) : (
                      result.source_analysis.reasoning || "Kaynak zinciri kesin olarak belirlenemedi."
                    )}
                  </div>

                  <button
                    onClick={() => setSourceChainOpen((v) => !v)}
                    className="rounded-xl border border-blue-500/40 bg-blue-500/10 px-4 py-2 text-sm font-semibold text-blue-200 hover:bg-blue-500/20"
                  >
                    {sourceChainOpen ? "Kaynakları Gizle" : "Kaynakları Gör"}
                  </button>

                  {sourceChainOpen && (
                    <div className="space-y-3">
                      {(result.source_analysis.source_chain || []).length > 0 ? (
                        result.source_analysis.source_chain!.map((item, index) => {
                          const hasUrl = !!item.url;
                          const lowMatch = typeof item.match_probability === "number" && item.match_probability < 20;
                          return (
                            <div
                              key={`${item.url || item.source}-${index}`}
                              className="block rounded-xl border border-slate-800 bg-slate-950 p-4 text-sm transition"
                            >
                              <div className="flex items-start justify-between gap-4">
                                <div className="space-y-1">
                                  <div className="font-semibold text-white">
                                    {item.source || item.author || "Birincil kaynak adayı"}
                                  </div>
                                  {item.author && (
                                    <div className="text-xs text-blue-400 font-mono">
                                      {item.author}
                                    </div>
                                  )}
                                  <div className={`inline-flex rounded-full px-2 py-1 text-[10px] font-bold ${lowMatch ? "bg-amber-500/10 text-amber-300" : "bg-emerald-500/10 text-emerald-300"}`}>
                                    {lowMatch ? "Düşük eşleşme — incele" : "İlgili aday kaynak"}
                                  </div>
                                  <div className="text-xs text-slate-500">
                                    {item.date || "Tarih bilinmiyor"}
                                    {item.platform ? ` · ${item.platform}` : ""}
                                    {item.primary_probability && item.primary_probability > 0 ? ` · Birincil olasılık: %${item.primary_probability}` : ""}
                                    {typeof item.match_probability === "number" ? ` · Eşleşme: %${item.match_probability}` : ""}
                                  </div>
                                </div>
                                {hasUrl && (
                                  <a
                                    href={item.url}
                                    target="_blank"
                                    rel="noopener noreferrer"
                                    className="shrink-0 rounded-lg bg-slate-900 border border-slate-800 hover:border-blue-500 hover:bg-slate-800 px-2.5 py-1.5 text-xs text-blue-400 transition"
                                  >
                                    Kaynağı Aç ↗
                                  </a>
                                )}
                              </div>
                              {item.url && (
                                <div className="mt-3 break-all text-xs text-slate-600 font-mono">
                                  {item.url}
                                </div>
                              )}
                            </div>
                          );
                        })
                      ) : (
                        <div className="rounded-xl border border-amber-500/20 bg-amber-500/5 p-4 text-amber-200">
                          Kaynak değerlendirmesi timeout nedeniyle tamamlanamadı; bu analiz için gösterilebilir aday bağlantı bulunamadı.
                        </div>
                      )}
                    </div>
                  )}
                </div>
              </Card>
            )}

            {/* CLAIMS */}
            <Card title="Tespit edilen iddialar">

              {result.claims && result.claims.length > 0 ? (

                <div className="space-y-3">

                  {result.claims.map((claim, index) => (

                    <div
                      key={index}
                      className="rounded-xl border border-slate-800 bg-slate-950 p-4"
                    >

                      <span className="mr-3 font-semibold text-blue-400">
                        {index + 1}.
                      </span>

                      {claim}

                    </div>

                  ))}

                </div>

              ) : (

                <div className="rounded-xl border border-slate-800 bg-slate-950 p-4 text-slate-500">
                  Doğrulanabilir bir iddia tespit edilemedi.
                </div>

              )}

            </Card>

            {/* CONTEXT */}
            <Card title="Eksik veya önemli bağlam">

              <p className="leading-7 text-slate-300">
                {result.context || "Ek bağlam bulunamadı."}
              </p>

            </Card>

            {/* SUPPORTING / CONTRADICTING SOURCES */}
            <div className="grid grid-cols-1 gap-4 lg:grid-cols-2">

              <Card title="Destekleyen kaynaklar">

                                  {result.claim && (
                    <div className="mb-4 rounded-xl border border-cyan-500/20 bg-cyan-500/5 p-4 text-sm text-cyan-100">
                      <div className="text-xs uppercase tracking-[0.2em] text-cyan-300">İncelenen ana iddia</div>
                      <p className="mt-2 leading-6">{result.claim}</p>
                    </div>
                  )}
                  {result.supporting_sources && result.supporting_sources.length > 0 ? (
                    <div className="space-y-3">

                    {result.supporting_sources.map((source, index) => (

                      <SourceLink key={`support-${index}`} source={source} />

                    ))}

                  </div>

                ) : (

                  <div className="rounded-xl border border-slate-800 bg-slate-950 p-4 text-slate-500">
                    Bu iddiayı destekleyen kaynak bulunamadı.
                  </div>

                )}

              </Card>

              <Card title="Çelişkili kaynaklar">

                {result.contradicting_sources && result.contradicting_sources.length > 0 ? (

                  <div className="space-y-3">

                    {result.contradicting_sources.map((source, index) => (

                      <SourceLink key={`contradict-${index}`} source={source} />

                    ))}

                  </div>

                ) : (

                  <div className="rounded-xl border border-slate-800 bg-slate-950 p-4 text-slate-500">
                    Çelişkili kaynak bulunamadı.
                  </div>

                )}

              </Card>

            </div>

            {/* SOURCES */}
            <Card title="Kaynaklar">

              {result.sources && result.sources.length > 0 ? (

                <div className="space-y-3">

                  {result.sources.map((source, index) => (

                    <SourceLink key={`source-${index}`} source={source} />

                  ))}

                </div>

              ) : (

                <div className="rounded-xl border border-slate-800 bg-slate-950 p-4 text-slate-500">
                  Güvenilir kaynak bulunamadı veya yeterli kanıt elde edilemedi.
                </div>

              )}

            </Card>

            </div>
          </section>
        )}

        {/* FOOTER */}
        <footer className="mt-16 border-t border-slate-800 pt-6 text-center text-sm text-slate-600">
          TruthLens AI — Bilgi güvenilirliği ve dijital içerik analiz sistemi
        </footer>

        {feedOpen && (
          <div className="fixed inset-0 z-50 flex items-start justify-center overflow-y-auto bg-slate-950/90 p-4 backdrop-blur-sm md:p-8">
            <section className="relative w-full max-w-6xl rounded-3xl border border-slate-800 bg-slate-900 shadow-2xl shadow-blue-950/30">
              <div className="sticky top-0 z-10 flex items-center justify-between gap-3 border-b border-slate-800 bg-slate-900/95 px-5 py-4 backdrop-blur md:px-6">
                <div>
                  <div className="text-xs font-bold uppercase tracking-[0.2em] text-slate-500">
                    {feedSource === "live" ? "Canlı Bluesky Feed" : "Demo Feed"}
                  </div>
                  <h2 className="mt-2 text-2xl font-bold text-white">TruthLens akışı</h2>
                </div>
                <button
                  onClick={() => setFeedOpen(false)}
                  className="rounded-xl border border-slate-700 px-4 py-2 text-sm font-semibold text-slate-300 hover:bg-slate-800"
                >
                  Kapat
                </button>
              </div>

              <nav className="flex flex-wrap gap-2 border-b border-slate-800 bg-slate-950/60 px-4 py-3 md:px-6" aria-label="Sosyal platform navigasyonu">
                {([
                  ["home", "Ana Akış"],
                  ["liked", "Beğenilenler"],
                  ["profile", "Profil"],
                  ["settings", "Ayarlar"],
                ] as const).map(([view, label]) => (
                  <button
                    key={view}
                    onClick={() => setSocialView(view)}
                    className={`rounded-xl px-4 py-2 text-sm font-semibold ${socialView === view ? "bg-blue-500/20 text-blue-200" : "text-slate-400 hover:bg-slate-800 hover:text-white"}`}
                  >
                    {label}
                  </button>
                ))}
                <span className="ml-auto rounded-xl border border-cyan-500/30 bg-cyan-500/10 px-4 py-2 text-xs font-bold text-cyan-300">
                  {feedSource === "live" ? "Bluesky canlı sağlayıcı" : "Yerel demo sağlayıcı"}
                </span>
              </nav>

              <div className={`max-h-[82vh] overflow-y-auto px-4 pb-6 pt-5 md:px-6 ${socialView === "home" ? "block" : "hidden"}`}>
                {demoSummary && (
                  <div className="mb-5 rounded-2xl border border-blue-900/50 bg-blue-950/20 p-4">
                    <div className="flex flex-wrap items-center justify-between gap-3">
                      <div>
                        <div className="text-xs uppercase tracking-[0.2em] text-slate-400">Topluluk uyarısı</div>
                        <div className="mt-2 text-lg font-semibold text-white">{demoSummary.highlight}</div>
                      </div>
                      <div className="rounded-full border border-amber-500/30 bg-amber-500/10 px-3 py-1 text-xs font-bold uppercase text-amber-300">
                        {demoSummary.top_emotion}
                      </div>
                    </div>
                    <div className="mt-4 grid grid-cols-1 gap-3 md:grid-cols-3">
                      <div className="rounded-xl border border-slate-800 bg-slate-950 p-3">
                        <div className="text-xs uppercase tracking-[0.2em] text-slate-500">Ortalama skor</div>
                        <div className="mt-2 text-2xl font-bold text-blue-300">{demoSummary.avg_truthlens_score}/100</div>
                      </div>
                      <div className="rounded-xl border border-slate-800 bg-slate-950 p-3">
                        <div className="text-xs uppercase tracking-[0.2em] text-slate-500">Risk seviyesi</div>
                        <div className="mt-2 text-2xl font-bold text-amber-300">{demoSummary.risk_level}</div>
                      </div>
                      <div className="rounded-xl border border-slate-800 bg-slate-950 p-3">
                        <div className="text-xs uppercase tracking-[0.2em] text-slate-500">Gönderi sayısı</div>
                        <div className="mt-2 text-2xl font-bold text-emerald-300">{demoSummary.total_posts}</div>
                      </div>
                    </div>
                  </div>
                )}

                <div className="mb-5 rounded-2xl border border-cyan-500/30 bg-cyan-950/20 p-4">
                  <div className="flex flex-wrap items-center justify-between gap-3">
                    <div>
                      <div className="text-xs font-bold uppercase tracking-[0.2em] text-cyan-300">NSosyal Entegrasyon Önizlemesi</div>
                      <div className="mt-1 text-sm text-slate-300">Gönderi yayınlanmadan önce TruthLens moderasyon adapteri toksisiteyi ve insan incelemesi gereğini kontrol eder.</div>
                    </div>
                    <span className="rounded-full border border-emerald-400/30 bg-emerald-400/10 px-3 py-1 text-xs font-bold text-emerald-300">Adapter v1 · Hazır</span>
                  </div>
                  <textarea
                    value={nsosyalDraft}
                    onChange={(event) => {
                      setNsosyalDraft(event.target.value);
                      setNsosyalCheck(null);
                      setNsosyalPublished(false);
                    }}
                    placeholder="NSosyal’de paylaşmak istediğin metni yaz..."
                    className="mt-4 min-h-24 w-full rounded-xl border border-slate-700 bg-slate-950 p-3 text-sm leading-6 text-slate-100 outline-none placeholder:text-slate-600 focus:border-cyan-400"
                    maxLength={10000}
                  />
                  <div className="mt-3 flex flex-wrap items-center gap-3">
                    <button
                      onClick={checkNsosyalPost}
                      disabled={nsosyalChecking || !nsosyalDraft.trim()}
                      className="rounded-xl bg-cyan-500 px-4 py-2 text-sm font-bold text-slate-950 hover:bg-cyan-300 disabled:cursor-not-allowed disabled:opacity-50"
                    >
                      {nsosyalChecking ? "Toksisite ve moderasyon kontrol ediliyor..." : "Gönderiyi moderasyondan geçir"}
                    </button>
                    <span className="text-xs text-slate-500">Gerçek platforma otomatik paylaşım yapılmaz; bu alan entegrasyon sözleşmesini simüle eder.</span>
                  </div>

                  {nsosyalCheck && (
                    <div className="mt-4 rounded-xl border border-slate-700 bg-slate-950 p-4">
                      <div className="flex flex-wrap items-center justify-between gap-3">
                        <div className="text-sm font-bold text-white">TruthLens karar motoru sonucu</div>
                        <span className={`rounded-full px-3 py-1 text-xs font-bold ${nsosyalCheck.publish.allowed ? "bg-emerald-500/15 text-emerald-300" : "bg-rose-500/15 text-rose-300"}`}>
                          {nsosyalCheck.publish.allowed ? "Yayın akışına uygun" : "İnsan incelemesine al"}
                        </span>
                      </div>
                      <div className="mt-3 grid grid-cols-2 gap-2 text-xs text-slate-200 md:grid-cols-4">
                        <div className="rounded-lg border border-slate-800 bg-slate-900 p-2">Hakaret: %{nsosyalCheck.toxicity.insult}</div>
                        <div className="rounded-lg border border-slate-800 bg-slate-900 p-2">Zorbalık: %{nsosyalCheck.toxicity.bullying}</div>
                        <div className="rounded-lg border border-slate-800 bg-slate-900 p-2">Nefret: %{nsosyalCheck.toxicity.hate_speech}</div>
                        <div className="rounded-lg border border-slate-800 bg-slate-900 p-2">Risk: {nsosyalCheck.toxicity.risk_level}</div>
                      </div>
                      <div className="mt-3 rounded-lg border border-blue-900/50 bg-blue-950/20 p-3 text-sm text-blue-100">
                        <span className="font-semibold">Aksiyon:</span> {nsosyalCheck.moderation.action_label}. {nsosyalCheck.publish.message}
                      </div>
                      <div className="mt-3 flex flex-wrap gap-2 text-xs text-slate-400">
                        <span className="rounded-full border border-slate-700 px-3 py-1">API: `/nsosyal/moderation-check`</span>
                        <span className="rounded-full border border-slate-700 px-3 py-1">İnsan onayı: {nsosyalCheck.publish.human_review_required ? "Gerekli" : "Gerekmiyor"}</span>
                        <span className="rounded-full border border-slate-700 px-3 py-1">Otomatik silme: Kapalı</span>
                      </div>
                      {nsosyalCheck.publish.allowed && (
                        <div className="mt-4 flex flex-wrap gap-2">
                          <button
                            onClick={publishNsosyalDemoPost}
                            className="rounded-xl border border-emerald-400/40 bg-emerald-500/10 px-4 py-2 text-sm font-bold text-emerald-200 hover:bg-emerald-500/20"
                          >
                            NSosyal demo akışına ekle
                          </button>
                          <button
                            onClick={publishToBluesky}
                            className="rounded-xl border border-sky-400/40 bg-sky-500/10 px-4 py-2 text-sm font-bold text-sky-200 hover:bg-sky-500/20"
                          >
                            Bluesky’ye gerçek gönder
                          </button>
                        </div>
                      )}
                      {nsosyalPublished && (
                        <div className="mt-3 text-sm font-semibold text-emerald-300">Gönderi kontrollü NSosyal demo akışına eklendi.</div>
                      )}
                    </div>
                  )}
                </div>

                {feedRefreshing && (
                  <div className="mb-4 rounded-2xl border border-slate-800 bg-slate-950 p-4 text-sm text-slate-400">
                    🤖 TruthLens mini analizleri güncelleniyor...
                  </div>
                )}

                <div className="space-y-4">
                  {demoFeed.map((post) => (
                    <div key={post.id} className="rounded-2xl border border-slate-800 bg-slate-950 p-4 md:p-5">
                          <div className="mb-4 flex items-center justify-between gap-3">
                        <div className="flex items-center gap-3">
                          <div className="h-10 w-10 overflow-hidden rounded-full border border-slate-700 bg-slate-800">
                            {post.avatar ? (
                              <img src={post.avatar} alt={post.author} className="h-full w-full object-cover" />
                            ) : (
                              <div className="flex h-full w-full items-center justify-center text-sm font-bold text-white">
                                {post.author.slice(0, 1).toUpperCase()}
                              </div>
                            )}
                          </div>
                          <div>
                            <div className="font-semibold text-white">{post.author}</div>
                            <div className="text-xs text-slate-500">{post.handle}</div>
                          </div>
                        </div>
                        <div className="flex items-center gap-2">
                          {post.verified_by_truthlens && (
                            <span
                              title="Bu paylaşım TruthLens analizinden geçti; sonuç kesin doğruluk garantisi değildir."
                              className="inline-flex items-center gap-1 rounded-full border border-emerald-400/40 bg-emerald-400/10 px-2.5 py-1 text-[10px] font-bold text-emerald-300"
                            >
                              ✓ Kanıt kapsamı tamamlandı
                            </span>
                          )}
                          <span className="rounded-full border border-slate-700 bg-slate-900 px-3 py-1 text-[10px] font-bold uppercase tracking-[0.2em] text-slate-300">
                            {post.tag}
                          </span>
                        </div>
                      </div>

                      <p className="text-base leading-7 text-slate-200">{post.content}</p>

                      {Array.isArray(post.image_urls) && post.image_urls.length > 0 && (
                        <div className="mt-4 grid gap-3 sm:grid-cols-2">
                          {post.image_urls.slice(0, 2).map((imageUrl: string, index: number) => (
                            <div key={`${post.id}-${index}`} className="space-y-2">
                              <img
                                src={imageUrl}
                                alt={`${post.author} görsel ${index + 1}`}
                                className="h-56 w-full rounded-2xl border border-slate-800 object-cover shadow-lg shadow-slate-950/40"
                              />
                              <div className="rounded-xl border border-slate-800 bg-slate-900/70 px-3 py-2 text-xs text-slate-300">
                                🖼️ Foto AI:{" "}
                                {post.image_analysis_available
                                  ? (post.image_ai_probability && post.image_ai_probability > 0
                                      ? `${post.image_ai_probability}/100`
                                      : "Analiz ediliyor")
                                  : "Kullanılamıyor"}
                              </div>
                            </div>
                          ))}
                        </div>
                      )}

                      <div className="mt-4 rounded-2xl border border-blue-900/50 bg-blue-950/20 p-4">
                        <div className="mb-2 flex items-center gap-2 text-xs font-bold uppercase tracking-[0.2em] text-blue-300">
                          <span>🤖</span>
                          <span>TruthLens AI</span>
                        </div>
                        <div className="text-sm text-blue-100">
                          <span className="font-semibold text-white">Kısa Özet:</span>{" "}
                          {post.analysis_status === "ready" || post.analysis_status === "cached"
                            ? (post.ai?.summary || post.summary || post.reason || "Bu içerik TruthLens tarafından incelendi.")
                            : "🤖 TruthLens analiz ediliyor..."}
                        </div>
                        <div className="mt-3 grid grid-cols-2 gap-2 text-xs text-slate-200 md:grid-cols-4">
                          <div className="rounded-xl border border-slate-700 bg-slate-900/70 p-2">⚠️ Risk: {post.misinformation_risk ?? post.truthlens_score ?? 0}/100</div>
                          <div className="rounded-xl border border-slate-700 bg-slate-900/70 p-2">🔥 Kutuplaşma: {post.polarization ?? 0}/100</div>
                          <div className="rounded-xl border border-slate-700 bg-slate-900/70 p-2">🛡️ Nefret: {post.hate_speech ?? 0}/100</div>
                          <div className="rounded-xl border border-slate-700 bg-slate-900/70 p-2">💬 Duygu: {post.sentiment || post.emotion || "Belirsiz"}</div>
                        </div>
                      </div>

                      <div className="mt-4 rounded-xl border border-blue-900/50 bg-blue-950/20 p-3 text-sm text-blue-100">
                        <span className="font-semibold">Neden?</span> {post.reason}
                      </div>

                      <div className="mt-3 text-sm font-semibold text-emerald-300">
                        Doğruluk / Güvenilirlik: {Math.max(0, Math.min(100, post.truthlens_score ?? (100 - (post.misinformation_risk ?? 100))))}%
                      </div>

                      <div className="mt-4 flex flex-wrap items-center justify-between gap-3">
                        <div className="flex flex-wrap items-center gap-2 text-xs text-slate-400">
                          <span>💬 {post.engagement?.replies ?? 0}</span>
                          <span>🔁 {post.engagement?.reposts ?? 0}</span>
                          <span>♥ {post.engagement?.likes ?? 0}</span>
                          <button onClick={() => toggleSocialLike(post)} className={`rounded-lg border px-3 py-1.5 font-semibold ${likedPostIds.has(post.id) ? "border-rose-400/40 bg-rose-500/15 text-rose-200" : "border-slate-700 text-slate-300 hover:bg-slate-800"}`}>
                            {likedPostIds.has(post.id) ? "♥ Beğenildi" : "♡ Beğen"}
                          </button>
                          <button onClick={() => repostSocialPost(post)} className="rounded-lg border border-slate-700 px-3 py-1.5 font-semibold text-slate-300 hover:bg-slate-800">🔁 Yeniden paylaş</button>
                          <button onClick={() => startSocialReply(post)} className="rounded-lg border border-slate-700 px-3 py-1.5 font-semibold text-slate-300 hover:bg-slate-800">💬 Yanıtla</button>
                        </div>
                        <button
                          onClick={async () => {
                            setContent(post.content);
                            setMode("text");
                            setFeedOpen(false);
                            const analyzed = await sendAnalysis("/analyze", { content: post.content });
                            if (analyzed?.verification) {
                              setDemoFeed((current) =>
                                current.map((item) =>
                                  item.id === post.id
                                    ? {
                                        ...item,
                                        verification: analyzed.verification,
                                        verified_by_truthlens: Boolean(analyzed.verification?.verified),
                                      }
                                    : item
                                )
                              );
                            }
                          }}
                          className="rounded-xl border border-blue-500/40 bg-blue-500/10 px-4 py-2 text-sm font-semibold text-blue-200 hover:bg-blue-500/20"
                        >
                          Detaylı Analiz
                        </button>
                      </div>
                      {socialActionStatus && (
                        <div className="mt-3 rounded-lg border border-cyan-500/20 bg-cyan-500/5 p-2 text-xs text-cyan-200">{socialActionStatus}</div>
                      )}
                      {post.analysis_status !== "ready" && post.analysis_status !== "cached" && (
                        <div className="mt-3 rounded-xl border border-slate-800 bg-slate-900/70 p-3 text-xs text-slate-400">
                          🤖 TruthLens analizi beklemede. Gönderi görünür durumda.
                        </div>
                      )}
                    </div>
                  ))}
                </div>

                <div className="mt-6 flex items-center justify-center">
                  <button
                    onClick={loadMoreFeed}
                    disabled={feedLimit >= 20 || feedRefreshing}
                    className="rounded-xl border border-blue-500/40 bg-blue-500/10 px-5 py-3 text-sm font-semibold text-blue-200 hover:bg-blue-500/20 disabled:cursor-not-allowed disabled:opacity-50"
                  >
                    {feedLimit >= 20 ? "Daha fazla yok" : feedRefreshing ? "Yükleniyor..." : "Daha fazla"}
                  </button>
                </div>
              </div>

              {socialView !== "home" && (
                <div className="max-h-[82vh] overflow-y-auto px-4 pb-6 pt-5 md:px-6">
                  {socialView === "liked" && (
                    <div>
                      <div className="mb-4 text-xs font-bold uppercase tracking-[0.2em] text-slate-500">Kişisel koleksiyon</div>
                      <h3 className="text-2xl font-bold text-white">Beğenilenler</h3>
                      <div className="mt-4 space-y-3">
                        {demoFeed.filter((post) => likedPostIds.has(post.id)).length === 0 ? (
                          <div className="rounded-2xl border border-slate-800 bg-slate-950 p-5 text-sm text-slate-400">Henüz beğenilen gönderi yok. Ana Akış’ta kalp düğmesine bas.</div>
                        ) : demoFeed.filter((post) => likedPostIds.has(post.id)).map((post) => (
                          <div key={`liked-${post.id}`} className="rounded-2xl border border-slate-800 bg-slate-950 p-4">
                            <div className="text-sm font-semibold text-white">{post.author} <span className="text-slate-500">{post.handle}</span></div>
                            <p className="mt-2 text-sm leading-6 text-slate-300">{post.content}</p>
                            <button onClick={() => toggleSocialLike(post)} className="mt-3 rounded-lg border border-rose-400/30 bg-rose-500/10 px-3 py-1.5 text-xs font-semibold text-rose-200">Beğeniyi kaldır</button>
                          </div>
                        ))}
                      </div>
                    </div>
                  )}

                  {socialView === "profile" && (
                    <div className="rounded-3xl border border-slate-800 bg-slate-950 p-6">
                      <div className="flex flex-wrap items-center gap-4">
                        <div className="flex h-16 w-16 items-center justify-center rounded-full bg-blue-500/20 text-2xl font-bold text-blue-200">{(user?.name || "T").slice(0, 1).toUpperCase()}</div>
                        <div>
                          <h3 className="text-2xl font-bold text-white">{user?.name || "TruthLens Demo Profili"}</h3>
                          <p className="text-sm text-slate-500">{user?.email || "@truthlens_demo"}</p>
                        </div>
                      </div>
                      <div className="mt-6 grid grid-cols-2 gap-3 md:grid-cols-4">
                        <div className="rounded-xl border border-slate-800 bg-slate-900 p-3"><div className="text-xs text-slate-500">Gönderi</div><div className="mt-1 text-xl font-bold text-white">{demoFeed.length}</div></div>
                        <div className="rounded-xl border border-slate-800 bg-slate-900 p-3"><div className="text-xs text-slate-500">Beğeni</div><div className="mt-1 text-xl font-bold text-white">{likedPostIds.size}</div></div>
                        <div className="rounded-xl border border-slate-800 bg-slate-900 p-3"><div className="text-xs text-slate-500">Analiz</div><div className="mt-1 text-xl font-bold text-white">{history.length}</div></div>
                        <div className="rounded-xl border border-slate-800 bg-slate-900 p-3"><div className="text-xs text-slate-500">Sağlayıcı</div><div className="mt-1 text-xl font-bold text-cyan-300">{feedSource === "live" ? "Bluesky" : "Demo"}</div></div>
                      </div>
                      <div className="mt-5 rounded-xl border border-cyan-500/20 bg-cyan-500/5 p-4 text-sm leading-6 text-slate-300">Bu profil paneli aynı sosyal arayüz içinde TruthLens analiz geçmişini ve platform sağlayıcısını gösterir. Gerçek Bluesky profil istatistikleri, sağlayıcı kimlik bilgileri yapılandırıldığında adapter üzerinden alınabilir.</div>
                    </div>
                  )}

                  {socialView === "settings" && (
                    <div className="rounded-3xl border border-slate-800 bg-slate-950 p-6">
                      <div className="text-xs font-bold uppercase tracking-[0.2em] text-slate-500">Platform ayarları</div>
                      <h3 className="mt-2 text-2xl font-bold text-white">Sosyal deneyim ayarları</h3>
                      <div className="mt-5 space-y-3">
                        <div className="flex items-center justify-between rounded-xl border border-slate-800 bg-slate-900 p-4"><div><div className="font-semibold text-white">Yayın öncesi moderasyon</div><div className="text-xs text-slate-500">NSosyal adapteri her gönderiyi yayın öncesi kontrol eder.</div></div><span className="rounded-full bg-emerald-500/15 px-3 py-1 text-xs font-bold text-emerald-300">Açık</span></div>
                        <div className="flex items-center justify-between rounded-xl border border-slate-800 bg-slate-900 p-4"><div><div className="font-semibold text-white">Otomatik silme</div><div className="text-xs text-slate-500">Geri dönüşü olmayan işlemler insan onayı olmadan çalışmaz.</div></div><span className="rounded-full bg-slate-700 px-3 py-1 text-xs font-bold text-slate-300">Kapalı</span></div>
                        <div className="flex items-center justify-between rounded-xl border border-slate-800 bg-slate-900 p-4"><div><div className="font-semibold text-white">Sağlayıcı</div><div className="text-xs text-slate-500">NSosyal API doğrulanana kadar güvenli fallback.</div></div><span className="rounded-full bg-cyan-500/15 px-3 py-1 text-xs font-bold text-cyan-300">{feedSource === "live" ? "Bluesky" : "Demo"}</span></div>
                      </div>
                    </div>
                  )}
                </div>
              )}
            </section>
          </div>
        )}

      </div>
    </main>
  );
}

/* ============================================================
   METRIC COMPONENT
============================================================ */

function Metric({
  title,
  value,
}: {
  title: string;
  value: number;
}) {
  const safeValue = Math.min(100, Math.max(0, value));

  return (
    <div className="rounded-2xl border border-slate-800 bg-slate-900 p-6">

      <h3 className="text-sm font-medium text-slate-400">
        {title}
      </h3>

      <div className="mt-3 flex items-end justify-between">

        <span className="text-3xl font-bold">
          {safeValue}%
        </span>

        <span className="text-sm text-slate-500">
          risk
        </span>

      </div>

      <div className="mt-4 h-2 overflow-hidden rounded-full bg-slate-800">

        <div
          className="h-full bg-blue-500 transition-all duration-700"
          style={{
            width: `${safeValue}%`,
          }}
        />

      </div>

    </div>
  );
}

function SourceLink({ source }: { source: Source }) {
  return (
    <a
      href={source.url}
      target="_blank"
      rel="noopener noreferrer"
      className="block rounded-xl border border-slate-800 bg-slate-950 p-4 transition hover:border-blue-500"
    >

      <div className="flex items-center justify-between gap-3">
        <div className="font-semibold text-blue-400">
          {source.title}
        </div>

        {typeof source.reliability === "number" && (
          <span className="rounded-full border border-emerald-500/30 bg-emerald-500/10 px-3 py-1 text-[11px] font-bold text-emerald-300">
            {source.reliability}%
          </span>
        )}
      </div>

      <p className="mt-2 text-sm leading-6 text-slate-400">
        {source.relevance}
      </p>

      {source.reliability_reason && (
        <p className="mt-2 text-xs leading-5 text-slate-500">
          {source.reliability_reason}
        </p>
      )}

      <p className="mt-3 break-all text-xs text-slate-600">
        {source.url}
      </p>

    </a>
  );
}

/* ============================================================
   CARD COMPONENT
============================================================ */

function Card({
  title,
  children,
}: {
  title: string;
  children: React.ReactNode;
}) {
  return (
    <div className="rounded-2xl border border-slate-800 bg-slate-900 p-6">

      <h2 className="mb-4 text-xl font-semibold">
        {title}
      </h2>

      {children}

    </div>
  );
}
