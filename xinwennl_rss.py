#!/usr/bin/env python3
import json
import os
import urllib.parse
from datetime import datetime, timezone
from typing import TypedDict

import requests
from bs4 import BeautifulSoup
from feedgen.feed import FeedGenerator


class Article(TypedDict):
    title: str
    translate_url: str
    pub_date: str


def fetch_html(url: str) -> str:
    response = requests.get(url)
    response.raise_for_status()
    return response.text


def parse_articles(html: str) -> list[Article]:
    soup = BeautifulSoup(html, "html.parser")
    articles: list[Article] = []
    # Find all elements that include 'tm-timeline-item' in their class
    timeline_items = soup.select("div.tm-timeline-item")
    for item in timeline_items:
        # Skip if no article title is found
        h3 = item.select_one("h3.tm-font-400")
        if not h3:
            continue
        title = h3.get_text(strip=True)

        # Extract the original article URL from the green button
        orig_link = item.select_one("a.button-green")
        orig_url = orig_link.get("href") if orig_link else ""
        # If orig_url is a list, take the first element
        if isinstance(orig_url, list):
            orig_url = orig_url[0]

        # Get the Google Translate link (it has class "button-black")
        translate_link = item.select_one("a.button-black")
        if not translate_link:
            continue
        raw_translate_url = translate_link.get("href", "")
        if isinstance(raw_translate_url, list):
            raw_translate_url = raw_translate_url[0]

        # If the original URL is from NL Times, construct a Yandex translate URL
        if orig_url and "nltimes.nl" in orig_url:
            encoded_url = urllib.parse.quote(orig_url, safe="")
            translate_url = f"https://translate.yandex.com/en/translate?url={encoded_url}&lang=en-zh"
        else:
            translate_url = raw_translate_url

        # Try to extract publication date from the element with class including "tm-text-green"
        pub_date = None
        p_date = item.select_one("p.tm-text-green")
        if p_date:
            text = p_date.get_text(strip=True)
            if "发布于" in text:
                try:
                    # Expecting a format like: "Ducth News.nl 发布于 Sat, 15 Feb 2025 17:04:03 +0000"
                    pub_str = text.split("发布于")[-1].strip()
                    pub_date = datetime.strptime(pub_str, "%a, %d %b %Y %H:%M:%S %z")
                except Exception:
                    pass
        if not pub_date:
            pub_date = datetime.now()

        articles.append(
            {
                "title": title,
                "translate_url": translate_url,
                "pub_date": pub_date.isoformat(),
            }
        )
    return articles


def save_json(data, path: str) -> None:
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)


def generate_rss(articles: list[Article], output_path: str) -> None:
    fg = FeedGenerator()
    fg.title("荷兰新闻 | 本地新闻每日更新")
    fg.link(href="https://xinwen.nl/", rel="alternate")
    fg.description("最新鲜的荷兰本地新闻，每日不间断更新！")
    fg.language("zh-CN")

    for art in articles:
        fe = fg.add_entry()
        fe.title(art["title"])
        fe.link(href=art["translate_url"])
        try:
            pub_date = datetime.fromisoformat(art["pub_date"])
        except Exception:
            pub_date = datetime.now(timezone.utc)
        # If pub_date is naive, attach UTC as the default timezone
        if pub_date.tzinfo is None:
            pub_date = pub_date.replace(tzinfo=timezone.utc)
        fe.pubDate(pub_date)
        # Using title as description; adjust as needed.
        fe.description(art["title"])

    os.makedirs(os.path.dirname(output_path), exist_ok=True)
    fg.rss_file(output_path)


def main():
    url = "https://xinwen.nl/"
    html = fetch_html(url)
    articles = parse_articles(html)
    # Save the parsed articles state
    save_json(articles, "state/articles.json")
    # Generate RSS feed from the JSON state
    generate_rss(articles, "gh-pages/rss.xml")


if __name__ == "__main__":
    main()
