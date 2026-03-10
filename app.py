import io
import json
import os
import time
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, List, Optional

import pandas as pd
import requests
import streamlit as st
from dotenv import load_dotenv

load_dotenv()


# ---------------------------------------------------------------------------
# Data classes
# ---------------------------------------------------------------------------

@dataclass
class ApiResult:
    request_details: Dict[str, Any]
    status_code: Optional[int]
    response_body: Any
    error: Optional[str] = None
    records: List[Dict[str, Any]] = field(default_factory=list)


# ---------------------------------------------------------------------------
# Base client
# ---------------------------------------------------------------------------

class BaseClient:
    timeout = 30
    USER_AGENT = "SocialConnector/1.0 (research-tool)"

    def _default_headers(self) -> Dict[str, str]:
        return {"User-Agent": self.USER_AGENT}

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

        headers = {**self._default_headers(), "Authorization": f"Bearer {bearer_token}"}
        redacted_headers = {"Authorization": "Bearer ***redacted***"}

        if search_mode == "profile":
            username = query.lstrip("@")
            url = f"{self.BASE_URL}/users/by/username/{username}"
            params = {"user.fields": "name,username,description,public_metrics,created_at"}
            request_details = {"method": "GET", "url": url, "params": params, "headers": redacted_headers}
            try:
                resp = requests.get(url, params=params, headers=headers, timeout=self.timeout)
                body = self._safe_json(resp)
                records = [body.get("data")] if isinstance(body, dict) and body.get("data") else []
                return ApiResult(request_details, resp.status_code, body, records=records)
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
                body = self._safe_json(resp)
                records = body.get("data", []) if isinstance(body, dict) else []
                return ApiResult(request_details, resp.status_code, body, records=records)
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
            headers=self._default_headers(),
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

        headers = {**self._default_headers(), "Authorization": f"Bearer {token}"}
        redacted_headers = {"Authorization": "Bearer ***redacted***", "User-Agent": self.USER_AGENT}

        if search_mode == "profile":
            url = f"{self.BASE_URL}/user/{query}/about"
            params: Dict[str, Any] = {}
            request_details = {"method": "GET", "url": url, "params": params, "headers": redacted_headers}
            try:
                resp = requests.get(url, params=params, headers=headers, timeout=self.timeout)
                body = self._safe_json(resp)
                records = [body.get("data")] if isinstance(body, dict) and body.get("data") else []
                return ApiResult(request_details, resp.status_code, body, records=records)
            except requests.RequestException as exc:
                return ApiResult(request_details, None, {}, error=str(exc))
        else:
            url = f"{self.BASE_URL}/search"
            params = {"q": query, "limit": max_results, "type": "link", "sort": "relevance"}
            request_details = {"method": "GET", "url": url, "params": params, "headers": redacted_headers}
            try:
                resp = requests.get(url, params=params, headers=headers, timeout=self.timeout)
                body = self._safe_json(resp)
                children = body.get("data", {}).get("children", []) if isinstance(body, dict) else []
                records = [c.get("data", c) for c in children if isinstance(c, dict)]
                return ApiResult(request_details, resp.status_code, body, records=records)
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
        }
        try:
            resp = requests.get(endpoint, params=params, headers=self._default_headers(), timeout=self.timeout)
            body = self._safe_json(resp)
            records = body.get("data", [body]) if isinstance(body, dict) else []
            return ApiResult(request_details, resp.status_code, body, records=records)
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
                    {"operation": "IN", "field_name": "hashtag_name", "field_values": hashtags}
                ] if search_mode == "hashtag" and hashtags else []
            },
        }

        if search_mode in {"profile", "post"}:
            payload["query"] = {
                "and": [{"operation": "EQ", "field_name": "keyword", "field_values": [query]}]
            }

        headers = {**self._default_headers(), "Authorization": f"Bearer {access_token}", "Content-Type": "application/json"}
        request_details = {
            "method": "POST",
            "url": endpoint,
            "headers": {"Authorization": "Bearer ***redacted***", "Content-Type": "application/json"},
            "json": payload,
        }
        try:
            resp = requests.post(endpoint, headers=headers, json=payload, timeout=self.timeout)
            body = self._safe_json(resp)
            records = body.get("data", {}).get("videos", []) if isinstance(body, dict) else []
            return ApiResult(request_details, resp.status_code, body, records=records)
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
            resp = requests.get(self.BASE_URL, params=params, headers=self._default_headers(), timeout=self.timeout)
            body = self._safe_json(resp)
            records = body.get("items", []) if isinstance(body, dict) else []
            return ApiResult(request_details, resp.status_code, body, records=records)
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
        headers = {**self._default_headers(), "Authorization": f"Bearer {api_key}", "Content-Type": "application/json"}
        request_details = {
            "method": "POST",
            "url": self.BASE_URL,
            "headers": {"Authorization": "Bearer ***redacted***", "Content-Type": "application/json"},
            "json": payload,
        }
        try:
            resp = requests.post(self.BASE_URL, headers=headers, json=payload, timeout=self.timeout)
            body = self._safe_json(resp)
            records = body.get("choices", []) if isinstance(body, dict) else []
            return ApiResult(request_details, resp.status_code, body, records=records)
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
            resp = requests.post(url, json=payload, headers=self._default_headers(), timeout=self.timeout)
            body = self._safe_json(resp)
            records = body.get("candidates", []) if isinstance(body, dict) else []
            return ApiResult(request_details, resp.status_code, body, records=records)
        except requests.RequestException as exc:
            return ApiResult(request_details, None, {}, error=str(exc))


# ---------------------------------------------------------------------------
# NCBI E-utilities (NIH) – comprehensive client
# ---------------------------------------------------------------------------

NCBI_DATABASES = {
    "PubMed": {"db": "pubmed", "desc": "Biomedical literature citations"},
    "PMC": {"db": "pmc", "desc": "Full-text journal articles"},
    "Gene": {"db": "gene", "desc": "Gene records across species"},
    "Protein": {"db": "protein", "desc": "Protein sequences"},
    "Nucleotide": {"db": "nuccore", "desc": "Nucleotide sequences"},
    "SNP": {"db": "snp", "desc": "Single nucleotide polymorphisms"},
    "ClinVar": {"db": "clinvar", "desc": "Clinical significance of variants"},
    "MeSH": {"db": "mesh", "desc": "Medical Subject Headings vocabulary"},
    "OMIM": {"db": "omim", "desc": "Online Mendelian Inheritance in Man"},
    "Taxonomy": {"db": "taxonomy", "desc": "Organism classification"},
    "BioSample": {"db": "biosample", "desc": "Biological source materials"},
    "BioProject": {"db": "bioproject", "desc": "Biological projects"},
    "SRA": {"db": "sra", "desc": "Sequence Read Archive"},
    "Structure": {"db": "structure", "desc": "3D macromolecular structures"},
    "PubChem Compound": {"db": "pccompound", "desc": "Chemical compound records"},
    "PubChem Substance": {"db": "pcsubstance", "desc": "Chemical substance records"},
    "GEO Datasets": {"db": "gds", "desc": "Gene expression datasets"},
    "GEO Profiles": {"db": "geoprofiles", "desc": "Gene expression profiles"},
    "dbGaP": {"db": "gap", "desc": "Genotype and phenotype studies"},
    "Bookshelf": {"db": "books", "desc": "NCBI Bookshelf full-text books"},
}


class NCBIClient(BaseClient):
    ESEARCH_URL = "https://eutils.ncbi.nlm.nih.gov/entrez/eutils/esearch.fcgi"
    ESUMMARY_URL = "https://eutils.ncbi.nlm.nih.gov/entrez/eutils/esummary.fcgi"
    EINFO_URL = "https://eutils.ncbi.nlm.nih.gov/entrez/eutils/einfo.fcgi"
    EFETCH_URL = "https://eutils.ncbi.nlm.nih.gov/entrez/eutils/efetch.fcgi"
    ELINK_URL = "https://eutils.ncbi.nlm.nih.gov/entrez/eutils/elink.fcgi"
    ESPELL_URL = "https://eutils.ncbi.nlm.nih.gov/entrez/eutils/espell.fcgi"
    EGQUERY_URL = "https://eutils.ncbi.nlm.nih.gov/entrez/eutils/egquery.fcgi"

    BATCH_SIZE = 200
    REQUEST_DELAY = 0.4  # 3 requests/sec without API key

    def __init__(self, database: str = "pubmed"):
        self.database = database

    def search_with_summaries(self, query: str, max_results: int,
                              progress_callback: Optional[Callable] = None) -> ApiResult:
        """esearch to get IDs, then esummary in batches for full records."""
        esearch_params = {
            "db": self.database,
            "term": query,
            "retmode": "json",
            "retmax": min(max_results, 100000),
        }
        request_details = {
            "method": "GET",
            "urls": [self.ESEARCH_URL, self.ESUMMARY_URL],
            "esearch_params": esearch_params,
        }

        try:
            resp = requests.get(
                self.ESEARCH_URL, params=esearch_params,
                headers=self._default_headers(), timeout=self.timeout,
            )
            resp.raise_for_status()
            search_data = resp.json()

            id_list = search_data.get("esearchresult", {}).get("idlist", [])
            total_available = int(search_data.get("esearchresult", {}).get("count", 0))
            ids_to_fetch = id_list[:max_results]

            request_details["total_available"] = total_available
            request_details["ids_returned"] = len(ids_to_fetch)

            if not ids_to_fetch:
                return ApiResult(request_details, resp.status_code, search_data, records=[])

            # Fetch summaries in batches
            all_records: List[Dict[str, Any]] = []
            total_batches = max(1, (len(ids_to_fetch) + self.BATCH_SIZE - 1) // self.BATCH_SIZE)
            seen_ids: set = set()

            for batch_idx in range(total_batches):
                start = batch_idx * self.BATCH_SIZE
                end = min(start + self.BATCH_SIZE, len(ids_to_fetch))
                batch_ids = ids_to_fetch[start:end]

                if progress_callback:
                    progress_callback(
                        batch_idx, total_batches,
                        f"Fetching summaries: batch {batch_idx + 1} of {total_batches} "
                        f"({len(all_records)} records so far)"
                    )

                summary_params = {
                    "db": self.database,
                    "id": ",".join(batch_ids),
                    "retmode": "json",
                }
                summary_resp = requests.get(
                    self.ESUMMARY_URL, params=summary_params,
                    headers=self._default_headers(), timeout=self.timeout,
                )
                summary_data = summary_resp.json()
                result_block = summary_data.get("result", {})
                uids = result_block.get("uids", [])
                for uid in uids:
                    if uid in result_block and uid not in seen_ids:
                        seen_ids.add(uid)
                        record = dict(result_block[uid])
                        record["uid"] = uid
                        all_records.append(record)

                if batch_idx < total_batches - 1:
                    time.sleep(self.REQUEST_DELAY)

            if progress_callback:
                progress_callback(total_batches, total_batches, "Complete")

            request_details["total_fetched"] = len(all_records)
            request_details["batches"] = total_batches

            return ApiResult(
                request_details, resp.status_code,
                {"total_available": total_available, "total_fetched": len(all_records), "records": all_records},
                records=all_records,
            )
        except requests.RequestException as exc:
            return ApiResult(request_details, None, {}, error=str(exc))

    def search_ids(self, query: str, max_results: int) -> ApiResult:
        """esearch only – returns IDs."""
        params = {
            "db": self.database,
            "term": query,
            "retmode": "json",
            "retmax": max_results,
        }
        request_details = {"method": "GET", "url": self.ESEARCH_URL, "params": params}
        try:
            resp = requests.get(
                self.ESEARCH_URL, params=params,
                headers=self._default_headers(), timeout=self.timeout,
            )
            data = self._safe_json(resp)
            ids = data.get("esearchresult", {}).get("idlist", []) if isinstance(data, dict) else []
            records = [{"id": i} for i in ids]
            return ApiResult(request_details, resp.status_code, data, records=records)
        except requests.RequestException as exc:
            return ApiResult(request_details, None, {}, error=str(exc))

    def db_info(self) -> ApiResult:
        """einfo – database statistics and searchable fields."""
        params: Dict[str, Any] = {"db": self.database, "retmode": "json"}
        request_details = {"method": "GET", "url": self.EINFO_URL, "params": params}
        try:
            resp = requests.get(
                self.EINFO_URL, params=params,
                headers=self._default_headers(), timeout=self.timeout,
            )
            data = self._safe_json(resp)
            fields = []
            if isinstance(data, dict):
                db_info = data.get("einforesult", {}).get("dbinfo", {})
                if not db_info:
                    db_info = data.get("einforesult", [{}])[0] if isinstance(data.get("einforesult"), list) else {}
                fields = db_info.get("fieldlist", [])
                if isinstance(fields, list):
                    fields = [f if isinstance(f, dict) else {"name": f} for f in fields]
            return ApiResult(request_details, resp.status_code, data, records=fields)
        except requests.RequestException as exc:
            return ApiResult(request_details, None, {}, error=str(exc))

    def spell_check(self, query: str) -> ApiResult:
        """espell – suggest corrected spelling."""
        params: Dict[str, Any] = {"db": self.database, "term": query}
        request_details = {"method": "GET", "url": self.ESPELL_URL, "params": params}
        try:
            resp = requests.get(
                self.ESPELL_URL, params=params,
                headers=self._default_headers(), timeout=self.timeout,
            )
            return ApiResult(request_details, resp.status_code, resp.text)
        except requests.RequestException as exc:
            return ApiResult(request_details, None, {}, error=str(exc))

    def global_query(self, query: str) -> ApiResult:
        """egquery – search counts across all Entrez databases."""
        params: Dict[str, Any] = {"term": query, "retmode": "json"}
        request_details = {"method": "GET", "url": self.EGQUERY_URL, "params": params}
        try:
            resp = requests.get(
                self.EGQUERY_URL, params=params,
                headers=self._default_headers(), timeout=self.timeout,
            )
            data = self._safe_json(resp)
            records = []
            if isinstance(data, dict):
                eg = data.get("egqueryresult", {})
                records = eg.get("resultitem", []) if isinstance(eg, dict) else []
            return ApiResult(request_details, resp.status_code, data, records=records)
        except requests.RequestException as exc:
            return ApiResult(request_details, None, {}, error=str(exc))

    def fetch_details(self, query: str, max_results: int) -> ApiResult:
        """efetch – fetch full records (returns text/XML for most dbs)."""
        # First get IDs via esearch
        search_params = {
            "db": self.database,
            "term": query,
            "retmode": "json",
            "retmax": max_results,
        }
        try:
            search_resp = requests.get(
                self.ESEARCH_URL, params=search_params,
                headers=self._default_headers(), timeout=self.timeout,
            )
            search_data = search_resp.json()
            id_list = search_data.get("esearchresult", {}).get("idlist", [])

            if not id_list:
                return ApiResult(
                    {"method": "GET", "url": self.ESEARCH_URL, "params": search_params},
                    search_resp.status_code, search_data, records=[],
                )

            fetch_params: Dict[str, Any] = {
                "db": self.database,
                "id": ",".join(id_list[:max_results]),
                "retmode": "xml",
            }
            request_details = {
                "method": "GET",
                "url": self.EFETCH_URL,
                "params": fetch_params,
                "note": "efetch returns XML for most databases",
            }
            resp = requests.get(
                self.EFETCH_URL, params=fetch_params,
                headers=self._default_headers(), timeout=self.timeout,
            )
            return ApiResult(request_details, resp.status_code, resp.text)
        except requests.RequestException as exc:
            return ApiResult(
                {"method": "GET", "url": self.EFETCH_URL},
                None, {}, error=str(exc),
            )

    def find_links(self, query: str, target_db: str, max_results: int) -> ApiResult:
        """elink – find related records in another database."""
        search_params = {
            "db": self.database,
            "term": query,
            "retmode": "json",
            "retmax": min(max_results, 20),
        }
        try:
            search_resp = requests.get(
                self.ESEARCH_URL, params=search_params,
                headers=self._default_headers(), timeout=self.timeout,
            )
            search_data = search_resp.json()
            id_list = search_data.get("esearchresult", {}).get("idlist", [])

            if not id_list:
                return ApiResult(
                    {"method": "GET", "url": self.ESEARCH_URL, "params": search_params},
                    search_resp.status_code, search_data, records=[],
                )

            link_params: Dict[str, Any] = {
                "dbfrom": self.database,
                "db": target_db,
                "id": ",".join(id_list),
                "retmode": "json",
            }
            request_details = {"method": "GET", "url": self.ELINK_URL, "params": link_params}
            resp = requests.get(
                self.ELINK_URL, params=link_params,
                headers=self._default_headers(), timeout=self.timeout,
            )
            data = self._safe_json(resp)
            records = []
            if isinstance(data, dict):
                linksets = data.get("linksets", [])
                records = linksets
            return ApiResult(request_details, resp.status_code, data, records=records)
        except requests.RequestException as exc:
            return ApiResult(
                {"method": "GET", "url": self.ELINK_URL},
                None, {}, error=str(exc),
            )


# ---------------------------------------------------------------------------
# NIH Reporter (grants & publications)
# ---------------------------------------------------------------------------

class NIHReporterClient(BaseClient):
    BASE_URL = "https://api.reporter.nih.gov/v2"
    BATCH_SIZE = 500
    REQUEST_DELAY = 0.5

    def search(self, search_mode: str, query: str, max_results: int,
               progress_callback: Optional[Callable] = None) -> ApiResult:
        endpoint = "publications" if search_mode == "publications" else "projects"
        url = f"{self.BASE_URL}/{endpoint}/search"

        search_field = "title,abstract" if endpoint == "publications" else "terms,projecttitle"
        all_records: List[Dict[str, Any]] = []
        offset = 0
        total: Optional[int] = None
        batch_num = 0
        seen_ids: set = set()

        try:
            while len(all_records) < max_results:
                batch_size = min(self.BATCH_SIZE, max_results - len(all_records))
                payload = {
                    "criteria": {
                        "advanced_text_search": {
                            "operator": "and",
                            "search_field": search_field,
                            "search_text": query,
                        }
                    },
                    "offset": offset,
                    "limit": batch_size,
                }

                resp = requests.post(
                    url, json=payload,
                    headers={**self._default_headers(), "Content-Type": "application/json"},
                    timeout=self.timeout,
                )
                data = resp.json()

                if total is None:
                    total = data.get("meta", {}).get("total", 0)

                results = data.get("results", [])
                if not results:
                    break

                for r in results:
                    rid = str(r.get("appl_id", "") or r.get("pmid", "") or id(r))
                    if rid not in seen_ids:
                        seen_ids.add(rid)
                        all_records.append(r)

                offset += batch_size
                batch_num += 1

                total_batches = max(1, (min(max_results, total or max_results) + batch_size - 1) // batch_size)
                if progress_callback:
                    progress_callback(
                        batch_num, total_batches,
                        f"Batch {batch_num} of {total_batches} ({len(all_records)} records)"
                    )

                if offset >= (total or 0):
                    break

                if len(all_records) < max_results:
                    time.sleep(self.REQUEST_DELAY)

            if progress_callback:
                progress_callback(1, 1, "Complete")

            return ApiResult(
                {
                    "method": "POST",
                    "url": url,
                    "total_available": total,
                    "total_fetched": len(all_records),
                    "batches": batch_num,
                },
                200,
                {"total_available": total, "records": all_records},
                records=all_records,
            )
        except requests.RequestException as exc:
            return ApiResult({"method": "POST", "url": url}, None, {}, error=str(exc))


# ---------------------------------------------------------------------------
# Other no-key connectors
# ---------------------------------------------------------------------------

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
            resp = requests.get(
                self.BASE_URL, params=params,
                headers=self._default_headers(), timeout=self.timeout,
            )
            body = self._safe_json(resp)
            records = body.get("studies", []) if isinstance(body, dict) else []
            return ApiResult(request_details, resp.status_code, body, records=records)
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
        headers = {**self._default_headers(), "Accept": "application/json"}
        request_details = {"method": "GET", "url": self.BASE_URL, "params": params}
        try:
            resp = requests.get(self.BASE_URL, params=params, headers=headers, timeout=self.timeout)
            body = self._safe_json(resp)
            records = body.get("message", {}).get("items", []) if isinstance(body, dict) else []
            return ApiResult(request_details, resp.status_code, body, records=records)
        except requests.RequestException as exc:
            return ApiResult(request_details, None, {}, error=str(exc))


class WikipediaClient(BaseClient):
    SEARCH_URL = "https://en.wikipedia.org/w/api.php"
    SUMMARY_URL = "https://en.wikipedia.org/api/rest_v1/page/summary"

    def search(self, search_mode: str, query: str, max_results: int) -> ApiResult:
        headers = self._default_headers()

        if search_mode == "summary":
            url = f"{self.SUMMARY_URL}/{requests.utils.quote(query)}"
            request_details = {"method": "GET", "url": url, "headers": {"User-Agent": self.USER_AGENT}}
            try:
                resp = requests.get(url, headers=headers, timeout=self.timeout)
                body = self._safe_json(resp)
                records = [body] if isinstance(body, dict) else []
                return ApiResult(request_details, resp.status_code, body, records=records)
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
            request_details = {
                "method": "GET",
                "url": self.SEARCH_URL,
                "params": params,
                "headers": {"User-Agent": self.USER_AGENT},
            }
            try:
                resp = requests.get(self.SEARCH_URL, params=params, headers=headers, timeout=self.timeout)
                body = self._safe_json(resp)
                records = body.get("query", {}).get("search", []) if isinstance(body, dict) else []
                return ApiResult(request_details, resp.status_code, body, records=records)
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
    "NIH (NCBI)": ["Search", "Fetch IDs", "Database Info", "Fetch Details (XML)", "Spell Check", "Global Query", "Find Links"],
    "NIH Reporter": ["Projects", "Publications"],
    "ClinicalTrials.gov": ["Search"],
    "Crossref": ["Search"],
    "Wikipedia": ["Search", "Summary"],
}

NO_KEY_PLATFORMS = {"NIH (NCBI)", "NIH Reporter", "ClinicalTrials.gov", "Crossref", "Wikipedia"}

PLATFORM_ICONS: Dict[str, str] = {
    "X (Twitter)": "𝕏",
    "Reddit": "🟠",
    "Instagram": "📸",
    "TikTok": "🎵",
    "YouTube": "▶",
    "OpenAI": "✦",
    "Gemini": "✦",
    "NIH (NCBI)": "🔬",
    "NIH Reporter": "📊",
    "ClinicalTrials.gov": "🏥",
    "Crossref": "📚",
    "Wikipedia": "📖",
}


def run_search(platform: str, search_mode: str, query: str, max_results: int) -> ApiResult:
    """Run a simple (non-paginated) search for standard connectors."""
    clients: Dict[str, BaseClient] = {
        "X (Twitter)": TwitterClient(),
        "Reddit": RedditClient(),
        "Instagram": InstagramClient(),
        "TikTok": TikTokClient(),
        "YouTube": YouTubeClient(),
        "OpenAI": OpenAIClient(),
        "Gemini": GeminiClient(),
        "ClinicalTrials.gov": ClinicalTrialsClient(),
        "Crossref": CrossrefClient(),
        "Wikipedia": WikipediaClient(),
    }
    return clients[platform].search(search_mode.lower(), query, max_results)


# ---------------------------------------------------------------------------
# Export helpers
# ---------------------------------------------------------------------------

def flatten_record(record: Dict[str, Any], parent_key: str = "", sep: str = ".") -> Dict[str, Any]:
    """Flatten nested dicts for tabular export."""
    items: List[tuple] = []
    for k, v in record.items():
        new_key = f"{parent_key}{sep}{k}" if parent_key else k
        if isinstance(v, dict):
            items.extend(flatten_record(v, new_key, sep).items())
        elif isinstance(v, list):
            items.append((new_key, json.dumps(v, default=str)))
        else:
            items.append((new_key, v))
    return dict(items)


def records_to_excel(records: List[Dict], selected_keys: List[str]) -> bytes:
    """Convert records to Excel bytes, including only selected keys."""
    rows = []
    for record in records:
        flat = flatten_record(record) if isinstance(record, dict) else {"value": record}
        row = {k: flat.get(k, "") for k in selected_keys}
        rows.append(row)
    df = pd.DataFrame(rows)
    buffer = io.BytesIO()
    df.to_excel(buffer, index=False, engine="openpyxl")
    return buffer.getvalue()


def records_to_json(records: List[Dict], selected_keys: List[str]) -> str:
    """Convert records to JSON string, including only selected keys."""
    filtered = []
    for record in records:
        flat = flatten_record(record) if isinstance(record, dict) else {"value": record}
        filtered.append({k: flat.get(k, "") for k in selected_keys})
    return json.dumps(filtered, indent=2, default=str)


def extract_all_keys(records: List[Dict]) -> List[str]:
    """Get all unique keys from a list of records (flattened)."""
    keys: set = set()
    for record in records:
        if isinstance(record, dict):
            flat = flatten_record(record)
            keys.update(flat.keys())
    return sorted(keys)


# ---------------------------------------------------------------------------
# Streamlit UI
# ---------------------------------------------------------------------------

st.set_page_config(page_title="Social Connector", layout="wide", page_icon="⚡")

st.markdown("""
<style>
/* ── Global reset ── */
[data-testid="stAppViewContainer"] { background: #0d1117; }
[data-testid="stSidebar"] { background: #161b22; border-right: 1px solid #30363d; }
[data-testid="stSidebar"] * { color: #c9d1d9 !important; }

/* ── Hide default chrome ── */
#MainMenu, footer, header { visibility: hidden; }

/* ── Typography ── */
html, body, [class*="css"] {
    font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Helvetica, Arial, sans-serif;
}
h1, h2, h3 {
    font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Helvetica, Arial, sans-serif !important;
    color: #e6edf3 !important;
}

/* ── Sidebar labels ── */
.sidebar-label {
    font-size: 12px;
    font-weight: 600;
    color: #8b949e !important;
    margin: 16px 0 4px 0;
    text-transform: uppercase;
    letter-spacing: 0.05em;
}

/* ── Panel cards ── */
.panel-card {
    background: #161b22;
    border: 1px solid #30363d;
    border-radius: 6px;
    padding: 16px 18px;
}
.panel-title {
    font-size: 12px;
    font-weight: 600;
    color: #8b949e;
    margin-bottom: 12px;
    display: flex;
    align-items: center;
    gap: 6px;
    text-transform: uppercase;
    letter-spacing: 0.04em;
}
.panel-dot {
    width: 8px; height: 8px;
    border-radius: 50%;
    display: inline-block;
}
.dot-request  { background: #58a6ff; }
.dot-response { background: #3fb950; }

/* ── Status badges ── */
.status-badge {
    display: inline-flex;
    align-items: center;
    gap: 5px;
    font-size: 12px;
    font-weight: 600;
    padding: 2px 10px;
    border-radius: 20px;
    margin-bottom: 12px;
    font-family: ui-monospace, SFMono-Regular, "SF Mono", Menlo, monospace;
}
.status-2xx { background: #0d2818; color: #3fb950; border: 1px solid #238636; }
.status-3xx { background: #2a1f00; color: #d29922; border: 1px solid #9e6a03; }
.status-4xx { background: #2d0e0e; color: #f85149; border: 1px solid #da3633; }
.status-5xx { background: #2d0e0e; color: #f85149; border: 1px solid #da3633; }
.status-none { background: #161b22; color: #8b949e; border: 1px solid #30363d; }

/* ── Empty state ── */
.empty-state {
    display: flex;
    flex-direction: column;
    align-items: center;
    justify-content: center;
    padding: 60px 24px;
    text-align: center;
    background: #161b22;
    border: 1px dashed #30363d;
    border-radius: 6px;
    margin-top: 8px;
}
.empty-state-icon { font-size: 36px; margin-bottom: 14px; opacity: 0.4; }
.empty-state-title { font-size: 15px; font-weight: 600; color: #8b949e; margin-bottom: 4px; }
.empty-state-sub   { font-size: 13px; color: #484f58; }

/* ── No-key indicator ── */
.nokey-badge {
    display: inline-block;
    font-size: 11px;
    font-weight: 600;
    background: #0d2818;
    color: #3fb950;
    border: 1px solid #238636;
    border-radius: 4px;
    padding: 1px 6px;
    margin-left: 4px;
}

/* ── Header ── */
.app-header {
    display: flex;
    align-items: center;
    gap: 12px;
    padding: 4px 0 20px 0;
    border-bottom: 1px solid #21262d;
    margin-bottom: 24px;
}
.app-header-icon {
    width: 36px; height: 36px;
    background: #1f6feb;
    border-radius: 8px;
    display: flex; align-items: center; justify-content: center;
    font-size: 18px;
    color: white;
}
.app-header-title { font-size: 20px; font-weight: 600; color: #e6edf3; margin: 0; }
.app-header-sub   { font-size: 13px; color: #8b949e; margin: 0; }
.connector-count {
    margin-left: auto;
    background: #21262d;
    border: 1px solid #30363d;
    border-radius: 20px;
    padding: 3px 12px;
    font-size: 12px;
    font-weight: 600;
    color: #8b949e;
}

/* ── Buttons ── */
[data-testid="stButton"] > button {
    width: 100%;
    background: #1f6feb !important;
    color: white !important;
    border: 1px solid rgba(240, 246, 252, 0.1) !important;
    border-radius: 6px !important;
    font-weight: 600 !important;
    font-size: 14px !important;
    padding: 8px !important;
    margin-top: 6px;
    transition: background 0.15s;
}
[data-testid="stButton"] > button:hover {
    background: #388bfd !important;
}

/* ── Download buttons ── */
[data-testid="stDownloadButton"] > button {
    background: #21262d !important;
    color: #c9d1d9 !important;
    border: 1px solid #30363d !important;
    border-radius: 6px !important;
    font-weight: 500 !important;
    font-size: 13px !important;
    width: 100%;
}
[data-testid="stDownloadButton"] > button:hover {
    background: #30363d !important;
    border-color: #8b949e !important;
}

/* ── Code blocks ── */
[data-testid="stCode"] {
    border-radius: 6px !important;
    border: 1px solid #30363d !important;
}

/* ── Expander ── */
[data-testid="stExpander"] {
    border: 1px solid #30363d !important;
    border-radius: 6px !important;
    background: #161b22 !important;
}

/* ── Multiselect / select ── */
.stMultiSelect > div > div {
    background: #0d1117 !important;
    border-color: #30363d !important;
}

/* ── Section divider ── */
.section-divider {
    border-top: 1px solid #21262d;
    margin: 20px 0 16px 0;
    padding-top: 16px;
}

/* ── Info box ── */
.info-box {
    background: #161b22;
    border: 1px solid #30363d;
    border-radius: 6px;
    padding: 12px 16px;
    font-size: 13px;
    color: #8b949e;
    line-height: 1.5;
}
</style>
""", unsafe_allow_html=True)

# ── Header ──
num_connectors = len(PLATFORM_MODES)
st.markdown(f"""
<div class="app-header">
  <div class="app-header-icon">⚡</div>
  <div>
    <p class="app-header-title">Social Connector</p>
    <p class="app-header-sub">API explorer for {num_connectors} platforms</p>
  </div>
  <div class="connector-count">{num_connectors} connectors</div>
</div>
""", unsafe_allow_html=True)


# ── Sidebar ──
with st.sidebar:
    st.markdown("""
    <div style="padding: 14px 0 8px 0;">
      <p style="font-size:16px; font-weight:600; color:#e6edf3; margin:0;">Configuration</p>
      <p style="font-size:12px; color:#8b949e; margin:2px 0 0 0;">Select a connector and run a query</p>
    </div>
    """, unsafe_allow_html=True)

    st.markdown('<p class="sidebar-label">Platform</p>', unsafe_allow_html=True)

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
            '<p style="font-size:12px; color:#3fb950; margin:-4px 0 6px 0;">No API key required</p>',
            unsafe_allow_html=True,
        )
    else:
        st.markdown(
            '<p style="font-size:12px; color:#8b949e; margin:-4px 0 6px 0;">API key required</p>',
            unsafe_allow_html=True,
        )

    # Route / mode selector
    st.markdown('<p class="sidebar-label">Route</p>', unsafe_allow_html=True)
    available_modes = PLATFORM_MODES[platform]
    mode = st.radio("Route", available_modes, label_visibility="collapsed", horizontal=len(available_modes) <= 3)

    # NIH database selector
    selected_db_name = None
    selected_db_code = None
    link_target_db = None

    if platform == "NIH (NCBI)":
        st.markdown('<p class="sidebar-label">Database</p>', unsafe_allow_html=True)
        selected_db_name = st.selectbox(
            "Database",
            list(NCBI_DATABASES.keys()),
            format_func=lambda x: f"{x} — {NCBI_DATABASES[x]['desc']}",
            label_visibility="collapsed",
        )
        selected_db_code = NCBI_DATABASES[selected_db_name]["db"]

        # For Find Links, pick target database
        if mode == "Find Links":
            st.markdown('<p class="sidebar-label">Target Database</p>', unsafe_allow_html=True)
            target_db_name = st.selectbox(
                "Target DB",
                [n for n in NCBI_DATABASES.keys() if n != selected_db_name],
                label_visibility="collapsed",
            )
            link_target_db = NCBI_DATABASES[target_db_name]["db"]

    # Query input
    st.markdown('<p class="sidebar-label">Query</p>', unsafe_allow_html=True)
    skip_query = platform == "NIH (NCBI)" and mode == "Database Info"

    if skip_query:
        query = ""
        st.markdown(
            '<p style="font-size:12px; color:#8b949e; margin:0 0 6px 0;">No query needed for Database Info</p>',
            unsafe_allow_html=True,
        )
    elif platform in {"OpenAI", "Gemini"}:
        query = st.text_input("Query", placeholder="Enter your prompt...", label_visibility="collapsed")
    elif platform in NO_KEY_PLATFORMS:
        query = st.text_input("Query", placeholder="e.g. mRNA vaccine outcomes", label_visibility="collapsed")
    else:
        query = st.text_input("Query", placeholder="keyword, @username, or #hashtag", label_visibility="collapsed")

    # Max results
    needs_max = mode not in {"Database Info", "Spell Check", "Global Query", "Generate"}
    if needs_max:
        st.markdown('<p class="sidebar-label">Max Results</p>', unsafe_allow_html=True)
        if platform in {"NIH (NCBI)", "NIH Reporter"}:
            max_results = st.slider(
                "Max results", min_value=1, max_value=1000, value=50,
                label_visibility="collapsed",
                help="For large fetches, results are retrieved in batches with a progress indicator.",
            )
        else:
            max_results = st.slider(
                "Max results", min_value=1, max_value=50, value=10,
                label_visibility="collapsed",
            )
    else:
        max_results = 10

    st.markdown("<br>", unsafe_allow_html=True)
    submit = st.button("Send Request", type="primary")

    # Sidebar footer
    st.markdown(f"""
    <div style="margin-top: 24px; padding-top: 12px; border-top: 1px solid #30363d;">
      <p class="sidebar-label">No-key connectors</p>
      <p style="font-size:12px; color:#8b949e; line-height:1.6;">
        {"  ·  ".join(sorted(NO_KEY_PLATFORMS))}
      </p>
    </div>
    """, unsafe_allow_html=True)


# ── Main content ──
if submit:
    if not query and not skip_query:
        st.warning("Please enter a query.")
        st.stop()

    result: Optional[ApiResult] = None

    # ── NIH (NCBI) – handled separately for pagination / special routes ──
    if platform == "NIH (NCBI)":
        ncbi = NCBIClient(database=selected_db_code)

        if mode == "Search":
            if max_results > ncbi.BATCH_SIZE:
                # Paginated fetch with progress
                progress_bar = st.progress(0, text="Starting search...")
                status_area = st.empty()

                def on_progress(current: int, total: int, message: str):
                    frac = current / total if total > 0 else 0
                    progress_bar.progress(min(frac, 1.0), text=message)
                    status_area.caption(message)

                result = ncbi.search_with_summaries(query, max_results, progress_callback=on_progress)
                progress_bar.progress(1.0, text=f"Done — {len(result.records)} records fetched")
                time.sleep(0.5)
                progress_bar.empty()
                status_area.empty()
            else:
                with st.spinner("Searching NCBI..."):
                    result = ncbi.search_with_summaries(query, max_results)

        elif mode == "Fetch IDs":
            with st.spinner("Searching NCBI..."):
                result = ncbi.search_ids(query, max_results)

        elif mode == "Database Info":
            with st.spinner("Fetching database info..."):
                result = ncbi.db_info()

        elif mode == "Fetch Details (XML)":
            with st.spinner("Fetching full records..."):
                result = ncbi.fetch_details(query, max_results)

        elif mode == "Spell Check":
            with st.spinner("Checking spelling..."):
                result = ncbi.spell_check(query)

        elif mode == "Global Query":
            with st.spinner("Querying across all databases..."):
                result = ncbi.global_query(query)

        elif mode == "Find Links":
            with st.spinner("Finding linked records..."):
                result = ncbi.find_links(query, link_target_db, max_results)

    # ── NIH Reporter – paginated ──
    elif platform == "NIH Reporter":
        reporter = NIHReporterClient()

        if max_results > reporter.BATCH_SIZE:
            progress_bar = st.progress(0, text="Starting search...")
            status_area = st.empty()

            def on_progress_reporter(current: int, total: int, message: str):
                frac = current / total if total > 0 else 0
                progress_bar.progress(min(frac, 1.0), text=message)
                status_area.caption(message)

            result = reporter.search(mode.lower(), query, max_results, progress_callback=on_progress_reporter)
            progress_bar.progress(1.0, text=f"Done — {len(result.records)} records fetched")
            time.sleep(0.5)
            progress_bar.empty()
            status_area.empty()
        else:
            with st.spinner("Searching NIH Reporter..."):
                result = reporter.search(mode.lower(), query, max_results)

    # ── All other platforms ──
    else:
        with st.spinner("Sending request..."):
            result = run_search(platform, mode, query, max_results)

    # Store result in session state
    if result:
        st.session_state["result"] = result
        st.session_state["result_platform"] = platform
        st.session_state["result_mode"] = mode
        st.session_state["result_query"] = query
        # Reset field selection on new search
        st.session_state.pop("field_selection_key", None)


# ── Display results ──
if "result" in st.session_state:
    result = st.session_state["result"]

    if result.error:
        st.markdown(f"""
        <div style="background:#2d0e0e; border:1px solid #da3633; border-radius:6px;
                    padding:12px 16px; margin-bottom:16px; color:#f85149; font-size:13px;">
          <strong>Error:</strong> {result.error}
        </div>""", unsafe_allow_html=True)

    left, right = st.columns(2, gap="medium")

    with left:
        st.markdown("""
        <div class="panel-title">
          <span class="panel-dot dot-request"></span> Request
        </div>""", unsafe_allow_html=True)
        st.code(json.dumps(result.request_details, indent=2, default=str), language="json")

    with right:
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

    # ── Field selection & Export ──
    records = result.records
    if records and isinstance(records, list) and len(records) > 0:
        st.markdown('<div class="section-divider"></div>', unsafe_allow_html=True)
        st.markdown(f"**{len(records)} records available for export**")

        all_keys = extract_all_keys(records)

        if all_keys:
            with st.expander("Select fields to include in export", expanded=False):
                st.caption("Uncheck fields you want to exclude. Nested objects are flattened with dot notation.")
                # Use a unique key per search to reset selection
                widget_key = f"fields_{hash(str(st.session_state.get('result_query', '')) + str(st.session_state.get('result_mode', '')))}"
                selected_keys = st.multiselect(
                    "Fields",
                    all_keys,
                    default=all_keys,
                    label_visibility="collapsed",
                    key=widget_key,
                )

            if not selected_keys:
                selected_keys = all_keys

            col_json, col_excel = st.columns(2)
            with col_json:
                json_data = records_to_json(records, selected_keys)
                st.download_button(
                    "Download JSON",
                    json_data,
                    file_name="export.json",
                    mime="application/json",
                    use_container_width=True,
                )
            with col_excel:
                excel_data = records_to_excel(records, selected_keys)
                st.download_button(
                    "Download Excel",
                    excel_data,
                    file_name="export.xlsx",
                    mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                    use_container_width=True,
                )

elif not submit:
    icon = PLATFORM_ICONS.get(platform, "⚡")
    st.markdown(f"""
    <div class="empty-state">
      <div class="empty-state-icon">{icon}</div>
      <p class="empty-state-title">Ready to connect to {platform}</p>
      <p class="empty-state-sub">Configure your query in the sidebar and click <strong style="color:#8b949e">Send Request</strong>.</p>
    </div>
    """, unsafe_allow_html=True)


# ── Setup reference ──
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
| X (Twitter) | `TWITTER_BEARER_TOKEN` | Yes |
| Reddit | `REDDIT_CLIENT_ID`, `REDDIT_CLIENT_SECRET` | Yes |
| Instagram | `INSTAGRAM_ACCESS_TOKEN` | Yes |
| TikTok | `TIKTOK_ACCESS_TOKEN` | Yes |
| YouTube | `YOUTUBE_API_KEY` | Yes |
| OpenAI | `OPENAI_API_KEY` | Yes |
| Gemini | `GEMINI_API_KEY` | Yes |
| NIH (NCBI) | — | No |
| NIH Reporter | — | No |
| ClinicalTrials.gov | — | No |
| Crossref | — | No |
| Wikipedia | — | No |

**NIH (NCBI) databases available:** """ + ", ".join(NCBI_DATABASES.keys()) + """

**NIH (NCBI) routes:**
- **Search** — Full text search with document summaries (paginated)
- **Fetch IDs** — Returns matching record IDs only
- **Database Info** — Statistics and searchable fields for a database
- **Fetch Details (XML)** — Full record data in XML format
- **Spell Check** — Spelling suggestions for search terms
- **Global Query** — Search counts across all Entrez databases
- **Find Links** — Discover related records in another database

**Export:** After any search, use the JSON or Excel download buttons. You can select which fields to include.
    """)
