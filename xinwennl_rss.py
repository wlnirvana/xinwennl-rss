#!/usr/bin/env python3

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


def fetch_rss_feeds(api_key: str) -> list[Article]:
    """Fetch and parse RSS feeds from the two sources"""
    logger.info("Starting RSS feed fetching and translation")
    feeds = [
        ("https://nltimes.nl/rssfeed2", "NL Times"),
        ("https://www.dutchnews.nl/feed/", "Dutch News"),
        # ("https://www.theguardian.com/world/netherlands/rss", "The Guardian")  # Commented out - infrequent updates
    ]
    
    articles: list[Article] = []
    
    for feed_url, source in feeds:
        logger.info(f"Fetching RSS feed from {source}: {feed_url}")
        try:
            feed = feedparser.parse(feed_url)
            logger.info(f"Successfully parsed {len(feed.entries)} entries from {source}")
            for entry in feed.entries:
                # Get title and description
                title = entry.get('title', '').strip()
                description = entry.get('summary', '') or entry.get('description', '')
                
                # Clean HTML from description if present
                if description:
                    soup = BeautifulSoup(description, 'html.parser')
                    description = soup.get_text(strip=True)
                
                # Skip if no title
                if not title:
                    continue
                
                # Translate title and description
                logger.info(f"Translating title: {title[:50]}...")
                title_zh = translate_text(title, api_key)
                
                if description:
                    logger.info(f"Translating description ({len(description)} chars)")
                    description_zh = translate_text(description, api_key)
                else:
                    description_zh = ''
                
                # Create Google Translate link for the original URL
                original_link = entry.get('link', '')
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
                
                articles.append({
                    "title": title,
                    "title_zh": title_zh,
                    "description": description,
                    "description_zh": description_zh,
                    "link": original_link,
                    "translate_link": translate_link,
                    "pub_date": pub_date.isoformat(),
                    "source_website": source,
                })
        except (requests.RequestException, ValueError, KeyError) as e:
            logger.error(f"Failed to fetch {feed_url}: {e}")
    
    # Sort by publication date, newest first
    articles.sort(key=lambda x: x['pub_date'], reverse=True)
    logger.info(f"Successfully processed {len(articles)} total articles")
    return articles


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
        # Fetch and translate articles from RSS feeds
        articles = fetch_rss_feeds(api_key)
        
        # Save the parsed articles state
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
