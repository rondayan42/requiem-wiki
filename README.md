# Requiem Wiki (2009) – Static Rebuild

A static, searchable rebuild of the 2009 community wiki for Requiem: Bloodymare / Desiderium Mortis.

- Input: archived HTML mirrors in `requiem-wiki.org/` and `dridriou.free.fr/`.
- Output: modern static site in `site/` with new CSS, header, and client‑side search.
- Dead/archival error pages are skipped automatically.
- Categories are rebuilt from the original pages and enhanced with a curated taxonomy (Equipment, Weapons, Classes, Skills, Quests, Monsters, Character, World, Downloads, Consumables, Guides). Breadcrumbs show an article’s categories.

## Quick start

1) Install Python 3.9+ (3.11 recommended) and BeautifulSoup.

```bash
pip install beautifulsoup4
```

2) Build the site:

```bash
python build.py
```

3) Open the site:

- Double‑click `site/index.html` (file://). Search works offline via `site/search-index.js`.
- Or serve locally:

```bash
python -m http.server 9000 -d site
# then visit http://localhost:9000
```

## Project layout

```
build.py                # Builder: parses archive, skips dead pages, writes site/
site/                   # Generated static website (commit/publish this)
templates/              # HTML/CSS/JS used by the builder
  page.html             # Base page template
  assets/style.css      # Dark theme styling
  assets/search.js      # Search + suggestions (works online and file://)
requiem-wiki.org/       # Raw mirror (ignored by .gitignore)
dridriou.free.fr/       # Raw mirror (ignored by .gitignore)
.gitignore              # Keeps site/, ignores mirrors/caches
```

## Search and suggestions

- As you type, a suggestion panel shows the top 20 matches.
- Press Enter to go to the best match. Matching is token‑based with fuzzy ranking (title weighted higher than content).
- When opened via `file://`, search auto‑loads `site/search-index.js`. When served via HTTP, it uses `site/search-index.json`.

## Categories

- Original MediaWiki categories and subcategories are parsed from the mirrored pages.
- Curated categories are added automatically based on article titles (e.g., EXP Chart → Character, Places/Dungeons → World).
- Pages for referenced subcategories are generated even if the original HTML is missing, so links don’t break.

### Tuning the taxonomy

Edit these in `build.py`:

- `curated_roots_order`: controls the list and order of featured categories on `Categories.html`.
- `curated_taxonomy`: regex rules mapping article titles to curated categories.

Run `python build.py` again after changes.

## Deploying to GitHub Pages

Option A – `gh-pages` branch (recommended)
- Create a branch `gh-pages` whose root contains the contents of `site/`.
- In repository Settings → Pages, choose “Deploy from a branch”, branch `gh-pages`, folder `/`.

Option B – `docs/` folder
- Copy the contents of `site/` into a `docs/` folder.
- In Settings → Pages, choose “Deploy from a branch”, branch `main`, folder `/docs`.

> `.gitignore` keeps mirrors and caches out of the repo but keeps `site/` by default. If you deploy from `docs/`, you can safely keep both `site/` and `docs/` or change the builder to write into `docs/`.

## Troubleshooting

- Some images/links are missing: this is expected where the archive didn’t capture them.
- Category link 404: rebuild (`python build.py`). The builder pre‑creates referenced subcategories and curated categories.
- Search not showing suggestions from file://: refresh the page; it loads `search-index.js` offline.

---
Code for the builder and theme is MIT‑style; archived content remains the property of their original authors and license holders.
