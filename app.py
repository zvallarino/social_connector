import json
import os
from dataclasses import dataclass
from typing import Any, Dict, Optional

import requests
import streamlit as st
from dotenv import load_dotenv

load_dotenv()


@dataclass
class ConnectorResult:
    request_details: Dict[str, Any]
    status_code: Optional[int]
    response_body: Any
    error: Optional[str] = None


class HttpConnector:
    timeout = 30

    @staticmethod
    def _safe_json(response: requests.Response) -> Any:
        try:
            return response.json()
        except ValueError:
            return response.text

    def execute(
        self,
        method: str,
        url: str,
        *,
        params: Optional[Dict[str, Any]] = None,
        json_body: Optional[Dict[str, Any]] = None,
        headers: Optional[Dict[str, str]] = None,
        redacted_request: Optional[Dict[str, Any]] = None,
    ) -> ConnectorResult:
        request_details = redacted_request or {
            "method": method,
            "url": url,
            "params": params or {},
            "json": json_body or {},
            "headers": headers or {},
        }

        try:
            response = requests.request(
                method,
                url,
                params=params,
                json=json_body,
                headers=headers,
                timeout=self.timeout,
            )
            return ConnectorResult(request_details, response.status_code, self._safe_json(response))
        except requests.RequestException as exc:
            return ConnectorResult(request_details, None, {}, error=str(exc))


def redacted_auth_header(token: str) -> Dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


def connector_configs() -> Dict[str, Dict[str, Any]]:
    return {
        "NIH PubMed (No key)": {
            "search_modes": ["post", "profile"],
            "auth": "none",
            "handler": lambda query, max_results, mode: {
                "method": "GET",
                "url": "https://eutils.ncbi.nlm.nih.gov/entrez/eutils/esearch.fcgi",
                "params": {
                    "db": "pubmed",
                    "term": query or "biomedical research",
                    "retmode": "json",
                    "retmax": max_results,
                },
            },
            "notes": "Fast keyless test endpoint for biomedical literature search.",
        },
        "ClinicalTrials.gov (No key)": {
            "search_modes": ["post", "profile"],
            "auth": "none",
            "handler": lambda query, max_results, mode: {
                "method": "GET",
                "url": "https://clinicaltrials.gov/api/v2/studies",
                "params": {
                    "query.term": query or "cancer",
                    "pageSize": max_results,
                },
            },
            "notes": "Useful for trial discovery and sanity-checking connector health.",
        },
        "Crossref (No key)": {
            "search_modes": ["post", "profile"],
            "auth": "none",
            "handler": lambda query, max_results, mode: {
                "method": "GET",
                "url": "https://api.crossref.org/works",
                "params": {
                    "query": query or "global health",
                    "rows": max_results,
                },
            },
            "notes": "Good keyless fallback for publication metadata testing.",
        },
        "Wikipedia (No key)": {
            "search_modes": ["post", "profile"],
            "auth": "none",
            "handler": lambda query, max_results, mode: {
                "method": "GET",
                "url": "https://en.wikipedia.org/w/api.php",
                "params": {
                    "action": "query",
                    "list": "search",
                    "format": "json",
                    "srlimit": max_results,
                    "srsearch": query or "population health",
                },
            },
            "notes": "Handy for API smoke tests with no credentials.",
        },
        "YouTube": {
            "search_modes": ["post", "profile"],
            "auth": "api_key:YOUTUBE_API_KEY",
            "handler": lambda query, max_results, mode: {
                "method": "GET",
                "url": "https://www.googleapis.com/youtube/v3/search",
                "params": {
                    "part": "snippet",
                    "q": query,
                    "type": "video" if mode == "post" else "channel",
                    "maxResults": max_results,
                    "key": os.getenv("YOUTUBE_API_KEY", ""),
                },
                "redacted": {
                    "method": "GET",
                    "url": "https://www.googleapis.com/youtube/v3/search",
                    "params": {
                        "part": "snippet",
                        "q": query,
                        "type": "video" if mode == "post" else "channel",
                        "maxResults": max_results,
                        "key": "***redacted***",
                    },
                },
            },
            "notes": "Official Data API; key required.",
        },
        "Reddit": {
            "search_modes": ["post", "profile"],
            "auth": "oauth:REDDIT_ACCESS_TOKEN",
            "handler": lambda query, max_results, mode: {
                "method": "GET",
                "url": "https://oauth.reddit.com/search" if mode == "post" else "https://oauth.reddit.com/users/search",
                "params": {
                    "q": query,
                    "limit": max_results,
                    "sort": "new",
                },
                "headers": {
                    "Authorization": f"Bearer {os.getenv('REDDIT_ACCESS_TOKEN', '')}",
                    "User-Agent": os.getenv("REDDIT_USER_AGENT", "social-connector/0.1"),
                },
                "redacted": {
                    "method": "GET",
                    "url": "https://oauth.reddit.com/search" if mode == "post" else "https://oauth.reddit.com/users/search",
                    "params": {
                        "q": query,
                        "limit": max_results,
                        "sort": "new",
                    },
                    "headers": {
                        "Authorization": "Bearer ***redacted***",
                        "User-Agent": os.getenv("REDDIT_USER_AGENT", "social-connector/0.1"),
                    },
                },
            },
            "notes": "Use script app OAuth token + user-agent.",
        },
        "Instagram": {
            "search_modes": ["post", "profile"],
            "auth": "oauth:INSTAGRAM_ACCESS_TOKEN",
            "handler": lambda query, max_results, mode: {
                "method": "GET",
                "url": "https://graph.instagram.com/me" if mode == "profile" else "https://graph.instagram.com/me/media",
                "params": (
                    {
                        "fields": "id,username,account_type,media_count",
                        "access_token": os.getenv("INSTAGRAM_ACCESS_TOKEN", ""),
                    }
                    if mode == "profile"
                    else {
                        "fields": "id,caption,media_type,media_url,permalink,timestamp",
                        "limit": max_results,
                        "access_token": os.getenv("INSTAGRAM_ACCESS_TOKEN", ""),
                    }
                ),
                "redacted": {
                    "method": "GET",
                    "url": "https://graph.instagram.com/me" if mode == "profile" else "https://graph.instagram.com/me/media",
                    "params": (
                        {
                            "fields": "id,username,account_type,media_count",
                            "access_token": "***redacted***",
                        }
                        if mode == "profile"
                        else {
                            "fields": "id,caption,media_type,media_url,permalink,timestamp",
                            "limit": max_results,
                            "access_token": "***redacted***",
                        }
                    ),
                },
            },
            "notes": "Basic Display is usually scoped to authenticated account data.",
        },
        "TikTok": {
            "search_modes": ["post", "profile", "hashtag"],
            "auth": "oauth:TIKTOK_ACCESS_TOKEN",
            "handler": lambda query, max_results, mode: {
                "method": "POST",
                "url": f"{os.getenv('TIKTOK_API_BASE', 'https://open.tiktokapis.com')}/v2/research/video/query/",
                "headers": {
                    "Authorization": f"Bearer {os.getenv('TIKTOK_ACCESS_TOKEN', '')}",
                    "Content-Type": "application/json",
                },
                "json": {
                    "max_count": max_results,
                    "query": {
                        "and": [
                            {
                                "operation": "IN" if mode == "hashtag" else "EQ",
                                "field_name": "hashtag_name" if mode == "hashtag" else "keyword",
                                "field_values": (
                                    [token.strip().lstrip("#") for token in query.split() if token.strip()]
                                    if mode == "hashtag"
                                    else [query]
                                ),
                            }
                        ]
                    },
                },
                "redacted": {
                    "method": "POST",
                    "url": f"{os.getenv('TIKTOK_API_BASE', 'https://open.tiktokapis.com')}/v2/research/video/query/",
                    "headers": {
                        "Authorization": "Bearer ***redacted***",
                        "Content-Type": "application/json",
                    },
                    "json": {
                        "max_count": max_results,
                        "query": {
                            "and": [
                                {
                                    "operation": "IN" if mode == "hashtag" else "EQ",
                                    "field_name": "hashtag_name" if mode == "hashtag" else "keyword",
                                    "field_values": (
                                        [token.strip().lstrip("#") for token in query.split() if token.strip()]
                                        if mode == "hashtag"
                                        else [query]
                                    ),
                                }
                            ]
                        },
                    },
                },
            },
            "notes": "Research APIs vary by access tier.",
        },
        "X (Twitter)": {
            "search_modes": ["post", "profile"],
            "auth": "oauth:X_BEARER_TOKEN",
            "handler": lambda query, max_results, mode: {
                "method": "GET",
                "url": "https://api.twitter.com/2/tweets/search/recent" if mode == "post" else "https://api.twitter.com/2/users/by",
                "params": (
                    {
                        "query": query,
                        "max_results": min(max_results, 100),
                    }
                    if mode == "post"
                    else {
                        "usernames": query,
                    }
                ),
                "headers": redacted_auth_header(os.getenv("X_BEARER_TOKEN", "")),
                "redacted": {
                    "method": "GET",
                    "url": "https://api.twitter.com/2/tweets/search/recent" if mode == "post" else "https://api.twitter.com/2/users/by",
                    "params": (
                        {
                            "query": query,
                            "max_results": min(max_results, 100),
                        }
                        if mode == "post"
                        else {
                            "usernames": query,
                        }
                    ),
                    "headers": {"Authorization": "Bearer ***redacted***"},
                },
            },
            "notes": "Twitter/X v2 bearer token required.",
        },
        "OpenAI": {
            "search_modes": ["post", "profile"],
            "auth": "oauth:OPENAI_API_KEY",
            "handler": lambda query, max_results, mode: {
                "method": "POST",
                "url": "https://api.openai.com/v1/responses",
                "headers": {
                    "Authorization": f"Bearer {os.getenv('OPENAI_API_KEY', '')}",
                    "Content-Type": "application/json",
                },
                "json": {
                    "model": os.getenv("OPENAI_MODEL", "gpt-4.1-mini"),
                    "input": query or "Hello from Social Connector",
                },
                "redacted": {
                    "method": "POST",
                    "url": "https://api.openai.com/v1/responses",
                    "headers": {
                        "Authorization": "Bearer ***redacted***",
                        "Content-Type": "application/json",
                    },
                    "json": {
                        "model": os.getenv("OPENAI_MODEL", "gpt-4.1-mini"),
                        "input": query or "Hello from Social Connector",
                    },
                },
            },
            "notes": "Simple connectivity check using Responses API.",
        },
        "Gemini": {
            "search_modes": ["post", "profile"],
            "auth": "api_key:GEMINI_API_KEY",
            "handler": lambda query, max_results, mode: {
                "method": "POST",
                "url": (
                    "https://generativelanguage.googleapis.com/v1beta/models/"
                    f"{os.getenv('GEMINI_MODEL', 'gemini-1.5-flash')}:generateContent"
                ),
                "params": {"key": os.getenv("GEMINI_API_KEY", "")},
                "json": {
                    "contents": [
                        {
                            "parts": [
                                {"text": query or "Hello from Social Connector"},
                            ]
                        }
                    ]
                },
                "redacted": {
                    "method": "POST",
                    "url": (
                        "https://generativelanguage.googleapis.com/v1beta/models/"
                        f"{os.getenv('GEMINI_MODEL', 'gemini-1.5-flash')}:generateContent"
                    ),
                    "params": {"key": "***redacted***"},
                    "json": {
                        "contents": [{"parts": [{"text": query or "Hello from Social Connector"}]}]
                    },
                },
            },
            "notes": "Gemini API key required.",
        },
    }


def require_auth(config: Dict[str, Any]) -> Optional[str]:
    auth_config = config.get("auth", "none")
    if auth_config == "none":
        return None

    _, env_var = auth_config.split(":", maxsplit=1)
    if not os.getenv(env_var):
        return f"Missing `{env_var}` in your environment/.env file."
    return None


def run_connector(connector: str, mode: str, query: str, max_results: int) -> ConnectorResult:
    config = connector_configs()[connector]
    auth_error = require_auth(config)
    if auth_error:
        return ConnectorResult({}, None, {}, error=auth_error)

    payload = config["handler"](query, max_results, mode)
    client = HttpConnector()
    return client.execute(
        payload["method"],
        payload["url"],
        params=payload.get("params"),
        json_body=payload.get("json"),
        headers=payload.get("headers"),
        redacted_request=payload.get("redacted"),
    )


def keyless_connectors() -> list[str]:
    return [name for name, cfg in connector_configs().items() if cfg.get("auth") == "none"]


st.set_page_config(page_title="Social Connector", layout="wide")
st.title("Social Connector — API Troubleshooting Console")
st.caption("Choose a connector and compare exact outbound request details with inbound response payload.")

configs = connector_configs()

with st.sidebar:
    st.header("Connector settings")
    connector = st.selectbox("Connector", list(configs.keys()))
    mode = st.radio("Search type", [m.title() for m in configs[connector]["search_modes"]])
    query = st.text_input("Query / username / keyword", placeholder="cancer biomarkers")
    max_results = st.slider("Max results", min_value=1, max_value=50, value=10)
    send = st.button("Send request", type="primary")

st.info(f"Connector note: {configs[connector]['notes']}")
st.success("No-key testing connectors: " + ", ".join(keyless_connectors()))

if send:
    result = run_connector(connector, mode.lower(), query, max_results)

    if result.error:
        st.error(result.error)

    left, right = st.columns(2)
    with left:
        st.subheader("What it's sending")
        st.code(json.dumps(result.request_details, indent=2), language="json")

    with right:
        st.subheader("What it's getting back")
        st.write(f"Status code: `{result.status_code}`" if result.status_code else "No HTTP response status.")
        if isinstance(result.response_body, (dict, list)):
            st.json(result.response_body)
        else:
            st.code(str(result.response_body))
else:
    st.info("Pick a connector, set query/mode, and click **Send request**.")

with st.expander("Quick start"):
    st.markdown(
        """
```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env
streamlit run app.py
```
        """
    )
