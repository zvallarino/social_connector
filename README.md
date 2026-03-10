# Social Connector

A super-simple Streamlit front page for exploring API calls to:
- Instagram API
- YouTube API
- TikTok API

It shows:
- **Left side**: request payload/params being sent
- **Right side**: response body received

You can search by:
- **Post**
- **Profile**
- **Hashtag** (TikTok only)

## Quick start

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env
# fill in API credentials in .env
streamlit run app.py
```

Then open the local Streamlit URL (usually `http://localhost:8501`).

## Notes

- **Instagram**: Basic Display endpoints typically return data for the authenticated account. Broader account/post discovery usually requires Instagram Graph API + Business setup.
- **YouTube**: Uses `youtube/v3/search` and switches `type` between `video` (post) and `channel` (profile).
- **TikTok**: API products differ by access tier. This demo defaults to a research-style endpoint and includes hashtag query support.

## Environment variables

- `YOUTUBE_API_KEY`
- `INSTAGRAM_ACCESS_TOKEN`
- `TIKTOK_ACCESS_TOKEN`
- `TIKTOK_API_BASE` (optional)
