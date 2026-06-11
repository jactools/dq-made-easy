#!/usr/bin/env python3
from __future__ import annotations

import json
import re
import shutil
import sys
from datetime import datetime, timezone
from html import escape as html_escape
from pathlib import Path
from string import Template


UI_ROOT = Path(__file__).resolve().parent.parent
SOURCE_DIR = (UI_ROOT.parent / "docs" / "user-manuals").resolve()
TARGET_DIR = (UI_ROOT / "public" / "user-manuals").resolve()
MANUALS_PUBLIC_BASE = "/user-manuals/"
MANUALS_LOGO_LIGHT = "/assets/dq-made-easy-light.svg"
MANUALS_LOGO_DARK = "/assets/dq-made-easy-dark.svg"


PAGE_SHELL_TEMPLATE = Template(
    r"""<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1" />
  <title>$page_title</title>
  <script>
    (() => {
      const prefersDark = window.matchMedia && window.matchMedia('(prefers-color-scheme: dark)').matches
      document.documentElement.setAttribute('data-theme', prefersDark ? 'dark' : 'light')
    })()
  </script>
  <style>
    :root {
      color-scheme: light dark;
      --font-primary: "Open Sans", -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif;
      --font-mono: "SFMono-Regular", Consolas, "Liberation Mono", Menlo, monospace;
      --color-primary: #1a5999;
      --color-primary-dark: #0d3c63;
      --color-primary-light: #e5f0fa;
      --color-secondary: #f5f5f5;
      --color-text: #333;
      --color-text-light: #666;
      --color-text-lighter: #999;
      --color-border: #ddd;
      --color-success: #28a745;
      --color-warning: #ffc107;
      --color-error: #dc3545;
      --color-bg: #fff;
      --color-bg-dark: #f8f9fa;
      --color-nav-bg: #0d3c63;
      --color-card-bg: #fff;
      --color-footer-bg: #f8f9fa;
      --shadow-sm: 0 1px 2px rgba(0, 0, 0, 0.1);
      --shadow-md: 0 4px 6px rgba(0, 0, 0, 0.1);
    }
    [data-theme="dark"] {
      --color-primary: #4a90e2;
      --color-primary-dark: #2a6fa5;
      --color-primary-light: #1a3a5c;
      --color-secondary: #2d2d2d;
      --color-text: #e0e0e0;
      --color-text-light: #b0b0b0;
      --color-text-lighter: #808080;
      --color-border: #444;
      --color-success: #2ecc71;
      --color-warning: #f39c12;
      --color-error: #e74c3c;
      --color-bg: #121212;
      --color-bg-dark: #1e1e1e;
      --color-nav-bg: #1a3a5c;
      --color-card-bg: #1e1e1e;
      --color-footer-bg: #121212;
      --shadow-sm: 0 1px 2px rgba(0, 0, 0, 0.3);
      --shadow-md: 0 4px 6px rgba(0, 0, 0, 0.3);
    }
    * {
      margin: 0;
      padding: 0;
      box-sizing: border-box;
      transition: background-color 0.3s, color 0.3s, border-color 0.3s;
    }
    html {
      font-size: 16px;
      scroll-behavior: smooth;
    }
    body {
      min-height: 100vh;
      font-family: var(--font-primary);
      line-height: 1.6;
      color: var(--color-text);
      background-color: var(--color-bg);
    }
    h1, h2, h3, h4, h5, h6 {
      font-weight: 600;
      line-height: 1.2;
      margin-bottom: 0.5rem;
      color: var(--color-primary-light);
    }
    h1 { font-size: 2.5rem; }
    h2 { font-size: 2rem; }
    h3 { font-size: 1.75rem; }
    h4 { font-size: 1.5rem; }
    p { margin-bottom: 1rem; }
    a {
      color: var(--color-primary);
      text-decoration: none;
      transition: color 0.2s;
    }
    a:hover {
      color: var(--color-primary-dark);
      text-decoration: underline;
    }
    code {
      font-family: var(--font-mono);
      background: var(--color-secondary);
      padding: 0.2rem 0.4rem;
      border-radius: 4px;
      font-size: 0.9em;
    }
    main {
      min-height: 100vh;
      max-width: 1200px;
      margin: 0 auto;
      padding: 0 1rem 1rem;
      display: flex;
    }
    .manuals-page {
      width: 100%;
      display: grid;
      gap: 1rem;
    }
    .manuals-brand {
      display: flex;
      align-items: center;
      gap: 1rem;
      flex-wrap: wrap;
      padding: 1rem 1.25rem;
      border-radius: 8px;
      background-color: var(--color-nav-bg);
      color: #fff;
      border: 1px solid var(--color-border);
      box-shadow: var(--shadow-sm);
    }
    .manuals-brand-link {
      display: inline-flex;
      align-items: center;
      justify-content: center;
      flex-shrink: 0;
      text-decoration: none;
    }
    .manuals-brand-logo {
      display: block;
      height: 44px;
      width: auto;
      max-width: min(280px, 38vw);
      object-fit: contain;
    }
    .manuals-brand-copy {
      display: flex;
      flex-direction: column;
      gap: 0.1rem;
      min-width: 0;
    }
    .manuals-brand-kicker {
      margin: 0;
      font-size: 0.84rem;
      font-weight: 600;
      color: rgba(255, 255, 255, 0.85);
    }
    .manuals-brand-title {
      margin: 0;
      font-size: 1.5rem;
      font-weight: 700;
      line-height: 1.2;
      color: #fff;
    }
    .manuals-brand-subtitle {
      margin: 0;
      color: rgba(255, 255, 255, 0.85);
      font-size: 0.96rem;
      line-height: 1.35;
    }
    .manuals-summary {
      display: grid;
      gap: 0.55rem;
      padding: 1.25rem;
      border-radius: 8px;
      background: linear-gradient(180deg, var(--color-nav-bg) 0%, var(--color-primary-dark) 100%);
      color: #fff;
      box-shadow: var(--shadow-md);
    }
    .manuals-summary-kicker {
      margin: 0;
      color: var(--color-primary-light);
      font-size: 0.84rem;
      font-weight: 700;
      letter-spacing: 0.08em;
      text-transform: uppercase;
    }
    .manuals-summary-title {
      margin: 0;
      font-size: 2.5rem;
      line-height: 1.1;
      letter-spacing: -0.02em;
      font-weight: 700;
      color: #fff;
    }
    .manuals-summary-copy {
      margin: 0;
      max-width: 72ch;
      color: rgba(255, 255, 255, 0.9);
      font-size: 1rem;
      line-height: 1.55;
    }
    .manuals-section-heading {
      display: grid;
      gap: 0.25rem;
      margin-bottom: 0.75rem;
    }
    .manuals-section-kicker {
      margin: 0;
      color: var(--color-primary);
      font-size: 0.8rem;
      font-weight: 700;
      letter-spacing: 0.08em;
      text-transform: uppercase;
    }
    .manuals-section-heading h2 {
      margin: 0;
      font-size: 1.15rem;
      line-height: 1.25;
      color: var(--color-primary-dark);
    }
    .manuals-search {
      display: flex;
      flex-direction: column;
      gap: 0.75rem;
      padding: 1rem;
      border-radius: 8px;
      border: 1px solid var(--color-border);
      background: var(--color-card-bg);
      box-shadow: var(--shadow-sm);
    }
    .manuals-search-label {
      font-size: 0.95rem;
      font-weight: 600;
      color: var(--color-primary-dark);
    }
    .manuals-search-input {
      width: 100%;
      padding: 0.5rem 1rem;
      border: 1px solid var(--color-border);
      border-radius: 4px;
      font-size: 1rem;
      background-color: var(--color-bg-dark);
      color: var(--color-text);
      font: inherit;
    }
    .manuals-search-input:focus {
      outline: 2px solid color-mix(in srgb, var(--color-primary) 55%, transparent);
      outline-offset: 2px;
    }
    .manuals-search-status {
      margin: 0;
      color: var(--color-text-light);
      font-size: 0.92rem;
    }
    .manuals-search-results {
      display: grid;
      grid-template-columns: repeat(auto-fit, minmax(260px, 1fr));
      gap: 0.75rem;
    }
    .manuals-search-results[hidden] {
      display: none;
    }
    .manuals-search-result {
      padding: 0.9rem 1rem;
      border-radius: 8px;
      border: 1px solid var(--color-border);
      background: var(--color-card-bg);
      box-shadow: var(--shadow-sm);
    }
    .manuals-search-result-title {
      display: inline-block;
      margin: 0 0 0.3rem;
      font-weight: 600;
      text-decoration: none;
      color: var(--color-primary);
    }
    .manuals-search-result-summary {
      margin: 0;
      color: var(--color-text-light);
      font-size: 0.94rem;
    }
    .manuals-quick-links {
      padding: 0;
    }
    .manuals-quick-links-grid {
      display: grid;
      grid-template-columns: repeat(auto-fit, minmax(220px, 1fr));
      gap: 1rem;
    }
    .manuals-quick-link-card {
      display: flex;
      flex-direction: column;
      gap: 0.35rem;
      min-height: 100%;
      padding: 1rem;
      border-radius: 8px;
      border: 1px solid var(--color-border);
      background: var(--color-card-bg);
      box-shadow: var(--shadow-sm);
      text-decoration: none;
      color: inherit;
      transition: background-color 0.2s, box-shadow 0.2s, border-color 0.2s;
    }
    .manuals-quick-link-card:hover,
    .manuals-quick-link-card:focus-visible {
      border-color: var(--color-primary-light);
      box-shadow: var(--shadow-md);
      background: var(--color-bg-dark);
    }
    .manuals-quick-link-title {
      font-size: 1rem;
      font-weight: 600;
      color: var(--color-primary);
    }
    .manuals-quick-link-copy {
      color: var(--color-text-light);
      font-size: 0.92rem;
      line-height: 1.45;
    }
    article {
      background: var(--color-card-bg);
      border: 1px solid var(--color-border);
      border-radius: 8px;
      padding: 1rem;
      box-shadow: var(--shadow-sm);
    }
    table {
      width: 100%;
      border-collapse: collapse;
      margin: 1.25rem 0;
      font-size: 0.95rem;
    }
    th, td {
      border: 1px solid var(--color-border);
      padding: 0.8rem 0.75rem;
      vertical-align: top;
      text-align: left;
    }
    th {
      background-color: var(--color-primary-light);
      color: var(--color-primary-dark);
    }
    ul, ol {
      padding-left: 1.5rem;
    }
    mark {
      background: var(--color-primary-light);
      color: var(--color-primary-dark);
      padding: 0 0.1rem;
      border-radius: 2px;
    }
    .manuals-footer {
      background-color: var(--color-footer-bg);
      padding: 1.25rem 1rem;
      margin-top: 2rem;
      border-top: 1px solid var(--color-border);
      border-radius: 8px;
      color: var(--color-text-light);
      font-size: 0.88rem;
      line-height: 1.45;
      display: grid;
      gap: 0.2rem;
    }
    .manuals-footer p {
      margin: 0;
    }
    @media (max-width: 768px) {
      .manuals-brand {
        align-items: flex-start;
      }

      .manuals-summary-title {
        font-size: 2rem;
      }
    }
  </style>
</head>
<body>
  <main>
    <div class="manuals-page">
      <header class="manuals-brand">
        <a class="manuals-brand-link" href="/" aria-label="Data Quality Made Easy home">
          <picture>
            <source media="(prefers-color-scheme: dark)" srcset="$manuals_logo_dark" />
            <img class="manuals-brand-logo" src="$manuals_logo_light" alt="Data Quality Made Easy" />
          </picture>
        </a>
        <div class="manuals-brand-copy">
          <p class="manuals-brand-kicker">Data Quality Made Easy</p>
          <p class="manuals-brand-title">User manuals</p>
          <p class="manuals-brand-subtitle">Public reference cards for terminology, FAQ, and lookup items</p>
        </div>
      </header>
      <section class="manuals-summary" aria-label="Manuals introduction">
        <p class="manuals-summary-kicker">Help Centre</p>
        <h1 class="manuals-summary-title">How can we help you?</h1>
        <p class="manuals-summary-copy">Search the public manuals or open a reference card to find the approved wording, lookup terms, and supporting guidance used across the app.</p>
      </section>
      <section class="manuals-search" aria-label="Search manuals">
        <label class="manuals-search-label" for="manuals-search-input">Search all public manuals pages</label>
        <input
          id="manuals-search-input"
          class="manuals-search-input"
          type="search"
          placeholder="Search titles, terms, and page text"
          autocomplete="off"
          spellcheck="false"
        />
        <p class="manuals-search-status" id="manuals-search-status">Searches all public manuals pages.</p>
        <div class="manuals-search-results" id="manuals-search-results" hidden></div>
      </section>
      $quick_links_html
      <article>
$body_html
      </article>
      <footer class="manuals-footer" aria-label="Publication details">
        <p>Generated on $generated_at_label by the dq-ui manuals publisher.</p>
        <p>Responsible publisher: dq-rulebuilder maintainers.</p>
      </footer>
    </div>
  </main>
  <script>
    (() => {
      const manualsSearchIndex = $search_index_json
      const searchInput = document.getElementById('manuals-search-input')
      const searchResults = document.getElementById('manuals-search-results')
      const searchStatus = document.getElementById('manuals-search-status')

      if (!searchInput || !searchResults || !searchStatus) {
        return
      }

      const indexedPages = manualsSearchIndex.map((entry) => ({
        ...entry,
        haystack: (entry.title + ' ' + entry.summary + ' ' + entry.searchText).toLowerCase(),
      }))

      function escapeHtml(value) {
        return value
          .replace(/&/g, '&amp;')
          .replace(/</g, '&lt;')
          .replace(/>/g, '&gt;')
          .replace(/"/g, '&quot;')
          .replace(/'/g, '&#39;')
      }

      function highlight(value, queryTerms) {
        const escapedValue = escapeHtml(value)
        if (!queryTerms.length) {
          return escapedValue
        }

        let highlightedValue = escapedValue
        for (const term of queryTerms) {
          const pattern = new RegExp('(' + term.replace(/[.*+?^$$()|[\]\\]/g, '\\$$&') + ')', 'gi')
          highlightedValue = highlightedValue.replace(pattern, '<mark>$$1</mark>')
        }

        return highlightedValue
      }

      function renderResults(query) {
        const trimmedQuery = query.trim().toLowerCase()

        if (!trimmedQuery) {
          searchResults.innerHTML = ''
          searchResults.hidden = true
          searchStatus.textContent = 'Searches all public manuals pages.'
          return
        }

        const queryTerms = trimmedQuery.split(/\s+/).filter(Boolean)
        const matches = indexedPages.filter((entry) => queryTerms.every((term) => entry.haystack.includes(term)))

        if (!matches.length) {
          searchResults.hidden = false
          searchResults.innerHTML = '<p class="manuals-search-result-summary">No public manuals pages matched that search.</p>'
          searchStatus.textContent = 'No matches for "' + query + '".'
          return
        }

        searchResults.hidden = false
        searchResults.innerHTML = matches
          .map((entry) =>
            '<div class="manuals-search-result">' +
            '<a class="manuals-search-result-title" href="' + escapeHtml(entry.href) + '">' + highlight(entry.title, queryTerms) + '</a>' +
            '<p class="manuals-search-result-summary">' + highlight(entry.summary, queryTerms) + '</p>' +
            '</div>',
          )
          .join('')

        searchStatus.textContent = matches.length + ' result' + (matches.length === 1 ? '' : 's') + ' across all public manuals pages.'
      }

      searchInput.addEventListener('input', (event) => {
        renderResults(event.currentTarget.value)
      })

      renderResults(searchInput.value)
    })()
  </script>
</body>
</html>
"""
)


def fail(message: str) -> None:
    print(f"[sync-user-manuals] {message}", file=sys.stderr)
    raise SystemExit(1)


def escape_html(value: str) -> str:
    return html_escape(value, quote=True)


def is_markdown_file(file_name: str) -> bool:
    return file_name.lower().endswith(".md")


def walk_markdown_files(current_dir: Path) -> list[Path]:
    collected: list[Path] = []
    for path in sorted(current_dir.rglob("*")):
        if not path.is_file() or not is_markdown_file(path.name):
            continue
        if path.name.startswith("_"):
            continue
        collected.append(path)
    return collected


def output_path_for_source(source_path: Path) -> Path:
    relative_path = source_path.relative_to(SOURCE_DIR)
    base_name = "index.html" if relative_path.stem.lower() == "readme" else f"{relative_path.stem}.html"
    return TARGET_DIR / relative_path.parent / base_name


def public_href_for_source(source_path: Path) -> str:
    relative_path = source_path.relative_to(SOURCE_DIR)
    base_name = "index.html" if relative_path.stem.lower() == "readme" else f"{relative_path.stem}.html"
    relative_dir = "/".join(relative_path.parent.parts)
    return "/".join(part for part in (MANUALS_PUBLIC_BASE.rstrip("/"), relative_dir, base_name) if part)


def is_external_link(href: str) -> bool:
    return re.match(r"^(?:[a-z][a-z0-9+.-]*:|#|/)", href, re.IGNORECASE) is not None


def is_hidden_manual_link_target(target_path_without_query: str) -> bool:
    return any(segment.startswith("_") for segment in target_path_without_query.replace("\\", "/").split("/"))


def render_inline(text: str, source_path: Path) -> str:
    rendered = escape_html(text)

    def replace_link(match: re.Match[str]) -> str:
        label = match.group(1)
        raw_target = match.group(2).strip()

        if is_external_link(raw_target):
            return f'<a href="{escape_html(raw_target)}">{label}</a>'

        target_path_only, anchor = (raw_target.split("#", 1) + [""])[:2]
        target_path_without_query, query = (target_path_only.split("?", 1) + [""])[:2]
        resolved_target = (source_path.parent / target_path_without_query).resolve()

        if is_hidden_manual_link_target(target_path_without_query):
            return escape_html(label)

        if resolved_target.is_relative_to(SOURCE_DIR) and is_markdown_file(resolved_target.name):
            relative_href = public_href_for_source(resolved_target)
            anchor_suffix = f"#{anchor}" if anchor else ""
            query_suffix = f"?{query}" if query else ""
            return f'<a href="{escape_html(relative_href + query_suffix + anchor_suffix)}">{label}</a>'

        return f'<a href="{escape_html(raw_target)}">{label}</a>'

    rendered = re.sub(r"\[([^\]]+)\]\(([^)]+)\)", replace_link, rendered)
    rendered = re.sub(r"`([^`]+)`", r"<code>\1</code>", rendered)
    rendered = re.sub(r"\*\*([^*]+)\*\*", r"<strong>\1</strong>", rendered)
    return rendered


def is_table_separator(line: str) -> bool:
    return re.match(r"^\s*\|?(?:\s*:?-{3,}:?\s*\|)+\s*:?-{3,}:?\s*\|?\s*$", line) is not None


def split_table_row(line: str) -> list[str]:
    return [cell.strip() for cell in line.strip().strip("|").split("|")]


def extract_page_title(source_text: str, fallback_title: str) -> str:
    match = re.search(r"^#\s+(.*)$", source_text, re.MULTILINE)
    return match.group(1).strip() if match else fallback_title


def strip_markdown_for_search(source_text: str) -> str:
    cleaned = source_text.replace("\r\n", "\n")
    cleaned = re.sub(r"^#{1,6}\s+", "", cleaned, flags=re.MULTILINE)
    cleaned = re.sub(r"^\s*[-*]\s+", "", cleaned, flags=re.MULTILINE)
    cleaned = re.sub(r"^\s*\d+\.\s+", "", cleaned, flags=re.MULTILINE)
    cleaned = re.sub(r"\[([^\]]+)\]\(([^)]+)\)", r"\1", cleaned)
    cleaned = re.sub(r"`([^`]+)`", r"\1", cleaned)
    cleaned = re.sub(r"\*\*([^*]+)\*\*", r"\1", cleaned)
    cleaned = re.sub(r"\*([^*]+)\*", r"\1", cleaned)
    cleaned = re.sub(r"^\s*\|", " ", cleaned, flags=re.MULTILINE)
    cleaned = re.sub(r"\|\s*$", " ", cleaned, flags=re.MULTILINE)
    cleaned = re.sub(r"^\s*\|(?:\s*:?-{3,}:?\s*\|)+\s*:?-{3,}:?\s*\|?\s*$", " ", cleaned, flags=re.MULTILINE)
    cleaned = re.sub(r"\s+", " ", cleaned)
    return cleaned.strip()


def summarize_search_text(search_text: str, max_length: int = 180) -> str:
    return search_text if len(search_text) <= max_length else f"{search_text[: max_length - 1].rstrip()}…"


def format_generated_at(date: datetime) -> str:
    return date.strftime("%Y-%m-%d %H:%M UTC")


def serialize_json_for_script(value: object) -> str:
    return json.dumps(value, ensure_ascii=False, separators=(",", ":")).replace("<", "\\u003c")


def build_search_index_entry(source_text: str, source_path: Path) -> dict[str, str]:
    title = extract_page_title(source_text, source_path.stem)
    search_text = strip_markdown_for_search(source_text)
    return {
        "title": title,
        "href": public_href_for_source(source_path),
        "summary": summarize_search_text(search_text),
        "searchText": search_text,
    }


def build_quick_links_html(entries: list[dict[str, str]]) -> str:
    cards = [
        {
            "title": "Search the manuals",
            "description": "Jump straight to the search bar and filter the public reference cards.",
            "href": "#manuals-search-input",
        },
        {
            "title": "Current cards",
            "description": "Browse the manuals index and the public reference cards that are available now.",
            "href": "#current-cards",
        },
    ]

    for entry in entries:
        if entry["href"].endswith("/index.html"):
            continue

        cards.append({"title": entry["title"], "description": entry["summary"], "href": entry["href"]})

    rendered_cards = "\n".join(
        f'''                <a class="manuals-quick-link-card" href="{escape_html(card["href"])}">
                  <span class="manuals-quick-link-title">{escape_html(card["title"])}</span>
                  <span class="manuals-quick-link-copy">{escape_html(card["description"])}</span>
                </a>'''
        for card in cards
    )

    return f"""
      <section class="manuals-quick-links" aria-label="Quick links">
        <div class="manuals-section-heading">
          <p class="manuals-section-kicker">Quick links</p>
          <h2>Popular manuals actions</h2>
        </div>
        <div class="manuals-quick-links-grid">
{rendered_cards}
        </div>
      </section>"""


def render_markdown(source_text: str, source_path: Path, output_path: Path, search_index_json: str, generated_at_label: str) -> str:
    lines = source_text.replace("\r\n", "\n").split("\n")
    output: list[str] = []
    index = 0
    heading_ids: dict[str, int] = {}
    page_title = extract_page_title(source_text, output_path.stem)

    while index < len(lines):
        line = lines[index]
        trimmed = line.strip()

        if not trimmed:
            index += 1
            continue

        heading_match = re.match(r"^(#{1,6})\s+(.*)$", line)
        if heading_match:
            level = len(heading_match.group(1))
            heading_text = heading_match.group(2).strip()
            base_heading_id = re.sub(r"[^a-z0-9]+", "-", heading_text.lower()).strip("-") or "section"
            duplicate_count = heading_ids.get(base_heading_id, 0)
            heading_ids[base_heading_id] = duplicate_count + 1
            heading_id = base_heading_id if duplicate_count == 0 else f"{base_heading_id}-{duplicate_count + 1}"
            output.append(f'<h{level} id="{heading_id}">{render_inline(heading_text, source_path)}</h{level}>')
            index += 1
            continue

        next_line = lines[index + 1] if index + 1 < len(lines) else ""
        if "|" in line and is_table_separator(next_line):
            header_cells = split_table_row(line)
            rows: list[list[str]] = []
            index += 2

            while index < len(lines):
                table_line = lines[index]
                if not table_line.strip() or "|" not in table_line:
                    break

                rows.append(split_table_row(table_line))
                index += 1

            header_html = "".join(f"<th>{render_inline(cell, source_path)}</th>" for cell in header_cells)
            body_html = "".join(
                f"<tr>{''.join(f'<td>{render_inline(cell, source_path)}</td>' for cell in row)}</tr>" for row in rows
            )
            output.append(f"<table><thead><tr>{header_html}</tr></thead><tbody>{body_html}</tbody></table>")
            continue

        if re.match(r"^[-*]\s+", trimmed):
            items: list[str] = []
            while index < len(lines) and re.match(r"^[-*]\s+", lines[index].strip()):
                items.append(re.sub(r"^[-*]\s+", "", lines[index].strip()))
                index += 1

            output.append(f"<ul>{''.join(f'<li>{render_inline(item, source_path)}</li>' for item in items)}</ul>")
            continue

        if re.match(r"^\d+\.\s+", trimmed):
            items = []
            while index < len(lines) and re.match(r"^\d+\.\s+", lines[index].strip()):
                items.append(re.sub(r"^\d+\.\s+", "", lines[index].strip()))
                index += 1

            output.append(f"<ol>{''.join(f'<li>{render_inline(item, source_path)}</li>' for item in items)}</ol>")
            continue

        paragraph_lines = [trimmed]
        index += 1

        while index < len(lines):
            lookahead = lines[index]
            lookahead_trimmed = lookahead.strip()
            lookahead_next = lines[index + 1] if index + 1 < len(lines) else ""

            if not lookahead_trimmed:
                break

            if (
                re.match(r"^#{1,6}\s+", lookahead_trimmed)
                or re.match(r"^[-*]\s+", lookahead_trimmed)
                or re.match(r"^\d+\.\s+", lookahead_trimmed)
                or ("|" in lookahead and is_table_separator(lookahead_next))
            ):
                break

            paragraph_lines.append(lookahead_trimmed)
            index += 1

        output.append(f"<p>{render_inline(' '.join(paragraph_lines), source_path)}</p>")

    quick_links_html = build_quick_links_html(json.loads(search_index_json)) if source_path.name.lower() == "readme.md" else ""

    return PAGE_SHELL_TEMPLATE.substitute(
        page_title=escape_html(page_title),
        body_html="\n".join(output),
        quick_links_html=quick_links_html,
        search_index_json=search_index_json,
        generated_at_label=escape_html(generated_at_label),
        manuals_logo_dark=MANUALS_LOGO_DARK,
        manuals_logo_light=MANUALS_LOGO_LIGHT,
    )


def ensure_directory(dir_path: Path) -> None:
    dir_path.mkdir(parents=True, exist_ok=True)


def remove_stale_files(dir_path: Path) -> None:
    if not dir_path.exists():
        return

    for entry in sorted(dir_path.iterdir()):
        if entry.is_dir():
            shutil.rmtree(entry)
            continue

        entry.unlink(missing_ok=True)


def main() -> None:
    if not SOURCE_DIR.exists():
        fail(f"Source directory not found: {SOURCE_DIR}")

    ensure_directory(TARGET_DIR)
    remove_stale_files(TARGET_DIR)

    markdown_files = walk_markdown_files(SOURCE_DIR)
    generated_at_label = format_generated_at(datetime.now(timezone.utc))
    page_records = [build_search_index_entry(source_path.read_text(encoding="utf-8"), source_path) for source_path in markdown_files]
    search_index_json = serialize_json_for_script(page_records)

    for source_path in markdown_files:
        output_path = output_path_for_source(source_path)
        ensure_directory(output_path.parent)
        source_text = source_path.read_text(encoding="utf-8")
        html = render_markdown(source_text, source_path, output_path, search_index_json, generated_at_label)
        output_path.write_text(html, encoding="utf-8")

    print(f"[sync-user-manuals] Published {len(markdown_files)} manuals to {TARGET_DIR}")


if __name__ == "__main__":
    main()