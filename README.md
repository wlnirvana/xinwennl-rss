# Dutch News RSS Feed in Chinese

A Chinese [RSS feed](https://wlnirvana.github.io/xinwennl-rss/rss.xml) aggregating Dutch news from [NL Times](https://nltimes.nl) and [Dutch News](https://www.dutchnews.nl), automatically translated using Google Translate API.

*(Originally created as an RSS feed for xinwen.nl which is no longer updated.)*

## Running Locally

1. Set up your Google Translate API key:
   ```bash
   export GOOGLE_TRANSLATE_API_KEY="your-api-key-here"
   ```

2. Run the script with [uv](https://docs.astral.sh/uv/):
   ```bash
   uv run xinwennl_rss.py
   ```

   The script will:
   - Load existing articles from `state/articles.json` (if it exists)
   - Fetch new articles from RSS feeds
   - Translate titles and descriptions to Chinese
   - Save updated state and generate `gh-pages/rss.xml`

---
Inspired by https://github.com/zhangyoufu/lwn
