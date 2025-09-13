#!/usr/bin/env python3
import os
import re
import json
import shutil
from pathlib import Path
from html import unescape
from bs4 import BeautifulSoup  # type: ignore


ROOT = Path(__file__).parent
SRC_DIRS = [
    ROOT / "dridriou.free.fr" / "Requiem_Wiki" / "requiem-wiki.org" / "wiki",
    ROOT / "requiem-wiki.org" / "wiki",
]
SITE_DIR = ROOT / "site"
ASSETS_DIR = SITE_DIR / "assets"
CATEGORIES_DIR = SITE_DIR / "categories"
PAGES_DIR = SITE_DIR / "pages"


ERROR_TITLE_PATTERNS = [
    re.compile(r"Web server is down", re.I),
    re.compile(r"Error code\s*5\d\d", re.I),
    re.compile(r"Erreur\s*404|404\s*Not\s*Found|Free Pages Personnelles", re.I),
]


def is_error_page(soup: BeautifulSoup) -> bool:
    title = soup.find("title")
    title_text = title.get_text(strip=True) if title else ""
    for pat in ERROR_TITLE_PATTERNS:
        if pat.search(title_text or ""):
            return True
    # Cloudflare block signature
    if soup.find(id="cf-wrapper") or soup.find(string=re.compile(r"Cloudflare Ray ID", re.I)):
        return True
    return False


def extract_article(soup: BeautifulSoup) -> dict | None:
    # MediaWiki typical structure
    content = soup.select_one("#content #bodyContent") or soup.select_one("#content") or soup.select_one("#bodyContent")
    heading = soup.select_one("h1.firstHeading") or soup.find("h1")
    if not content or not heading:
        return None

    # Remove non-article UI elements inside content
    for sel in ["#jump-to-nav", ".printfooter", "#catlinks", ".toc"]:
        for el in content.select(sel):
            el.decompose()

    # Normalize links to local .html files
    for a in content.find_all("a"):
        href = a.get("href")
        if not href:
            continue
        # Skip external links
        if href.startswith("http://") or href.startswith("https://"):
            continue
        # Normalize same-folder wiki links
        if href.endswith(".html"):
            a["href"] = os.path.basename(href)

    title = heading.get_text(strip=True)
    article_html = str(content)
    # Also extract plain text for search
    article_text = content.get_text(" ", strip=True)
    return {"title": title, "html": article_html, "text": article_text}


def is_category_page(soup: BeautifulSoup) -> bool:
    body = soup.find("body")
    if body and any(cls.startswith("ns-14") for cls in (body.get("class") or [])):
        return True
    h1 = soup.select_one("h1.firstHeading")
    if h1 and h1.get_text(strip=True).startswith("Category:"):
        return True
    return False


def normalize_category_name(name: str) -> str:
    if name.startswith("Category:"):
        return name.split(":", 1)[1].strip()
    return name.strip()


def to_safe_name(title: str) -> str:
    return (re.sub(r"[^A-Za-z0-9_\-]+", "_", title).strip("_") or "page")


def category_output_filename(category_name: str) -> str:
    base = to_safe_name(f"Category_{category_name}")
    return f"{base}.html"


def write_page(output_path: Path, title: str, body_html: str, *, asset_prefix: str = "", breadcrumbs_html: str = ""):
    template = (ROOT / "templates" / "page.html").read_text(encoding="utf-8")
    html = (
        template
        .replace("{{TITLE}}", unescape(title))
        .replace("{{BODY}}", body_html)
        .replace("{{ASSET_PREFIX}}", asset_prefix)
        .replace("{{BREADCRUMBS}}", breadcrumbs_html or "")
    )
    output_path.write_text(html, encoding="utf-8")


def ensure_assets():
    ASSETS_DIR.mkdir(parents=True, exist_ok=True)
    PAGES_DIR.mkdir(parents=True, exist_ok=True)
    # Copy static files from templates/assets
    src_assets = ROOT / "templates" / "assets"
    if src_assets.exists():
        for item in src_assets.iterdir():
            dst = ASSETS_DIR / item.name
            if item.is_dir():
                if dst.exists():
                    shutil.rmtree(dst)
                shutil.copytree(item, dst)
            else:
                shutil.copy2(item, dst)


def build():
    if SITE_DIR.exists():
        shutil.rmtree(SITE_DIR)
    SITE_DIR.mkdir(parents=True, exist_ok=True)

    ensure_assets()
    CATEGORIES_DIR.mkdir(parents=True, exist_ok=True)

    search_index: list[dict] = []
    a_to_z: dict[str, list[dict]] = {}
    categories: dict[str, list[dict]] = {}

    # Process sources in priority order
    seen_titles: set[str] = set()
    article_title_to_filename: dict[str, str] = {}
    article_title_to_categories: dict[str, set[str]] = {}

    for base in SRC_DIRS:
        if not base.exists():
            continue
        for path in base.rglob("*.html"):
            try:
                html = path.read_text(encoding="utf-8", errors="ignore")
            except Exception:
                continue
            soup = BeautifulSoup(html, "html.parser")
            if is_error_page(soup):
                continue
            article = extract_article(soup)
            if not article:
                continue
            title = article["title"]
            if not title or title in seen_titles:
                continue

            seen_titles.add(title)
            safe_name = to_safe_name(title)
            # bucket by first char to avoid >1000 files per folder
            first_char = safe_name[0].upper() if safe_name else "#"
            if not ("A" <= first_char <= "Z"):
                first_char = "0-9"
            out_dir = PAGES_DIR / first_char
            out_dir.mkdir(parents=True, exist_ok=True)
            out_path = out_dir / f"{safe_name}.html"
            # breadcrumbs fill later once categories are known
            # compute asset prefix based on depth relative to SITE_DIR
            depth = len(out_path.relative_to(SITE_DIR).parts) - 1  # minus filename
            asset_prefix = "../" * depth
            write_page(out_path, title, article["html"], asset_prefix=asset_prefix)  # type: ignore[arg-type]
            url_rel = out_path.relative_to(SITE_DIR).as_posix()
            article_title_to_filename[title] = url_rel

            # Build search index entry
            search_index.append({
                "title": title,
                "url": url_rel,
                "content": article["text"],  # type: ignore[index]
            })

            # A-Z listing bucket
            first = title[0].upper()
            if not first.isalpha():
                first = "#"
            a_to_z.setdefault(first, []).append({"title": title, "url": url_rel})

            # Categories: infer from footer catlinks if present in raw html
            for catlink in soup.select("#catlinks a[title^='Category:']"):
                cat = normalize_category_name(catlink.get("title", catlink.get_text(strip=True)))
                categories.setdefault(cat, []).append({"title": title, "url": url_rel})
                article_title_to_categories.setdefault(title, set()).add(cat)

    # Pass 2: Parse category pages to build hierarchy (subcategories + pages)
    category_graph: dict[str, dict[str, set[str]]] = {}
    # {cat: {"subcats": set[str], "pages": set[str]}}

    for base in SRC_DIRS:
        if not base.exists():
            continue
        for path in base.rglob("Category_*.html"):
            try:
                html = path.read_text(encoding="utf-8", errors="ignore")
            except Exception:
                continue
            soup = BeautifulSoup(html, "html.parser")
            if is_error_page(soup) or not is_category_page(soup):
                continue
            h1 = soup.select_one("h1.firstHeading")
            if not h1:
                continue
            raw_title = h1.get_text(strip=True)
            cat_name = normalize_category_name(raw_title)
            node = category_graph.setdefault(cat_name, {"subcats": set(), "pages": set()})

            # Subcategories
            sub_wrap = soup.select_one('#mw-subcategories')
            if sub_wrap:
                for a in sub_wrap.select('a[title^="Category:"]'):
                    sub_name = normalize_category_name(a.get("title", a.get_text(strip=True)))
                    if sub_name:
                        node["subcats"].add(sub_name)
                        # Ensure a node exists for subcategory so we generate a page even if its source HTML is missing
                        category_graph.setdefault(sub_name, {"subcats": set(), "pages": set()})

            # Pages in category
            pages_wrap = soup.select_one('#mw-pages')
            if pages_wrap:
                for a in pages_wrap.select('a[title]'):
                    page_title = a.get("title", a.get_text(strip=True))
                    if page_title:
                        node["pages"].add(page_title)

    # Merge page-derived categories into graph
    for cat_name, items in categories.items():
        node = category_graph.setdefault(cat_name, {"subcats": set(), "pages": set()})
        for it in items:
            node["pages"].add(it["title"])  # type: ignore[index]

    # Sort listings
    for k in a_to_z:
        a_to_z[k].sort(key=lambda x: x["title"].lower())
    for k in categories:
        categories[k].sort(key=lambda x: x["title"].lower())

    # Write index files
    (SITE_DIR / "search-index.json").write_text(json.dumps(search_index, ensure_ascii=False), encoding="utf-8")
    # Also emit JS wrapper for file:// usage
    (SITE_DIR / "search-index.js").write_text("window.SEARCH_INDEX=" + json.dumps(search_index, ensure_ascii=False) + ";", encoding="utf-8")

    # A-Z page
    az_html_parts = ["<div class=\"az\">"]
    for letter in sorted(a_to_z.keys()):
        az_html_parts.append(f"<h2>{letter}</h2><ul>")
        for item in a_to_z[letter]:
            az_html_parts.append(f"<li><a href=\"{item['url']}\">{item['title']}</a></li>")
        az_html_parts.append("</ul>")
    az_html_parts.append("</div>")
    write_page(SITE_DIR / "A-Z.html", "A–Z Index", "".join(az_html_parts), asset_prefix="")

    # Generate per-category pages and hierarchical Categories index
    # Helper to resolve page title -> url if present
    def resolve_page_url(title: str) -> str | None:
        if title in article_title_to_filename:
            return article_title_to_filename[title]
        # Try underscore/space variants
        alt = title.replace("_", " ") if "_" in title else title.replace(" ", "_")
        return article_title_to_filename.get(alt)

    # Curated taxonomy rules (title-based regex mapping)
    curated_taxonomy: list[tuple[re.Pattern[str], str]] = [
        # Map gear-like titles to Equipment (aligns with original wiki wording)
        (re.compile(r"\b(Armor|Armors|Cloth|Leather|Plate|Shield|Shields|Jewelry|Equipment Set)s?\b", re.I), "Equipment"),
        (re.compile(r"\b(Claws|Crossbows|Dual Swords|Knuckles|Launcher|Staves|Two Handed|One Handed|Wands)\b", re.I), "Weapons"),
        (re.compile(r"\b(Quest|Quest:|Quests)\b", re.I), "Quests"),
        (re.compile(r"\b(Monster|Monsters|MOB|Drop|Mob item drops)\b", re.I), "Monsters"),
        (re.compile(r"\b(Skill|Skills|DNA)\b", re.I), "Skills"),
        (re.compile(r"\b(Stat|Stats|EXP|EXP Chart|Level|Levels|Leveling|Leveling Spots)\b", re.I), "Character"),
        (re.compile(r"\b(World|Map|World Map|Place|Places|Dungeon|Dungeons)\b", re.I), "World"),
        (re.compile(r"\b(Client|Patch|Patches|Downloads?)\b", re.I), "Downloads"),
        (re.compile(r"\b(Xeons|Waters|Consumables?|Potion|Potions|Elixir|Elixirs)\b", re.I), "Consumables"),
        (re.compile(r"\b(Build|Builds|Guide|Guides?)\b", re.I), "Guides"),
        (re.compile(r"\b(Class|Rogue|Warrior|Shaman|Mystic|Templar|Radiant|Assassin|Avenger|Berserker|Commander|Defender|Defiler|Dominator|Druid|Elementalist|Forsaker|Protector|Shadow Runner|Soul Hunter)\b", re.I), "Classes"),
    ]

    # Apply curated taxonomy to every article title
    for title, url in list(article_title_to_filename.items()):
        for pat, curated_cat in curated_taxonomy:
            if pat.search(title):
                categories.setdefault(curated_cat, []).append({"title": title, "url": url})
                article_title_to_categories.setdefault(title, set()).add(curated_cat)

    # Merge newly added (curated) categories into the graph as page lists
    for cat_name, items in categories.items():
        node = category_graph.setdefault(cat_name, {"subcats": set(), "pages": set()})
        for it in items:
            node["pages"].add(it["title"])  # type: ignore[index]

    # Helper to render a category page body with correct link prefix for articles
    def render_category_body(cat_name: str, node: dict[str, set[str]], page_link_prefix: str) -> str:
        body_parts: list[str] = []
        body_parts.append(f"<div class=\"category\"><h2>Category: {cat_name}</h2>")
        # Subcategories (relative to current file location)
        if node["subcats"]:
            body_parts.append("<h3>Subcategories</h3><ul>")
            for sub in sorted(node["subcats"], key=lambda s: s.lower()):
                href = category_output_filename(sub)
                body_parts.append(f"<li><a href=\"{href}\">{sub}</a></li>")
            body_parts.append("</ul>")
        # Pages (article links may live at site root; add prefix when needed)
        if node["pages"]:
            body_parts.append("<h3>Pages</h3><ul>")
            for p in sorted(node["pages"], key=lambda s: s.lower()):
                url = resolve_page_url(p)
                if url:
                    body_parts.append(f"<li><a href=\"{page_link_prefix}{url}\">{p}</a></li>")
            body_parts.append("</ul>")
        body_parts.append("</div>")
        return "".join(body_parts)

    # Write individual category pages
    for cat_name in sorted(category_graph.keys(), key=lambda s: s.lower()):
        node = category_graph[cat_name]
        # Under categories/ (CSS uses ../, article links use ../)
        body_cats = render_category_body(cat_name, node, page_link_prefix="../")
        write_page(CATEGORIES_DIR / category_output_filename(cat_name), f"Category: {cat_name}", body_cats, asset_prefix="../")
        # Root copy (no prefixes)
        body_root = render_category_body(cat_name, node, page_link_prefix="")
        write_page(SITE_DIR / category_output_filename(cat_name), f"Category: {cat_name}", body_root, asset_prefix="")

    # Determine top-level categories (not a subcategory of any other)
    all_cats = set(category_graph.keys())
    child_cats = set()
    for node in category_graph.values():
        child_cats.update(node["subcats"])
    roots_set = (all_cats - child_cats) or all_cats
    # Curated category list (always show, even empty)
    curated_roots_order = [
        "Equipment", "Armors", "Jewelry", "Shields", "Weapons",
        "Classes", "Skills", "Quests", "Monsters", "Character",
        "World", "Downloads", "Consumables", "Guides",
    ]
    for c in curated_roots_order:
        category_graph.setdefault(c, {"subcats": set(), "pages": set()})
    curated_present = curated_roots_order[:]
    # Ensure pages exist for curated categories (write/overwrite is fine)
    for cat_name in curated_present:
        node = category_graph.get(cat_name, {"subcats": set(), "pages": set()})
        body_cats = render_category_body(cat_name, node, page_link_prefix="../")
        write_page(CATEGORIES_DIR / category_output_filename(cat_name), f"Category: {cat_name}", body_cats, asset_prefix="../")
        body_root = render_category_body(cat_name, node, page_link_prefix="")
        write_page(SITE_DIR / category_output_filename(cat_name), f"Category: {cat_name}", body_root, asset_prefix="")

    roots = sorted(list(roots_set), key=lambda s: s.lower())

    # Render tree
    def render_tree(cat: str) -> str:
        node = category_graph.get(cat, {"subcats": set(), "pages": set()})
        html_parts = [f"<li><a href=\"categories/{category_output_filename(cat)}\">{cat}</a>"]
        children = sorted(node["subcats"], key=lambda s: s.lower())
        if children:
            html_parts.append("<ul>")
            for sub in children:
                html_parts.append(render_tree(sub))
            html_parts.append("</ul>")
        html_parts.append("</li>")
        return "".join(html_parts)

    cat_index_parts = ["<div class=\"categories\">", "<p>Browse by category and subcategory.</p>"]
    if curated_present:
        cat_index_parts.append("<h3>Featured</h3><ul>")
        for c in curated_present:
            cat_index_parts.append(f"<li><a href=\"categories/{category_output_filename(c)}\">{c}</a></li>")
        cat_index_parts.append("</ul>")
    # Legacy categories collapsed
    legacy = [r for r in roots if r not in set(curated_present)]
    if legacy:
        cat_index_parts.append("<details><summary>Legacy</summary><ul>")
        for r in legacy:
            cat_index_parts.append(render_tree(r))
        cat_index_parts.append("</ul></details>")
    cat_index_parts.append("</div>")
    write_page(SITE_DIR / "Categories.html", "Categories", "".join(cat_index_parts), asset_prefix="")

    # After categories are finalized, add breadcrumbs to article pages
    for title, filename in article_title_to_filename.items():
        cats = sorted(article_title_to_categories.get(title, []), key=lambda s: s.lower())
        if cats:
            crumbs = ["<div class=\"breadcrumbs\">Categories:"]
            parts = []
            for c in cats[:5]:  # cap to avoid very long lines
                parts.append(f"<a href=\"categories/{category_output_filename(c)}\">{c}</a>")
            crumbs.append(" <span class=\"sep\">|</span> ".join(parts))
            crumbs.append("</div>")
            # Re-read the body that was written earlier and rewrite page with breadcrumbs
            page_path = SITE_DIR / Path(filename)
            # Retrieve original body by re-parsing the built page body section would be complex; instead, reconstruct from source again
            # Find original source soup by searching both src dirs
            source_html = None
            for base in SRC_DIRS:
                src_guess1 = base / (title + ".html")
                if src_guess1.exists():
                    source_html = src_guess1.read_text(encoding="utf-8", errors="ignore")
                    break
            if source_html:
                soup = BeautifulSoup(source_html, "html.parser")
                article = extract_article(soup)
                if article:
                    # compute asset prefix for nested pages
                    depth = len(page_path.relative_to(SITE_DIR).parts) - 1
                    asset_prefix = "../" * depth
                    write_page(page_path, title, article["html"], asset_prefix=asset_prefix, breadcrumbs_html="".join(crumbs))  # type: ignore[arg-type]

    # Home page (for site/)
    home_html = """
    <div class="home">
      <p>Rebuilt static archive of the 2009 Requiem Wiki. Use the search box above, or browse:</p>
      <ul>
        <li><a href="A-Z.html">A–Z Index</a></li>
        <li><a href="Categories.html">Categories</a></li>
      </ul>
    </div>
    """
    write_page(SITE_DIR / "index.html", "Requiem Wiki (2009 Archive)", home_html, asset_prefix="")

    # Root-level index that points into site/ for GitHub Pages root deployment
    home_html_root = """
    <div class=\"home\">
      <p>Rebuilt static archive of the 2009 Requiem Wiki. Use the search box above, or browse:</p>
      <ul>
        <li><a href=\"site/A-Z.html\">A–Z Index</a></li>
        <li><a href=\"site/Categories.html\">Categories</a></li>
      </ul>
    </div>
    """
    write_page(ROOT / "index.html", "Requiem Wiki (2009 Archive)", home_html_root, asset_prefix="site/")


if __name__ == "__main__":
    # Check bs4 dependency hint
    try:
        build()
        print(f"Built site to {SITE_DIR}")
    except Exception as e:
        print("Build failed:", e)


