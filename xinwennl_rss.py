# /// script
# dependencies = [
#   "beautifulsoup4==4.14.2",
#   "feedgen==1.0.0",
#   "requests==2.32.5",
#   "feedparser==6.0.12"
# ]
# ///

import json
import logging
import os
from datetime import datetime, timezone
from typing import TypedDict
from urllib.parse import quote

import feedparser
import requests
from bs4 import BeautifulSoup
from feedgen.feed import FeedGenerator

# Set up logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    datefmt='%Y-%m-%d %H:%M:%S'
)
logger = logging.getLogger(__name__)


class Article(TypedDict):
    fingerprint: str
    title: str
    title_zh: str
    description: str
    description_zh: str
    link: str
    translate_link: str
    pub_date: str
    source_website: str


def translate_text(text: str, api_key: str, target_lang: str = 'zh') -> str:
    """Translate text using Google Translate REST API.
    
    Args:
        text: Text to translate
        api_key: Google Translate API key
        target_lang: Target language code (default: 'zh')
        
    Returns:
        Translated text
        
    Raises:
        requests.RequestException: If API request fails
        KeyError: If API response format is unexpected
    """
    if not text.strip():
        return text
        
    url = 'https://translation.googleapis.com/language/translate/v2'
    params = {
        'key': api_key,
        'q': text,
        'target': target_lang,
        'source': 'en'
    }
    
    try:
        response = requests.post(url, data=params, timeout=30)
        response.raise_for_status()
        result = response.json()
        return result['data']['translations'][0]['translatedText']
    except (requests.RequestException, KeyError) as e:
        logger.warning(f"Translation failed for text '{text[:50]}...': {e}")
        return text


def process_feed_entry(entry, source: str, api_key: str, existing_fingerprints: set[str]) -> Article | None:
    """Process a single RSS feed entry into an Article.
    
    Args:
        entry: RSS feed entry
        source: Source website name
        api_key: Google Translate API key
        existing_fingerprints: Set of existing article fingerprints (IDs or links)
        
    Returns:
        Article if successfully processed and new, None if skipped
    """
    # Get title and skip if empty
    title = entry.get('title', '').strip()
    if not title:
        return None
    
    # Get clean description
    description = entry.get('summary', '') or entry.get('description', '')
    if description:
        soup = BeautifulSoup(description, 'html.parser')
        description = soup.get_text(strip=True)
    
    # Get unique fingerprint (prefer GUID/ID, fallback to link)
    article_fingerprint = entry.get('guid') or entry.get('id') or entry.get('link', '')
    original_link = entry.get('link', '')
    
    # Skip if we already have this article
    if article_fingerprint in existing_fingerprints:
        logger.info(f"Skipping existing article: {title[:50]}...")
        return None
    
    # Translate title and description
    logger.info(f"Translating title: {title[:50]}...")
    title_zh = translate_text(title, api_key)
    
    if description:
        logger.info(f"Translating description ({len(description)} chars)")
        description_zh = translate_text(description, api_key)
    else:
        description_zh = ''
    
    # Create Google Translate link for the original URL
    encoded_url = quote(original_link, safe='')
    translate_link = f"https://translate.google.com/translate?sl=en&tl=zh&u={encoded_url}"
    
    # Parse publication date
    pub_date = datetime.now(timezone.utc)
    if hasattr(entry, 'published_parsed') and entry.published_parsed:
        try:
            pub_date = datetime(*entry.published_parsed[:6], tzinfo=timezone.utc)
        except (ValueError, TypeError, OverflowError):
            pass
    elif hasattr(entry, 'updated_parsed') and entry.updated_parsed:
        try:
            pub_date = datetime(*entry.updated_parsed[:6], tzinfo=timezone.utc)
        except (ValueError, TypeError, OverflowError):
            pass
    
    return {
        "fingerprint": article_fingerprint,
        "title": title,
        "title_zh": title_zh,
        "description": description,
        "description_zh": description_zh,
        "link": original_link,
        "translate_link": translate_link,
        "pub_date": pub_date.isoformat(),
        "source_website": source,
    }


def fetch_single_feed(feed_url: str, source: str, api_key: str, existing_fingerprints: set[str]) -> list[Article]:
    """Fetch and process a single RSS feed.
    
    Args:
        feed_url: URL of the RSS feed
        source: Source website name
        api_key: Google Translate API key
        existing_fingerprints: Set of existing article fingerprints (IDs or links)
        
    Returns:
        List of new articles from this feed
    """
    logger.info(f"Fetching RSS feed from {source}: {feed_url}")
    articles = []
    
    try:
        feed = feedparser.parse(feed_url)
        logger.info(f"Successfully parsed {len(feed.entries)} entries from {source}")
        
        for entry in feed.entries:
            article = process_feed_entry(entry, source, api_key, existing_fingerprints)
            if article:
                articles.append(article)
                
    except (requests.RequestException, ValueError, KeyError) as e:
        logger.error(f"Failed to fetch {feed_url}: {e}")
    
    return articles


def fetch_rss_feeds(api_key: str, existing_articles: list[Article] = None) -> list[Article]:
    """Fetch and parse RSS feeds from multiple sources
    
    Args:
        api_key: Google Translate API key
        existing_articles: Existing articles to check for duplicates
        
    Returns:
        List of all articles (existing + new)
    """
    logger.info("Starting RSS feed fetching and translation")
    feeds = [
        ("https://nltimes.nl/rssfeed2", "NL Times"),
        ("https://www.dutchnews.nl/feed/", "Dutch News"),
        # ("https://www.theguardian.com/world/netherlands/rss", "The Guardian")  # Commented out - infrequent updates
    ]
    
    if existing_articles is None:
        existing_articles = []
    
    # Create a set of existing article IDs or fallback links for fast lookup
    existing_fingerprints = {article.get('fingerprint', article.get('link', '')) for article in existing_articles}
    
    # Fetch articles from all feeds
    new_articles: list[Article] = []
    for feed_url, source in feeds:
        feed_articles = fetch_single_feed(feed_url, source, api_key, existing_fingerprints)
        new_articles.extend(feed_articles)
    
    # Combine existing and new articles
    all_articles = existing_articles + new_articles
    
    # Sort by publication date, newest first
    all_articles.sort(key=lambda x: x['pub_date'], reverse=True)
    
    # Keep only the latest 77 articles
    if len(all_articles) > 77:
        all_articles = all_articles[:77]
        logger.info(f"Truncated to latest 77 articles")
    
    logger.info(f"Successfully processed {len(new_articles)} new articles, {len(all_articles)} total articles")
    return all_articles


def load_existing_state(path: str) -> list[Article]:
    """Load existing article state from JSON file.
    
    Args:
        path: Path to existing state file
        
    Returns:
        List of existing articles, empty list if file doesn't exist
    """
    if not os.path.exists(path):
        logger.info(f"No existing state found at {path}")
        return []
    
    try:
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
        logger.info(f"Loaded {len(data)} existing articles from {path}")
        return data
    except (json.JSONDecodeError, OSError) as e:
        logger.warning(f"Failed to load existing state from {path}: {e}")
        return []


def save_json(data: list[Article], path: str) -> None:
    """Save article data to JSON file.
    
    Args:
        data: List of articles to save
        path: Output file path
    """
    logger.info(f"Saving {len(data)} articles to {path}")
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
    logger.info(f"Successfully saved articles to {path}")


def generate_rss(articles: list[Article], output_path: str) -> None:
    """Generate RSS feed from articles.
    
    Args:
        articles: List of articles to include in feed
        output_path: Output RSS file path
    """
    logger.info(f"Generating RSS feed with {len(articles)} articles")
    fg = FeedGenerator()
    fg.title("荷兰新闻 | 本地新闻每日更新")
    fg.link(href="https://xinwen.nl/", rel="alternate")
    fg.description("最新鲜的荷兰本地新闻，每日不间断更新！")
    fg.language("zh-CN")

    for art in articles:
        fe = fg.add_entry()
        fe.title(art["title_zh"])
        fe.link(href=art["translate_link"])
        fe.guid(art.get("fingerprint", art.get("link", "")))
        try:
            pub_date = datetime.fromisoformat(art["pub_date"])
        except (ValueError, TypeError):
            pub_date = datetime.now(timezone.utc)
        # If pub_date is naive, attach UTC as the default timezone
        if pub_date.tzinfo is None:
            pub_date = pub_date.replace(tzinfo=timezone.utc)
        fe.pubDate(pub_date)
        # Use translated description or title if no description
        description = art["description_zh"] if art["description_zh"] else art["title_zh"]
        fe.description(description)
        fe.author(
            {
                "name": art["source_website"],
                "email": f"{art['source_website']}@{art['source_website']}.com",
            }
        )

    os.makedirs(os.path.dirname(output_path), exist_ok=True)
    fg.rss_file(output_path)
    logger.info(f"Successfully generated RSS feed: {output_path}")


def main() -> None:
    """Main function to fetch, translate, and generate RSS feed."""
    logger.info("Starting RSS feed processing")
    
    # Get Google Translate API key from environment variable
    api_key = os.getenv('GOOGLE_TRANSLATE_API_KEY')
    if not api_key:
        logger.error("GOOGLE_TRANSLATE_API_KEY environment variable is required")
        raise ValueError("GOOGLE_TRANSLATE_API_KEY environment variable is required")
    
    try:
        # Load existing articles state
        existing_articles = load_existing_state("state/articles.json")
        
        # Fetch and translate new articles from RSS feeds
        articles = fetch_rss_feeds(api_key, existing_articles)
        
        # Save the updated articles state
        save_json(articles, "state/articles.json")
        
        # Generate RSS feed from the JSON state
        generate_rss(articles, "gh-pages/rss.xml")
        
        logger.info(f"Successfully completed processing {len(articles)} articles")
    except Exception as e:
        logger.error(f"Failed to process RSS feeds: {e}")
        raise


if __name__ == "__main__":
    try:
        main()
    except Exception as e:
        logger.error(f"Script failed: {e}")
        exit(1)
