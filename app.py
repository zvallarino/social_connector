import json
import os
from dataclasses import dataclass
from typing import Any, Dict, List, Optional

import requests
import streamlit as st
from dotenv import load_dotenv

load_dotenv()


@dataclass
class ApiResult:
    request_details: Dict[str, Any]
    status_code: Optional[int]
    response_body: Any
    error: Optional[str] = None


class BaseClient:
    timeout = 30

    @staticmethod
    def _safe_json(response: requests.Response) -> Any:
        try:
            return response.json()
        except ValueError:
            return response.text


# ---------------------------------------------------------------------------
# Key-required connectors
# ---------------------------------------------------------------------------

class TwitterClient(BaseClient):
    BASE_URL = "https://api.twitter.com/2"

    def search(self, search_mode: str, query: str, max_results: int) -> ApiResult:
        bearer_token = os.getenv("TWITTER_BEARER_TOKEN")
        if not bearer_token:
            return ApiResult({}, None, {}, error="Missing TWITTER_BEARER_TOKEN in environment.")

        headers = {"Authorization": f"Bearer {bearer_token}"}
        redacted_headers = {"Authorization": "Bearer ***redacted***"}

        if search_mode == "profile":
            username = query.lstrip("@")
            url = f"{self.BASE_URL}/users/by/username/{username}"
            params = {"user.fields": "name,username,description,public_metrics,created_at"}
            request_details = {"method": "GET", "url": url, "params": params, "headers": redacted_headers}
            try:
                resp = requests.get(url, params=params, headers=headers, timeout=self.timeout)
                return ApiResult(request_details, resp.status_code, self._safe_json(resp))
            except requests.RequestException as exc:
                return ApiResult(request_details, None, {}, error=str(exc))
        else:
            url = f"{self.BASE_URL}/tweets/search/recent"
            params = {
                "query": query,
                "max_results": min(max(max_results, 10), 100),
                "tweet.fields": "created_at,author_id,text,public_metrics",
            }
            request_details = {"method": "GET", "url": url, "params": params, "headers": redacted_headers}
            try:
                resp = requests.get(url, params=params, headers=headers, timeout=self.timeout)
                return ApiResult(request_details, resp.status_code, self._safe_json(resp))
            except requests.RequestException as exc:
                return ApiResult(request_details, None, {}, error=str(exc))


class RedditClient(BaseClient):
    TOKEN_URL = "https://www.reddit.com/api/v1/access_token"
    BASE_URL = "https://oauth.reddit.com"

    def _get_token(self, client_id: str, client_secret: str) -> Optional[str]:
        resp = requests.post(
            self.TOKEN_URL,
            auth=(client_id, client_secret),
            data={"grant_type": "client_credentials"},
            headers={"User-Agent": "SocialConnector/1.0"},
            timeout=self.timeout,
        )
        resp.raise_for_status()
        return resp.json().get("access_token")

    def search(self, search_mode: str, query: str, max_results: int) -> ApiResult:
        client_id = os.getenv("REDDIT_CLIENT_ID")
        client_secret = os.getenv("REDDIT_CLIENT_SECRET")
        if not client_id or not client_secret:
            return ApiResult({}, None, {}, error="Missing REDDIT_CLIENT_ID or REDDIT_CLIENT_SECRET in environment.")

        try:
            token = self._get_token(client_id, client_secret)
        except requests.RequestException as exc:
            return ApiResult({}, None, {}, error=f"Reddit auth failed: {exc}")

        headers = {"Authorization": f"Bearer {token}", "User-Agent": "SocialConnector/1.0"}
        redacted_headers = {"Authorization": "Bearer ***redacted***", "User-Agent": "SocialConnector/1.0"}

        if search_mode == "profile":
            url = f"{self.BASE_URL}/user/{query}/about"
            params: Dict[str, Any] = {}
            request_details = {"method": "GET", "url": url, "params": params, "headers": redacted_headers}
            try:
                resp = requests.get(url, params=params, headers=headers, timeout=self.timeout)
                return ApiResult(request_details, resp.status_code, self._safe_json(resp))
            except requests.RequestException as exc:
                return ApiResult(request_details, None, {}, error=str(exc))
        else:
            url = f"{self.BASE_URL}/search"
            params = {"q": query, "limit": max_results, "type": "link", "sort": "relevance"}
            request_details = {"method": "GET", "url": url, "params": params, "headers": redacted_headers}
            try:
                resp = requests.get(url, params=params, headers=headers, timeout=self.timeout)
                return ApiResult(request_details, resp.status_code, self._safe_json(resp))
            except requests.RequestException as exc:
                return ApiResult(request_details, None, {}, error=str(exc))


class InstagramClient(BaseClient):
    BASE_URL = "https://graph.instagram.com"

    def search(self, search_mode: str, query: str, max_results: int) -> ApiResult:
        access_token = os.getenv("INSTAGRAM_ACCESS_TOKEN")
        if not access_token:
            return ApiResult({}, None, {}, error="Missing INSTAGRAM_ACCESS_TOKEN in environment.")

        if search_mode == "profile":
            endpoint = f"{self.BASE_URL}/me"
            params: Dict[str, Any] = {
                "fields": "id,username,account_type,media_count",
                "access_token": access_token,
            }
        else:
            endpoint = f"{self.BASE_URL}/me/media"
            params = {
                "fields": "id,caption,media_type,media_url,permalink,timestamp",
                "limit": max_results,
                "access_token": access_token,
            }

        request_details = {
            "method": "GET",
            "url": endpoint,
            "params": {**params, "access_token": "***redacted***"},
            "notes": (
                "Instagram Basic Display primarily returns authenticated user data. "
                "Use a Graph/Business setup for broader discovery."
            ),
        }
        try:
            resp = requests.get(endpoint, params=params, timeout=self.timeout)
            return ApiResult(request_details, resp.status_code, self._safe_json(resp))
        except requests.RequestException as exc:
            return ApiResult(request_details, None, {}, error=str(exc))


class TikTokClient(BaseClient):
    BASE_URL = os.getenv("TIKTOK_API_BASE", "https://open.tiktokapis.com")

    def search(self, search_mode: str, query: str, max_results: int) -> ApiResult:
        access_token = os.getenv("TIKTOK_ACCESS_TOKEN")
        if not access_token:
            return ApiResult({}, None, {}, error="Missing TIKTOK_ACCESS_TOKEN in environment.")

        endpoint = f"{self.BASE_URL}/v2/research/video/query/"
        hashtags = [tag.strip().lstrip("#") for tag in query.split() if tag.strip()] if search_mode == "hashtag" else []
        payload: Dict[str, Any] = {
            "max_count": max_results,
            "query": {
                "and": [
                    {
                        "operation": "IN",
                        "field_name": "hashtag_name",
                        "field_values": hashtags,
                    }
                ]
                if search_mode == "hashtag" and hashtags
                else []
            },
        }

        if search_mode in {"profile", "post"}:
            payload["query"] = {
                "and": [{"operation": "EQ", "field_name": "keyword", "field_values": [query]}]
            }

        headers = {"Authorization": f"Bearer {access_token}", "Content-Type": "application/json"}
        request_details = {
            "method": "POST",
            "url": endpoint,
            "headers": {"Authorization": "Bearer ***redacted***", "Content-Type": "application/json"},
            "json": payload,
            "notes": (
                "TikTok APIs vary by product tier. This request uses a Research-style endpoint "
                "that supports hashtag querying."
            ),
        }
        try:
            resp = requests.post(endpoint, headers=headers, json=payload, timeout=self.timeout)
            return ApiResult(request_details, resp.status_code, self._safe_json(resp))
        except requests.RequestException as exc:
            return ApiResult(request_details, None, {}, error=str(exc))


class YouTubeClient(BaseClient):
    BASE_URL = "https://www.googleapis.com/youtube/v3/search"

    def search(self, search_mode: str, query: str, max_results: int) -> ApiResult:
        api_key = os.getenv("YOUTUBE_API_KEY")
        if not api_key:
            return ApiResult({}, None, {}, error="Missing YOUTUBE_API_KEY in environment.")

        item_type = "video" if search_mode == "post" else "channel"
        params: Dict[str, Any] = {
            "part": "snippet",
            "q": query,
            "type": item_type,
            "maxResults": max_results,
            "key": api_key,
        }
        request_details = {"method": "GET", "url": self.BASE_URL, "params": {**params, "key": "***redacted***"}}
        try:
            resp = requests.get(self.BASE_URL, params=params, timeout=self.timeout)
            return ApiResult(request_details, resp.status_code, self._safe_json(resp))
        except requests.RequestException as exc:
            return ApiResult(request_details, None, {}, error=str(exc))


class OpenAIClient(BaseClient):
    BASE_URL = "https://api.openai.com/v1/chat/completions"

    def search(self, search_mode: str, query: str, max_results: int) -> ApiResult:
        api_key = os.getenv("OPENAI_API_KEY")
        if not api_key:
            return ApiResult({}, None, {}, error="Missing OPENAI_API_KEY in environment.")

        payload: Dict[str, Any] = {
            "model": "gpt-4o-mini",
            "messages": [{"role": "user", "content": query}],
            "max_tokens": max(max_results * 20, 100),
        }
        headers = {"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"}
        request_details = {
            "method": "POST",
            "url": self.BASE_URL,
            "headers": {"Authorization": "Bearer ***redacted***", "Content-Type": "application/json"},
            "json": payload,
        }
        try:
            resp = requests.post(self.BASE_URL, headers=headers, json=payload, timeout=self.timeout)
            return ApiResult(request_details, resp.status_code, self._safe_json(resp))
        except requests.RequestException as exc:
            return ApiResult(request_details, None, {}, error=str(exc))


class GeminiClient(BaseClient):
    BASE_URL = "https://generativelanguage.googleapis.com/v1beta/models/gemini-2.0-flash:generateContent"

    def search(self, search_mode: str, query: str, max_results: int) -> ApiResult:
        api_key = os.getenv("GEMINI_API_KEY")
        if not api_key:
            return ApiResult({}, None, {}, error="Missing GEMINI_API_KEY in environment.")

        payload: Dict[str, Any] = {"contents": [{"parts": [{"text": query}]}]}
        url = f"{self.BASE_URL}?key={api_key}"
        request_details = {
            "method": "POST",
            "url": f"{self.BASE_URL}?key=***redacted***",
            "json": payload,
        }
        try:
            resp = requests.post(url, json=payload, timeout=self.timeout)
            return ApiResult(request_details, resp.status_code, self._safe_json(resp))
        except requests.RequestException as exc:
            return ApiResult(request_details, None, {}, error=str(exc))


# ---------------------------------------------------------------------------
# No-key test connectors
# ---------------------------------------------------------------------------

class PubMedClient(BaseClient):
    BASE_URL = "https://eutils.ncbi.nlm.nih.gov/entrez/eutils/esearch.fcgi"

    def search(self, search_mode: str, query: str, max_results: int) -> ApiResult:
        params: Dict[str, Any] = {
            "db": "pubmed",
            "retmode": "json",
            "term": query,
            "retmax": max_results,
        }
        request_details = {"method": "GET", "url": self.BASE_URL, "params": params}
        try:
            resp = requests.get(self.BASE_URL, params=params, timeout=self.timeout)
            return ApiResult(request_details, resp.status_code, self._safe_json(resp))
        except requests.RequestException as exc:
            return ApiResult(request_details, None, {}, error=str(exc))


class ClinicalTrialsClient(BaseClient):
    BASE_URL = "https://clinicaltrials.gov/api/v2/studies"

    def search(self, search_mode: str, query: str, max_results: int) -> ApiResult:
        params: Dict[str, Any] = {
            "query.term": query,
            "pageSize": max_results,
            "format": "json",
        }
        request_details = {"method": "GET", "url": self.BASE_URL, "params": params}
        try:
            resp = requests.get(self.BASE_URL, params=params, timeout=self.timeout)
            return ApiResult(request_details, resp.status_code, self._safe_json(resp))
        except requests.RequestException as exc:
            return ApiResult(request_details, None, {}, error=str(exc))


class CrossrefClient(BaseClient):
    BASE_URL = "https://api.crossref.org/works"

    def search(self, search_mode: str, query: str, max_results: int) -> ApiResult:
        params: Dict[str, Any] = {
            "query": query,
            "rows": max_results,
            "select": "DOI,title,author,published,type,URL",
        }
        request_details = {"method": "GET", "url": self.BASE_URL, "params": params}
        try:
            resp = requests.get(self.BASE_URL, params=params, timeout=self.timeout)
            return ApiResult(request_details, resp.status_code, self._safe_json(resp))
        except requests.RequestException as exc:
            return ApiResult(request_details, None, {}, error=str(exc))


class WikipediaClient(BaseClient):
    SEARCH_URL = "https://en.wikipedia.org/w/api.php"
    SUMMARY_URL = "https://en.wikipedia.org/api/rest_v1/page/summary"

    def search(self, search_mode: str, query: str, max_results: int) -> ApiResult:
        if search_mode == "summary":
            url = f"{self.SUMMARY_URL}/{requests.utils.quote(query)}"
            request_details = {"method": "GET", "url": url}
            try:
                resp = requests.get(url, timeout=self.timeout)
                return ApiResult(request_details, resp.status_code, self._safe_json(resp))
            except requests.RequestException as exc:
                return ApiResult(request_details, None, {}, error=str(exc))
        else:
            params: Dict[str, Any] = {
                "action": "query",
                "list": "search",
                "srsearch": query,
                "srlimit": max_results,
                "format": "json",
                "utf8": 1,
            }
            request_details = {"method": "GET", "url": self.SEARCH_URL, "params": params}
            try:
                resp = requests.get(self.SEARCH_URL, params=params, timeout=self.timeout)
                return ApiResult(request_details, resp.status_code, self._safe_json(resp))
            except requests.RequestException as exc:
                return ApiResult(request_details, None, {}, error=str(exc))


# ---------------------------------------------------------------------------
# Platform registry
# ---------------------------------------------------------------------------

PLATFORM_MODES: Dict[str, List[str]] = {
    "X (Twitter)": ["Post", "Profile"],
    "Reddit": ["Post", "Profile"],
    "Instagram": ["Post", "Profile"],
    "TikTok": ["Post", "Profile", "Hashtag"],
    "YouTube": ["Post", "Profile"],
    "OpenAI": ["Generate"],
    "Gemini": ["Generate"],
    "NIH PubMed": ["Search"],
    "ClinicalTrials.gov": ["Search"],
    "Crossref": ["Search"],
    "Wikipedia": ["Search", "Summary"],
}

NO_KEY_PLATFORMS = {"NIH PubMed", "ClinicalTrials.gov", "Crossref", "Wikipedia"}


def run_search(platform: str, search_mode: str, query: str, max_results: int) -> ApiResult:
    clients: Dict[str, BaseClient] = {
        "X (Twitter)": TwitterClient(),
        "Reddit": RedditClient(),
        "Instagram": InstagramClient(),
        "TikTok": TikTokClient(),
        "YouTube": YouTubeClient(),
        "OpenAI": OpenAIClient(),
        "Gemini": GeminiClient(),
        "NIH PubMed": PubMedClient(),
        "ClinicalTrials.gov": ClinicalTrialsClient(),
        "Crossref": CrossrefClient(),
        "Wikipedia": WikipediaClient(),
    }
    return clients[platform].search(search_mode.lower(), query, max_results)


# ---------------------------------------------------------------------------
# Streamlit UI
# ---------------------------------------------------------------------------

PLATFORM_ICONS: Dict[str, str] = {
    "X (Twitter)": "𝕏",
    "Reddit": "🟠",
    "Instagram": "📸",
    "TikTok": "🎵",
    "YouTube": "▶",
    "OpenAI": "✦",
    "Gemini": "✦",
    "NIH PubMed": "🔬",
    "ClinicalTrials.gov": "🏥",
    "Crossref": "📚",
    "Wikipedia": "📖",
}

st.set_page_config(page_title="Social Connector", layout="wide", page_icon="⚡")

st.markdown("""
<style>
/* ── Global ── */
[data-testid="stAppViewContainer"] { background: #0f1117; }
[data-testid="stSidebar"] { background: #161b27; border-right: 1px solid #1f2937; }
[data-testid="stSidebar"] * { color: #e2e8f0 !important; }

/* ── Hide default Streamlit chrome ── */
#MainMenu, footer, header { visibility: hidden; }

/* ── Typography ── */
h1, h2, h3 { font-family: "Inter", "Segoe UI", sans-serif !important; }

/* ── Sidebar labels ── */
.sidebar-section-label {
    font-size: 10px;
    font-weight: 700;
    letter-spacing: 0.12em;
    text-transform: uppercase;
    color: #4b5563 !important;
    margin: 18px 0 6px 0;
}

/* ── Panel cards ── */
.panel-card {
    background: #161b27;
    border: 1px solid #1f2937;
    border-radius: 12px;
    padding: 20px 22px;
    height: 100%;
}
.panel-title {
    font-size: 11px;
    font-weight: 700;
    letter-spacing: 0.1em;
    text-transform: uppercase;
    color: #6b7280;
    margin-bottom: 14px;
    display: flex;
    align-items: center;
    gap: 7px;
}
.panel-dot {
    width: 7px; height: 7px;
    border-radius: 50%;
    display: inline-block;
}
.dot-request  { background: #3b82f6; }
.dot-response { background: #10b981; }

/* ── Status badge ── */
.status-badge {
    display: inline-flex;
    align-items: center;
    gap: 6px;
    font-size: 12px;
    font-weight: 600;
    padding: 3px 10px;
    border-radius: 20px;
    margin-bottom: 14px;
    font-family: "JetBrains Mono", "Fira Code", monospace;
}
.status-2xx { background: #052e16; color: #34d399; border: 1px solid #065f46; }
.status-3xx { background: #1c1917; color: #fbbf24; border: 1px solid #78350f; }
.status-4xx { background: #2d0e0e; color: #f87171; border: 1px solid #7f1d1d; }
.status-5xx { background: #2d0e0e; color: #f87171; border: 1px solid #7f1d1d; }
.status-none { background: #1a1f2e; color: #9ca3af; border: 1px solid #374151; }

/* ── Empty state ── */
.empty-state {
    display: flex;
    flex-direction: column;
    align-items: center;
    justify-content: center;
    padding: 80px 24px;
    text-align: center;
    background: #161b27;
    border: 1px dashed #1f2937;
    border-radius: 16px;
    margin-top: 8px;
}
.empty-state-icon { font-size: 40px; margin-bottom: 16px; opacity: 0.5; }
.empty-state-title { font-size: 16px; font-weight: 600; color: #6b7280; margin-bottom: 6px; }
.empty-state-sub   { font-size: 13px; color: #374151; }

/* ── No-key pill ── */
.nokey-pill {
    display: inline-block;
    font-size: 9px;
    font-weight: 700;
    letter-spacing: 0.08em;
    text-transform: uppercase;
    background: #052e16;
    color: #34d399;
    border: 1px solid #065f46;
    border-radius: 4px;
    padding: 1px 5px;
    vertical-align: middle;
    margin-left: 4px;
}

/* ── Header ── */
.app-header {
    display: flex;
    align-items: center;
    gap: 14px;
    padding: 6px 0 28px 0;
    border-bottom: 1px solid #1f2937;
    margin-bottom: 28px;
}
.app-header-icon {
    width: 40px; height: 40px;
    background: linear-gradient(135deg, #3b82f6, #8b5cf6);
    border-radius: 10px;
    display: flex; align-items: center; justify-content: center;
    font-size: 20px;
}
.app-header-title { font-size: 22px; font-weight: 700; color: #f1f5f9; margin: 0; }
.app-header-sub   { font-size: 13px; color: #6b7280; margin: 0; }
.connector-count  {
    margin-left: auto;
    background: #1f2937;
    border: 1px solid #374151;
    border-radius: 20px;
    padding: 4px 14px;
    font-size: 12px;
    font-weight: 600;
    color: #9ca3af;
}

/* ── Sidebar send button ── */
[data-testid="stButton"] > button {
    width: 100%;
    background: linear-gradient(135deg, #3b82f6, #8b5cf6) !important;
    color: white !important;
    border: none !important;
    border-radius: 8px !important;
    font-weight: 600 !important;
    font-size: 14px !important;
    padding: 10px !important;
    margin-top: 8px;
    transition: opacity 0.2s;
}
[data-testid="stButton"] > button:hover { opacity: 0.88 !important; }

/* ── Stcode blocks ── */
[data-testid="stCode"] { border-radius: 8px !important; border: 1px solid #1f2937 !important; }
</style>
""", unsafe_allow_html=True)

# ── Header ──────────────────────────────────────────────────────────────────
st.markdown("""
<div class="app-header">
  <div class="app-header-icon">⚡</div>
  <div>
    <p class="app-header-title">Social Connector</p>
    <p class="app-header-sub">Inspect live API requests &amp; responses across 11 platforms</p>
  </div>
  <div class="connector-count">11 connectors</div>
</div>
""", unsafe_allow_html=True)

# ── Sidebar ──────────────────────────────────────────────────────────────────
with st.sidebar:
    st.markdown("""
    <div style="padding: 18px 0 10px 0;">
      <p style="font-size:18px; font-weight:700; color:#f1f5f9; margin:0;">Configuration</p>
      <p style="font-size:12px; color:#6b7280; margin:4px 0 0 0;">Select a connector and run a query</p>
    </div>
    """, unsafe_allow_html=True)

    st.markdown('<p class="sidebar-section-label">Platform</p>', unsafe_allow_html=True)

    def _fmt(p: str) -> str:
        icon = PLATFORM_ICONS.get(p, "")
        tag = " ★" if p in NO_KEY_PLATFORMS else ""
        return f"{icon}  {p}{tag}"

    platform = st.selectbox(
        "Platform",
        list(PLATFORM_MODES.keys()),
        format_func=_fmt,
        label_visibility="collapsed",
    )

    if platform in NO_KEY_PLATFORMS:
        st.markdown(
            f'<p style="font-size:12px; color:#34d399; margin:-4px 0 8px 0;">'
            f'✓ No API key required</p>',
            unsafe_allow_html=True,
        )
    else:
        st.markdown(
            f'<p style="font-size:12px; color:#6b7280; margin:-4px 0 8px 0;">'
            f'🔑 API key required</p>',
            unsafe_allow_html=True,
        )

    st.markdown('<p class="sidebar-section-label">Mode</p>', unsafe_allow_html=True)
    available_modes = PLATFORM_MODES[platform]
    mode = st.radio("Mode", available_modes, label_visibility="collapsed", horizontal=True)

    st.markdown('<p class="sidebar-section-label">Query</p>', unsafe_allow_html=True)
    if platform in {"OpenAI", "Gemini"}:
        query_placeholder = "Enter your prompt…"
    elif platform in NO_KEY_PLATFORMS:
        query_placeholder = "e.g. mRNA vaccine outcomes"
    else:
        query_placeholder = "keyword, @username, or #hashtag"

    query = st.text_input("Query", placeholder=query_placeholder, label_visibility="collapsed")

    st.markdown('<p class="sidebar-section-label">Max results</p>', unsafe_allow_html=True)
    max_results = st.slider("Max results", min_value=1, max_value=50, value=10, label_visibility="collapsed")

    st.markdown("<br>", unsafe_allow_html=True)
    submit = st.button("⚡  Send Request", type="primary")

    st.markdown("""
    <div style="margin-top: 32px; padding-top: 16px; border-top: 1px solid #1f2937;">
      <p class="sidebar-section-label">No-key connectors</p>
      <p style="font-size:12px; color:#6b7280; line-height:1.7;">
        NIH PubMed · ClinicalTrials.gov<br>Crossref · Wikipedia
      </p>
    </div>
    """, unsafe_allow_html=True)

# ── Main content ─────────────────────────────────────────────────────────────
if submit:
    with st.spinner("Sending request…"):
        result = run_search(platform, mode, query, max_results)

    if result.error:
        st.markdown(f"""
        <div style="background:#2d0e0e; border:1px solid #7f1d1d; border-radius:10px;
                    padding:14px 18px; margin-bottom:20px; color:#f87171; font-size:14px;">
          <strong>Error:</strong> {result.error}
        </div>""", unsafe_allow_html=True)

    left, right = st.columns(2, gap="medium")

    with left:
        st.markdown("""
        <div class="panel-title">
          <span class="panel-dot dot-request"></span> Request
        </div>""", unsafe_allow_html=True)
        st.code(json.dumps(result.request_details, indent=2), language="json")

    with right:
        # Status badge
        code = result.status_code
        if code is None:
            badge_cls, label = "status-none", "No response"
        elif code < 300:
            badge_cls, label = "status-2xx", f"{code} OK"
        elif code < 400:
            badge_cls, label = "status-3xx", f"{code} Redirect"
        elif code < 500:
            badge_cls, label = "status-4xx", f"{code} Client Error"
        else:
            badge_cls, label = "status-5xx", f"{code} Server Error"

        st.markdown(f"""
        <div class="panel-title">
          <span class="panel-dot dot-response"></span> Response
        </div>
        <span class="status-badge {badge_cls}">{label}</span>
        """, unsafe_allow_html=True)

        if isinstance(result.response_body, (dict, list)):
            st.json(result.response_body)
        else:
            st.code(str(result.response_body))

else:
    icon = PLATFORM_ICONS.get(platform, "⚡")
    st.markdown(f"""
    <div class="empty-state">
      <div class="empty-state-icon">{icon}</div>
      <p class="empty-state-title">Ready to connect to {platform}</p>
      <p class="empty-state-sub">Configure your query in the sidebar and click <strong style="color:#9ca3af">Send Request</strong>.</p>
    </div>
    """, unsafe_allow_html=True)

with st.expander("Setup & credentials reference"):
    st.markdown("""
**Quick start**
```bash
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env   # fill in your keys
streamlit run app.py
```

| Platform | Environment variable(s) | Key needed? |
|---|---|:---:|
| X (Twitter) | `TWITTER_BEARER_TOKEN` | ✓ |
| Reddit | `REDDIT_CLIENT_ID`, `REDDIT_CLIENT_SECRET` | ✓ |
| Instagram | `INSTAGRAM_ACCESS_TOKEN` | ✓ |
| TikTok | `TIKTOK_ACCESS_TOKEN` | ✓ |
| YouTube | `YOUTUBE_API_KEY` | ✓ |
| OpenAI | `OPENAI_API_KEY` | ✓ |
| Gemini | `GEMINI_API_KEY` | ✓ |
| NIH PubMed | — | No |
| ClinicalTrials.gov | — | No |
| Crossref | — | No |
| Wikipedia | — | No |
    """)
