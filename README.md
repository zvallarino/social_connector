# Social Connector

A simple Streamlit troubleshooting console for testing multiple connectors and seeing:
- **What it's sending** (URL, params, headers, JSON body)
- **What it's getting back** (status + response payload)

## Connectors included

- X (Twitter)
- Reddit
- Instagram
- TikTok
- YouTube
- OpenAI
- Gemini
- NIH PubMed
- ClinicalTrials.gov
- Crossref
- Wikipedia

## No-key connectors (good for quick smoke tests)

These should work without any API key/token:
- NIH PubMed
- ClinicalTrials.gov
- Crossref
- Wikipedia

## Command list (after git clone)

### macOS / Linux

```bash
git clone <your-repo-url>
cd social_connector
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env
# edit .env and add any keys you want to test
streamlit run app.py
```

### Windows PowerShell

```powershell
git clone <your-repo-url>
cd social_connector
py -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
copy .env.example .env
# edit .env and add any keys you want to test
streamlit run app.py
```

## Environment variables

Fill only the connectors you want to test:

- `YOUTUBE_API_KEY`
- `INSTAGRAM_ACCESS_TOKEN`
- `TIKTOK_ACCESS_TOKEN`
- `TIKTOK_API_BASE` (optional)
- `REDDIT_ACCESS_TOKEN`
- `REDDIT_USER_AGENT`
- `X_BEARER_TOKEN`
- `OPENAI_API_KEY`
- `OPENAI_MODEL` (optional)
- `GEMINI_API_KEY`
- `GEMINI_MODEL` (optional)

## Notes

- Some APIs need approved scopes/access tiers even when key/token is present.
- This project is currently a **single Streamlit app** (`app.py`), not split backend/frontend.
