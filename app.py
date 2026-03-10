import json
import os
from dataclasses import dataclass
from typing import Any, Dict, Optional

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


class YouTubeClient(BaseClient):
    BASE_URL = "https://www.googleapis.com/youtube/v3/search"

    def search(self, search_mode: str, query: str, max_results: int) -> ApiResult:
        api_key = os.getenv("YOUTUBE_API_KEY")
        if not api_key:
            return ApiResult(
                request_details={},
                status_code=None,
                response_body={},
                error="Missing YOUTUBE_API_KEY in environment.",
            )

        item_type = "video" if search_mode == "post" else "channel"
        params = {
            "part": "snippet",
            "q": query,
            "type": item_type,
            "maxResults": max_results,
            "key": api_key,
        }

        request_details = {
            "method": "GET",
            "url": self.BASE_URL,
            "params": {**params, "key": "***redacted***"},
        }

        try:
            response = requests.get(self.BASE_URL, params=params, timeout=self.timeout)
            return ApiResult(request_details, response.status_code, self._safe_json(response))
        except requests.RequestException as exc:
            return ApiResult(request_details, None, {}, error=str(exc))


class InstagramClient(BaseClient):
    BASE_URL = "https://graph.instagram.com"

    def search(self, search_mode: str, query: str, max_results: int) -> ApiResult:
        access_token = os.getenv("INSTAGRAM_ACCESS_TOKEN")
        if not access_token:
            return ApiResult(
                request_details={},
                status_code=None,
                response_body={},
                error="Missing INSTAGRAM_ACCESS_TOKEN in environment.",
            )

        if search_mode == "profile":
            endpoint = f"{self.BASE_URL}/me"
            params = {
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
            response = requests.get(endpoint, params=params, timeout=self.timeout)
            return ApiResult(request_details, response.status_code, self._safe_json(response))
        except requests.RequestException as exc:
            return ApiResult(request_details, None, {}, error=str(exc))


class TikTokClient(BaseClient):
    BASE_URL = os.getenv("TIKTOK_API_BASE", "https://open.tiktokapis.com")

    def search(self, search_mode: str, query: str, max_results: int) -> ApiResult:
        access_token = os.getenv("TIKTOK_ACCESS_TOKEN")
        if not access_token:
            return ApiResult(
                request_details={},
                status_code=None,
                response_body={},
                error="Missing TIKTOK_ACCESS_TOKEN in environment.",
            )

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
                "and": [
                    {
                        "operation": "EQ",
                        "field_name": "keyword",
                        "field_values": [query],
                    }
                ]
            }

        headers = {
            "Authorization": f"Bearer {access_token}",
            "Content-Type": "application/json",
        }

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
            response = requests.post(
                endpoint,
                headers=headers,
                json=payload,
                timeout=self.timeout,
            )
            return ApiResult(request_details, response.status_code, self._safe_json(response))
        except requests.RequestException as exc:
            return ApiResult(request_details, None, {}, error=str(exc))


def run_search(platform: str, search_mode: str, query: str, max_results: int) -> ApiResult:
    clients = {
        "YouTube": YouTubeClient(),
        "Instagram": InstagramClient(),
        "TikTok": TikTokClient(),
    }
    return clients[platform].search(search_mode.lower(), query, max_results)


st.set_page_config(page_title="Social Connector", layout="wide")
st.title("Social Connector — API Explorer")
st.caption(
    "Super-simple front page: pick a platform, choose search mode, and inspect request vs response."
)

with st.sidebar:
    st.header("Options")
    platform = st.selectbox("Choose API", ["Instagram", "YouTube", "TikTok"])

    available_modes = ["Post", "Profile"]
    if platform == "TikTok":
        available_modes.append("Hashtag")

    mode = st.radio("Search by", available_modes)
    query_help = "Required for YouTube and TikTok. Instagram may ignore free-text query for some endpoints."
    query = st.text_input("Query / username / keyword", placeholder="e.g. openai OR #ai", help=query_help)
    max_results = st.slider("Max results", min_value=1, max_value=50, value=10)

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
    st.info("Choose API + search mode, then click **Send request**.")

with st.expander("Setup checklist"):
    st.markdown(
        """
1. Create a Python virtual environment.
2. Install dependencies from `requirements.txt`.
3. Put credentials in `.env` (see `.env.example`).
4. Run `streamlit run app.py`.

**Tip:** For production scraping and broad discovery use-cases, consider API policy constraints and pagination/rate limiting.
        """
    )
