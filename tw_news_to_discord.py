#!/usr/bin/env python3
"""Total War news -> Discord.

Poste les nouveaux articles de totalwar.com/news dans un salon Discord
via un webhook. Concu pour tourner via cron ou un timer systemd.

Dependances :
    pip install --break-system-packages cloudscraper beautifulsoup4

Variable d'environnement requise :
    DISCORD_WEBHOOK_URL   l'URL du webhook du salon Discord
"""

import json
import os
import sys
import urllib.request
from datetime import datetime

import cloudscraper
from bs4 import BeautifulSoup

WEBHOOK_URL = os.environ.get("DISCORD_WEBHOOK_URL", "")
NEWS_URL = "https://www.totalwar.com/news"
BASE_URL = "https://www.totalwar.com"
STATE_FILE = os.environ.get(
    "TW_STATE_FILE", os.path.expanduser("~/.cache/tw_news_seen.json")
)
MAX_POST = 5          # garde-fou : jamais plus de N posts par execution
COLOR = 0xC8102E      # rouge Total War (decimal de l'embed Discord)


def load_seen():
    try:
        with open(STATE_FILE) as f:
            return set(json.load(f))
    except (FileNotFoundError, json.JSONDecodeError):
        return set()


def save_seen(seen):
    os.makedirs(os.path.dirname(STATE_FILE), exist_ok=True)
    with open(STATE_FILE, "w") as f:
        json.dump(sorted(seen), f)


def abs_url(href):
    if not href:
        return ""
    return BASE_URL + href if href.startswith("/") else href


def fetch_articles():
    """Liste de dicts d'articles, dans l'ordre de la page (plus recent en premier)."""
    scraper = cloudscraper.create_scraper()
    html = scraper.get(NEWS_URL, timeout=30).text
    soup = BeautifulSoup(html, "html.parser")

    articles = []
    for card in soup.select("div.post-item"):
        link = card.select_one("a.link[href^='/news/']") or card.select_one("a[href^='/news/']")
        if not link:
            continue
        href = (link.get("href") or "").strip()
        title = link.get_text(strip=True)
        if not href or not title:
            continue

        game_el = card.select_one(".post-item--game")
        date_el = card.select_one("time.post-item--published-date")
        desc_el = card.select_one(".post-item--description")
        img_el = card.select_one(".post-item--image img")

        image = ""
        if img_el:
            image = img_el.get("src") or img_el.get("data-src") or ""
            image = abs_url(image)

        articles.append({
            "title": title,
            "url": abs_url(href),
            "game": game_el.get_text(strip=True) if game_el else "",
            "date": (date_el.get("datetime") or "") if date_el else "",
            "description": desc_el.get_text(strip=True) if desc_el else "",
            "image": image,
        })
    return articles


def build_embed(article):
    embed = {
        "title": article["title"][:256],
        "url": article["url"],
        "color": COLOR,
    }
    if article.get("description"):
        embed["description"] = article["description"][:600]
    if article.get("game"):
        embed["author"] = {"name": article["game"]}
    if article.get("image"):
        embed["image"] = {"url": article["image"]}

    footer = "Total War News"
    if article.get("date"):
        try:
            footer += " | " + datetime.fromisoformat(article["date"]).strftime("%d/%m/%Y")
        except ValueError:
            pass
    embed["footer"] = {"text": footer}
    return embed


def post(article):
    payload = {"embeds": [build_embed(article)]}
    req = urllib.request.Request(
        WEBHOOK_URL,
        data=json.dumps(payload).encode("utf-8"),
        headers={"Content-Type": "application/json"},
    )
    urllib.request.urlopen(req, timeout=15)


def main():
    if not WEBHOOK_URL:
        sys.exit("Erreur : variable DISCORD_WEBHOOK_URL manquante.")

    seen = load_seen()
    articles = fetch_articles()
    if not articles:
        sys.exit("Aucun article trouve : le selecteur a peut-etre change.")

    # Premiere execution : on memorise tout SANS poster (evite de deverser
    # toute la page dans le salon d'un coup).
    if not seen:
        save_seen({a["url"] for a in articles})
        print(f"Init : {len(articles)} articles memorises, aucun post envoye.")
        return

    # Plus anciens d'abord, plafonne a MAX_POST : ordre chronologique preserve.
    unseen = [a for a in articles if a["url"] not in seen]
    unseen.reverse()
    to_post = unseen[:MAX_POST]

    for a in to_post:
        post(a)
        seen.add(a["url"])
        print(f"Poste : {a['title']}")

    save_seen(seen)
    if not to_post:
        print("Rien de nouveau.")


if __name__ == "__main__":
    main()
