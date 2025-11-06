#!/usr/bin/env python3
"""
update_pubs.py — generate pub.html from Google Scholar

Usage:
  python update_pubs.py --user-id YOUR_SCHOLAR_ID
"""

import argparse
import sys
import time
from typing import List, Optional, Dict, Any
from scholarly import scholarly  # pip install scholarly==1.7.11

def fetch_publications(user_id: str, max_pubs: int = 200, delay: float = 0.25) -> List[Dict[str, Any]]:
    """Fetch publications (title, authors, venue, year, url) sorted newest first."""
    author = scholarly.search_author_id(user_id)
    author = scholarly.fill(author, sections=["publications"])

    pubs: List[Dict[str, Any]] = []
    for i, pub in enumerate(author.get("publications", [])):
        if i >= max_pubs:
            break

        bib = pub.get("bib", {})
        title = (bib.get("title") or "").strip() or "(untitled)"
        authors = (bib.get("author") or "").strip()
        venue = (bib.get("venue") or bib.get("journal") or bib.get("publisher") or "").strip()
        year = str(bib.get("pub_year") or bib.get("year") or "").strip()

        url: Optional[str] = None
        try:
            pub_filled = scholarly.fill(pub)
            url = (
                pub_filled.get("pub_url")
                or pub_filled.get("eprint_url")
                or (pub_filled.get("eprint") or {}).get("url")
            )
        except Exception:
            pass

        pubs.append({"title": title, "authors": authors, "venue": venue, "year": year, "url": url})
        time.sleep(delay)

    def sort_key(p):  # sort by year desc
        try:
            return int(p["year"])
        except Exception:
            return -1

    pubs.sort(key=sort_key, reverse=True)
    return pubs

def escape_html(s: str) -> str:
    return (
        s.replace("&", "&amp;")
         .replace("<", "&lt;")
         .replace(">", "&gt;")
         .replace('"', "&quot;")
    )

def render_li(pub: Dict[str, Any]) -> str:
    title = escape_html(pub["title"])
    if pub.get("url"):
        title_html = f'<a href="{pub["url"]}" target="_blank" rel="noopener">{title}</a>'
    else:
        title_html = title

    parts = []
    if pub["authors"]:
        parts.append(escape_html(pub["authors"]))
    parts.append(f'“{title_html}”')

    venue_bits = []
    if pub["venue"]:
        venue_bits.append(escape_html(pub["venue"]))
    if pub["year"]:
        venue_bits.append(pub["year"])
    if venue_bits:
        parts.append(", ".join(venue_bits))

    return f"<li>{'; '.join(parts)}</li>"

def build_html_list(pubs: List[Dict[str, Any]]) -> str:
    items = "\n".join(render_li(p) for p in pubs)
    return f'<ol class="pub-list">\n{items}\n</ol>\n'

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--user-id", required=True, help="Google Scholar user ID")
    ap.add_argument("--output", default="pub.html", help="Output HTML file (default: pub.html)")
    ap.add_argument("--max", type=int, default=200)
    args = ap.parse_args()

    print(f"→ Fetching publications for user {args.user_id} ...")
    pubs = fetch_publications(args.user_id, max_pubs=args.max)
    if not pubs:
        print("× No publications found.")
        sys.exit(1)

    html_block = build_html_list(pubs)

    with open(args.output, "w", encoding="utf-8") as f:
        f.write(html_block)
    print(f"✓ Wrote {len(pubs)} publications to {args.output}")

if __name__ == "__main__":
    main()
