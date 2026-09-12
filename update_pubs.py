#!/usr/bin/env python3
"""
Generate pub.html from Google Scholar and cache reusable figures from supported
open-access publishers.

Usage:
  python update_pubs.py --user-id YOUR_SCHOLAR_ID
  python update_pubs.py --user-id YOUR_SCHOLAR_ID --refresh-figures

Figure extraction is deliberately conservative. Unsupported publications keep
their citation and simply render without figures.
"""

import argparse
import hashlib
import html
import json
import re
import sys
import time
import xml.etree.ElementTree as ET
from pathlib import Path
from typing import Any, Dict, List, Optional
from urllib.error import HTTPError, URLError
from urllib.parse import urlsplit
from urllib.request import Request, urlopen

from PIL import Image  # pip install Pillow==10.2.0
from scholarly import scholarly  # pip install scholarly==1.7.11


USER_AGENT = "DavidRisticPublicationUpdater/1.0 (+https://davidristic.com)"
XLINK = "http://www.w3.org/1999/xlink"
DOI_PATTERN = re.compile(r"10\.\d{4,9}/[-._;()/:A-Z0-9]+", re.IGNORECASE)
THUMBNAIL_MAX_SIZE = (480, 480)


def normalize_space(value: str) -> str:
    return " ".join(value.split())


def extract_doi(*values: Optional[str]) -> str:
    for value in values:
        if not value:
            continue
        match = DOI_PATTERN.search(value)
        if match:
            return match.group(0).rstrip(".,;)").lower()
    return ""


def fetch_url(url: str, accept: str = "*/*", timeout: int = 30) -> tuple[bytes, str]:
    request = Request(
        url,
        headers={"Accept": accept, "User-Agent": USER_AGENT},
    )
    with urlopen(request, timeout=timeout) as response:
        return response.read(), response.headers.get_content_type()


def resolve_url(url: str, timeout: int = 30) -> str:
    request = Request(url, headers={"User-Agent": USER_AGENT})
    with urlopen(request, timeout=timeout) as response:
        return response.geturl()


def fetch_publications(
    user_id: str,
    max_pubs: int = 200,
    delay: float = 0.25,
) -> List[Dict[str, Any]]:
    """Fetch publication metadata from Google Scholar, newest first."""
    author = scholarly.search_author_id(user_id)
    author = scholarly.fill(author, sections=["publications"])

    publications: List[Dict[str, Any]] = []
    for index, publication in enumerate(author.get("publications", [])):
        if index >= max_pubs:
            break

        bib = publication.get("bib", {})
        title = (bib.get("title") or "").strip() or "(untitled)"
        authors = (bib.get("author") or "").strip()
        venue = (
            bib.get("venue")
            or bib.get("journal")
            or bib.get("publisher")
            or ""
        ).strip()
        year = str(bib.get("pub_year") or bib.get("year") or "").strip()

        url: Optional[str] = None
        filled: Dict[str, Any] = {}
        try:
            filled = scholarly.fill(publication)
            url = (
                filled.get("pub_url")
                or filled.get("eprint_url")
                or (filled.get("eprint") or {}).get("url")
            )
        except Exception as error:
            print(f"Warning: could not expand '{title}': {error}", file=sys.stderr)

        filled_bib = filled.get("bib", {}) if filled else {}
        doi = extract_doi(
            str(filled_bib.get("doi") or ""),
            str(bib.get("doi") or ""),
            url,
        )

        publications.append(
            {
                "title": title,
                "authors": authors,
                "venue": venue,
                "year": year,
                "url": url,
                "doi": doi,
                "figures": [],
            }
        )
        time.sleep(delay)

    def sort_key(item: Dict[str, Any]) -> int:
        try:
            return int(item["year"])
        except (TypeError, ValueError):
            return -1

    publications.sort(key=sort_key, reverse=True)
    return publications


def frontiers_xml_url(publication: Dict[str, Any]) -> str:
    url = str(publication.get("url") or "")
    doi = str(publication.get("doi") or "")
    if "frontiersin.org" not in url.lower() and doi.startswith("10.3389/"):
        url = resolve_url(f"https://doi.org/{doi}")

    parsed = urlsplit(url)
    if "frontiersin.org" not in parsed.netloc.lower() or "/articles/" not in parsed.path:
        return ""

    article_path = parsed.path.rstrip("/")
    for suffix in ("/full", "/abstract"):
        if article_path.endswith(suffix):
            article_path = article_path[: -len(suffix)]
            break
    return f"{parsed.scheme or 'https'}://{parsed.netloc}{article_path}/xml/nlm"


def frontiers_article_id(publication: Dict[str, Any]) -> str:
    doi = str(publication.get("doi") or "")
    if doi.startswith("10.3389/"):
        candidate = doi.rsplit(".", 1)[-1]
        if candidate.isdigit():
            return candidate

    url = str(publication.get("url") or "")
    match = re.search(r"10\.3389/[^/?#]+\.([0-9]+)", url, re.IGNORECASE)
    return match.group(1) if match else ""


def license_metadata(root: ET.Element) -> tuple[str, str]:
    license_node = root.find(".//license")
    if license_node is None:
        return "", ""

    license_url = license_node.attrib.get(f"{{{XLINK}}}href", "")
    if license_url.startswith("http://creativecommons.org/"):
        license_url = "https://" + license_url[len("http://"):]
    license_text = normalize_space("".join(license_node.itertext()))
    if "creativecommons.org/licenses/by/" in license_url:
        return "CC BY", license_url
    return license_text[:80], license_url


def create_thumbnail(source: Path, destination: Path) -> None:
    destination.parent.mkdir(parents=True, exist_ok=True)
    with Image.open(source) as image:
        image.thumbnail(THUMBNAIL_MAX_SIZE, Image.Resampling.LANCZOS)
        if image.mode not in ("RGB", "RGBA"):
            image = image.convert("RGB")
        image.save(destination, format="WEBP", quality=80, method=6)


def discover_frontiers_figures(
    publication: Dict[str, Any],
    figures_root: Path,
    refresh: bool = False,
    max_figures: int = 12,
) -> List[Dict[str, str]]:
    xml_url = frontiers_xml_url(publication)
    article_id = frontiers_article_id(publication)
    if not xml_url or not article_id:
        return []

    xml_bytes, _ = fetch_url(xml_url, accept="application/xml,text/xml")
    root = ET.fromstring(xml_bytes)
    license_name, license_url = license_metadata(root)

    article_dir = figures_root / f"frontiers-{article_id}"
    article_dir.mkdir(parents=True, exist_ok=True)
    figures: List[Dict[str, str]] = []

    for figure_node in root.findall(".//fig")[:max_figures]:
        graphic = figure_node.find(".//graphic")
        if graphic is None:
            continue

        href = graphic.attrib.get(f"{{{XLINK}}}href", "")
        if not href:
            continue

        label_node = figure_node.find("./label")
        caption_node = figure_node.find("./caption")
        label = normalize_space("".join(label_node.itertext())) if label_node is not None else "Figure"
        caption = normalize_space("".join(caption_node.itertext())) if caption_node is not None else ""
        image_stem = Path(href).stem
        filename = f"{image_stem}.webp"
        local_file = article_dir / filename
        thumbnail_file = article_dir / "thumbnails" / filename
        image_url = (
            f"https://www.frontiersin.org/files/Articles/{article_id}/"
            f"xml-images/{filename}"
        )

        if refresh or not local_file.exists():
            image_bytes, content_type = fetch_url(image_url, accept="image/webp,image/*")
            if not content_type.startswith("image/"):
                raise ValueError(f"Unexpected content type for {image_url}: {content_type}")
            local_file.write_bytes(image_bytes)

        if refresh or not thumbnail_file.exists():
            create_thumbnail(local_file, thumbnail_file)

        figures.append(
            {
                "label": label,
                "caption": caption,
                "image": f"/assets/research/figures/frontiers-{article_id}/{filename}",
                "thumbnail": (
                    f"/assets/research/figures/frontiers-{article_id}/"
                    f"thumbnails/{filename}"
                ),
                "source": str(publication.get("url") or ""),
                "license": license_name,
                "license_url": license_url,
            }
        )

    return figures


def manifest_key(publication: Dict[str, Any]) -> str:
    return str(
        publication.get("doi")
        or publication.get("url")
        or publication.get("title")
        or ""
    ).lower()


def load_manifest(path: Path) -> Dict[str, Any]:
    if not path.exists():
        return {"version": 1, "publications": {}}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return {"version": 1, "publications": {}}
    data.setdefault("version", 1)
    data.setdefault("publications", {})
    return data


def cached_files_exist(figures: List[Dict[str, str]], project_root: Path) -> bool:
    if not figures:
        return False
    return all(
        item.get("thumbnail")
        and (project_root / item["image"].lstrip("/")).exists()
        and (project_root / item["thumbnail"].lstrip("/")).exists()
        for item in figures
    )


def add_figures(
    publications: List[Dict[str, Any]],
    figures_root: Path,
    manifest_path: Path,
    project_root: Path,
    refresh: bool = False,
    max_figures: int = 12,
) -> None:
    manifest = load_manifest(manifest_path)
    cache = manifest["publications"]

    for publication in publications:
        key = manifest_key(publication)
        cached = cache.get(key, {}).get("figures", [])
        if not refresh and cached_files_exist(cached, project_root):
            publication["figures"] = cached
            print(f"Figures: cached for '{publication['title']}'")
            continue

        try:
            figures = discover_frontiers_figures(
                publication,
                figures_root=figures_root,
                refresh=refresh,
                max_figures=max_figures,
            )
        except (HTTPError, URLError, ET.ParseError, OSError, ValueError) as error:
            if cached_files_exist(cached, project_root):
                publication["figures"] = cached
                print(
                    f"Warning: figure refresh failed; using cache for '{publication['title']}': {error}",
                    file=sys.stderr,
                )
            else:
                print(
                    f"Warning: figures unavailable for '{publication['title']}': {error}",
                    file=sys.stderr,
                )
            continue

        publication["figures"] = figures
        if figures:
            cache[key] = {
                "title": publication["title"],
                "doi": publication.get("doi", ""),
                "figures": figures,
            }
            print(f"Figures: found {len(figures)} for '{publication['title']}'")

    manifest_path.parent.mkdir(parents=True, exist_ok=True)
    manifest_path.write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )


def render_figure(figure: Dict[str, str]) -> str:
    label = html.escape(figure.get("label") or "Figure")
    caption = html.escape(figure.get("caption") or "")
    image = html.escape(figure["image"], quote=True)
    thumbnail = html.escape(figure.get("thumbnail") or figure["image"], quote=True)
    source = html.escape(figure.get("source") or "", quote=True)
    license_name = html.escape(figure.get("license") or "")
    license_url = html.escape(figure.get("license_url") or "", quote=True)

    return (
        '<figure class="pub-figure-card">\n'
        f'  <button class="pub-figure-trigger" type="button" '
        f'aria-label="Open {label} at full size" '
        f'data-label="{label}" data-caption="{caption}" '
        f'data-full-src="{image}" data-source="{source}" '
        f'data-license="{license_name}" data-license-url="{license_url}">\n'
        f'    <img src="{thumbnail}" alt="" loading="lazy" decoding="async">\n'
        '  </button>\n'
        f'  <figcaption>{label}</figcaption>\n'
        f'</figure>'
    )


def render_figure_preview(figures: List[Dict[str, str]]) -> str:
    preview_items = []
    for figure in figures[:3]:
        thumbnail = html.escape(figure.get("thumbnail") or figure["image"], quote=True)
        preview_items.append(
            '<span class="pub-figures-preview-item">'
            f'<img src="{thumbnail}" alt="" loading="lazy" decoding="async">'
            '</span>'
        )
    return "".join(preview_items)


def render_figures(figures: List[Dict[str, str]], gallery_id: str) -> str:
    if not figures:
        return ""

    gallery_items = "\n".join(render_figure(item) for item in figures)
    preview_items = render_figure_preview(figures)
    return (
        '<section class="pub-figures" aria-label="Publication figures">\n'
        f'  <button class="pub-figures-toggle" type="button" '
        f'aria-expanded="false" aria-controls="{gallery_id}">\n'
        f'    <span class="pub-figures-preview" aria-hidden="true">{preview_items}</span>\n'
        '    <span class="pub-figures-toggle-label">'
        '<span data-figures-toggle-label>Show figures</span>'
        '<span class="pub-figures-chevron" aria-hidden="true"></span>'
        '</span>\n'
        '  </button>\n'
        f'  <div class="pub-figures-panel" id="{gallery_id}" aria-hidden="true" hidden inert>\n'
        '    <div class="pub-figures-panel-inner">\n'
        f'      <div class="pub-figure-grid">\n{gallery_items}\n      </div>\n'
        '    </div>\n'
        '  </div>\n'
        '</section>'
    )


def render_li(publication: Dict[str, Any]) -> str:
    title = html.escape(publication["title"])
    url = str(publication.get("url") or "")
    if url:
        safe_url = html.escape(url, quote=True)
        title_html = (
            f'<a href="{safe_url}" target="_blank" rel="noopener">{title}</a>'
        )
    else:
        title_html = title

    parts = [f'“{title_html}”']
    if publication.get("authors"):
        parts.append(html.escape(publication["authors"]))
    if publication.get("venue"):
        parts.append(html.escape(publication["venue"]))
    if publication.get("year"):
        parts.append(html.escape(str(publication["year"])))

    doi_attr = ""
    if publication.get("doi"):
        doi_attr = (
            f' data-doi="{html.escape(publication["doi"], quote=True)}"'
        )

    citation = ", ".join(parts) + "."
    gallery_key = manifest_key(publication).encode("utf-8")
    gallery_id = f"publication-figures-{hashlib.sha1(gallery_key).hexdigest()[:10]}"
    figures = render_figures(publication.get("figures", []), gallery_id)
    return (
        f'<li{doi_attr}>\n'
        f'  <div class="pub-citation">{citation}</div>\n'
        f'{figures}\n'
        f'</li>'
    )


def build_html_list(publications: List[Dict[str, Any]]) -> str:
    items = "\n".join(render_li(publication) for publication in publications)
    return f'<ol class="pub-list" reversed>\n{items}\n</ol>\n'


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--user-id", required=True, help="Google Scholar user ID")
    parser.add_argument("--output", default="pub.html", help="Output HTML file")
    parser.add_argument("--max", type=int, default=200)
    parser.add_argument(
        "--skip-figures",
        action="store_true",
        help="Do not discover or refresh figures",
    )
    parser.add_argument(
        "--refresh-figures",
        action="store_true",
        help="Redownload cached figures",
    )
    parser.add_argument("--max-figures", type=int, default=12)
    parser.add_argument("--figures-dir", default="assets/research/figures")
    parser.add_argument(
        "--manifest",
        default="assets/research/figures/manifest.json",
    )
    args = parser.parse_args()
    project_root = Path(__file__).resolve().parent

    def project_path(value: str) -> Path:
        path = Path(value)
        return path if path.is_absolute() else project_root / path

    print(f"Fetching publications for user {args.user_id} ...")
    publications = fetch_publications(args.user_id, max_pubs=args.max)
    if not publications:
        print("No publications found.", file=sys.stderr)
        sys.exit(1)

    if not args.skip_figures:
        add_figures(
            publications,
            figures_root=project_path(args.figures_dir),
            manifest_path=project_path(args.manifest),
            project_root=project_root,
            refresh=args.refresh_figures,
            max_figures=args.max_figures,
        )

    output = project_path(args.output)
    output.write_text(build_html_list(publications), encoding="utf-8")
    print(f"Wrote {len(publications)} publications to {output}")


if __name__ == "__main__":
    main()
