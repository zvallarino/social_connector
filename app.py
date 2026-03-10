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

st.set_page_config(page_title="Social Connector", layout="wide")
st.title("Social Connector — API Explorer")
st.caption(
    "Pick a platform, choose a search mode, and inspect the request vs response side-by-side."
)

with st.sidebar:
    st.header("Options")

    st.markdown("**Key-required connectors**")
    key_platforms = [p for p in PLATFORM_MODES if p not in NO_KEY_PLATFORMS]
    st.markdown("**No-key test connectors**")
    no_key_platforms = list(NO_KEY_PLATFORMS)

    platform = st.selectbox(
        "Choose API",
        list(PLATFORM_MODES.keys()),
        help="Platforms marked with ★ require no API key.",
        format_func=lambda p: f"★ {p}" if p in NO_KEY_PLATFORMS else p,
    )

    available_modes = PLATFORM_MODES[platform]
    mode = st.radio("Mode", available_modes)

    if platform in {"OpenAI", "Gemini"}:
        query_placeholder = "e.g. Explain transformer architecture in one paragraph"
        query_help = "Your prompt / message to the model."
    elif platform in NO_KEY_PLATFORMS:
        query_placeholder = "e.g. mRNA vaccine clinical outcomes"
        query_help = "Search term — no API key required."
    else:
        query_placeholder = "e.g. openai  OR  @elonmusk  OR  #ai"
        query_help = "Search query, username, or keyword depending on mode."

    query = st.text_input("Query / keyword / prompt", placeholder=query_placeholder, help=query_help)
    max_results = st.slider("Max results / tokens multiplier", min_value=1, max_value=50, value=10)

    submit = st.button("Send request", type="primary")

if submit:
    result = run_search(platform, mode, query, max_results)

    if result.error:
        st.error(result.error)

    left, right = st.columns(2)

    with left:
        st.subheader("What we're sending")
        st.code(json.dumps(result.request_details, indent=2), language="json")

    with right:
        st.subheader("What we're receiving")
        st.write(f"Status code: `{result.status_code}`" if result.status_code else "No HTTP response status.")
        if isinstance(result.response_body, (dict, list)):
            st.json(result.response_body)
        else:
            st.code(str(result.response_body))
else:
    st.info("Choose a platform + mode, enter a query, then click **Send request**.")

with st.expander("Setup checklist"):
    st.markdown(
        """
### Quick start
1. Create a Python virtual environment and activate it.
2. `pip install -r requirements.txt`
3. Copy `.env.example` → `.env` and fill in your credentials.
4. `streamlit run app.py`

### No-key test connectors (smoke-test without any credentials)
- **NIH PubMed** — NCBI E-utilities article search
- **ClinicalTrials.gov** — Study search via ClinicalTrials API v2
- **Crossref** — Academic works search
- **Wikipedia** — Full-text search + page summary

### Key-required connectors
| Platform | Environment variable(s) |
|---|---|
| X (Twitter) | `TWITTER_BEARER_TOKEN` |
| Reddit | `REDDIT_CLIENT_ID`, `REDDIT_CLIENT_SECRET` |
| Instagram | `INSTAGRAM_ACCESS_TOKEN` |
| TikTok | `TIKTOK_ACCESS_TOKEN` |
| YouTube | `YOUTUBE_API_KEY` |
| OpenAI | `OPENAI_API_KEY` |
| Gemini | `GEMINI_API_KEY` |

**Tip:** For production use, consider API policy constraints, pagination, and rate limiting.
        """
    )
