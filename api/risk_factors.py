"""
Plain-English 10-K summary: the risk factor headings from Item 1A of the latest 10-K, and what changed versus the
prior year's 10-K. Extractive only: every line shown is a heading as the company wrote it, and every count is a count
of those headings, so nothing is paraphrased or invented.

Companies write each risk factor as a bold or italic heading sentence followed by plain paragraphs, so the headings
are the emphasized paragraphs inside Item 1A. Only the Item 1A part of the HTML is parsed, which keeps memory low
even for very long 10-Ks.
"""
import html as html_lib
import re
from difflib import SequenceMatcher

import lxml.html

# The section search runs on the raw bytes, so a 40 MB 10-K isn't also held as a (up to 4x larger) Python string
GAP = rb"(?:\s|&#160;|&nbsp;|&#xa0;|<[^>]{0,400}>)*"
ITEM = re.compile(rb"item" + GAP + rb"(1a|1b|1c|7a|[2-9]|1[0-6])\b", re.IGNORECASE)
BLOCKS = {"p", "div", "li", "h1", "h2", "h3", "h4", "h5", "h6", "td"}
BOLD = re.compile(r"font-weight\s*:\s*(?:bold|bolder|[6-9]00)", re.IGNORECASE)
ITALIC = re.compile(r"font-style\s*:\s*(?:italic|oblique)", re.IGNORECASE)
UNDERLINE = re.compile(r"text-decoration\s*:\s*underline", re.IGNORECASE)


def _plain(fragment):
    if isinstance(fragment, bytes):
        fragment = fragment.decode("utf-8", errors="ignore")
    return html_lib.unescape(re.sub(r"<[^>]*>", " ", fragment)).replace("\xa0", " ")


BLOCK_TAG = re.compile(rb"<(?:/?(?:p|div|td|th|tr|li|h[1-6]|table|tbody)\b|br\b)[^>]*>", re.IGNORECASE)


def _is_heading(html, pos):
    """True when an "Item ..." at pos starts its own block (a heading or table of contents entry), not a mention inside
    a sentence such as "see Item 7, Management's Discussion"."""
    window = html[max(0, pos - 3000):pos]
    last = None
    for last in BLOCK_TAG.finditer(window):
        pass
    lead = _plain(window[last.end():] if last else window).strip()
    return lead == "" or bool(re.fullmatch(r"part\s+[iv]+\s*[.,:\u2014\u2013-]?", lead, re.IGNORECASE))


HREF = re.compile(rb'href\s*=\s*"#([^"]{1,200})"', re.IGNORECASE)


def _target(html, anchor):
    m = re.search(rb'(?:id|name)\s*=\s*"' + re.escape(anchor) + rb'"', html)
    return m.start() if m else None


def _linked_1a(html):
    """Item 1A by following the table of contents link ("Item 1A. <a href="#risk">Risk Factors</a>") to its anchor,
    up to the anchor of the next item's link. Some filers set the real heading inside a table cell where it doesn't
    look like a heading, but the links still say where the section starts and ends."""
    items = list(ITEM.finditer(html))
    for k, m in enumerate(items):
        if m.group(1).lower() != b"1a":
            continue
        link = HREF.search(html, m.start(), m.end() + 1500)
        if not link or "risk factors" not in _plain(html[m.start():m.end() + 1500]).lower()[:300]:
            continue
        start = _target(html, link.group(1))
        for nxt in items[k + 1:k + 4]:
            if nxt.group(1).lower() == b"1a":
                continue
            nlink = HREF.search(html, nxt.start(), nxt.end() + 1500)
            end = _target(html, nlink.group(1)) if nlink and nlink.group(1) != link.group(1) else None
            if start is not None and end is not None and end > start:
                return start, end
            break
    return None


def item_1a_html(html):
    """The raw HTML (bytes or str in, str out) of Item 1A: from an "Item 1A ... Risk Factors" heading to the next Item heading. Of all such
    stretches the longest wins, since the table of contents has the same words but almost nothing between them.
    None if the 10-K has no Item 1A heading."""
    if isinstance(html, str):
        html = html.encode("utf-8")
    heads = [(m.start(), m.group(1).lower()) for m in ITEM.finditer(html) if _is_heading(html, m.start())]
    best = None
    for k, (pos, item) in enumerate(heads):
        if item != b"1a" or "risk factors" not in _plain(html[pos:pos + 1500]).lower()[:300]:
            continue
        end = next((p for p, it in heads[k + 1:] if it != b"1a"), None)
        if end is None:
            continue
        if best is None or end - pos > best[1] - best[0]:
            best = (pos, end)
    linked = _linked_1a(html)
    if linked and (best is None or linked[1] - linked[0] > best[1] - best[0]):
        best = linked
    if best is None:
        return None
    # Back up to the start of the tag that holds "Item 1A", so the fragment parses cleanly
    start = html.rfind(b"<", 0, best[0])
    return html[max(start, 0):best[1]].decode("utf-8", errors="ignore")


def _style_of(el):
    tag = el.tag if isinstance(el.tag, str) else ""
    style = el.get("style", "") if tag else ""
    return {
        "b": tag in ("b", "strong") or bool(BOLD.search(style)),
        "i": tag in ("i", "em") or bool(ITALIC.search(style)),
        "u": tag == "u" or bool(UNDERLINE.search(style)),
    }


def _runs(block):
    """(text, emphasis) pieces of one block in reading order; emphasis is the set of b/i/u that applies."""
    out = []

    def walk(el, inherited):
        s = _style_of(el)
        here = {k for k in ("b", "i", "u") if s[k] or k in inherited}
        if el.text:
            out.append((el.text, frozenset(here)))
        for child in el:
            if isinstance(child.tag, str) and child.tag not in ("script", "style"):
                walk(child, here)
            if child.tail:
                out.append((child.tail, frozenset(here)))

    walk(block, frozenset())
    return out


def _clean(s):
    s = re.sub(r"^[\s\u2022\u25cf\u25aa\u25a0\u2023\u2043\u00b7\uf0b7-]+", "", s)
    s = s.replace("\xa0", " ").replace("’", "'").replace("“", '"').replace("”", '"')
    return re.sub(r"\s+", " ", s).strip()


def blocks(fragment_html):
    """Leaf text blocks of the fragment (no block children), outside tables, as (text, emphasis, lead_text)."""
    root = lxml.html.fromstring(f"<div>{fragment_html}</div>")
    out = []
    for el in root.iter():
        if not isinstance(el.tag, str) or el.tag not in BLOCKS:
            continue
        if any(isinstance(c.tag, str) and c.tag in BLOCKS for c in el.iterdescendants()):
            continue
        if el.tag == "td" or any(a.tag == "table" for a in el.iterancestors()):
            continue
        runs = _runs(el)
        text = _clean("".join(t for t, _ in runs))
        if not text:
            continue
        chars = {"b": 0, "i": 0, "u": 0}
        total = 0
        for t, emph in runs:
            n = len(re.sub(r"\s", "", t))
            total += n
            for k in emph:
                chars[k] += n
        full = frozenset(k for k, n in chars.items() if total and n / total >= 0.9)
        # A run-in heading: an emphasized sentence that starts the paragraph, followed by plain text
        lead = []
        for t, emph in runs:
            if emph or not t.strip():
                lead.append(t)
            else:
                break
        lead_text = _clean("".join(lead))
        out.append((text, full, lead_text if not full and len(lead_text) >= 40 else ""))
    return out


CATEGORY = re.compile(r"^(?:risks?\b|general\b|summary\b|.*\brisks?$|.*\brelated to\b|.*\brelating to\b|.*\bfactors$)", re.IGNORECASE)
SKIP = re.compile(r"^(?:item\s*1a|risk factors\.?$|table of contents|index|\d+$|page \d+|part i\b)", re.IGNORECASE)
# Introductions some filers also set in bold or italic ("The following risk factors should be considered...")
INTRO = re.compile(r"^(?:the\s+following|the\s+above|readers\s+should|you\s+should|investors\s+should|in\s+addition\s+to\s+the\s+other|"
                   r"this\s+section|we\s+are\s+subject\s+to\s+(?:a\s+)?(?:number|variety)\s+of\s+risks|our\s+business,?\s+(?:operations\s+)?and\s+financial|"
                   r"an\s+investment\s+in|investing\s+in|certain\s+factors\s+may)", re.IGNORECASE)


def headings(fragment_html):
    """{"categories": [...], "risks": [{"title", "category"}], "words": n} from the Item 1A fragment."""
    rows = blocks(fragment_html)
    words = sum(len(t.split()) for t, _, _ in rows)
    emphasized = [(t, e) for t, e, _ in rows if e]
    run_ins = sum(1 for _, _, lead in rows if lead)
    # Use run-in headings when the filing has more of them than whole emphasized paragraphs of heading length
    use_run_ins = run_ins > sum(1 for t, e in emphasized if len(t) >= 40)

    items = []
    for text, emph, lead in rows:
        if SKIP.match(text):
            continue
        title = text if emph else (lead if use_run_ins else "")
        if not title:
            continue
        if len(title) < 120 and not title.endswith(".") and (CATEGORY.match(title) or len(title.split()) <= 8):
            items.append(("category", title))
        elif 30 <= len(title) <= 900 and not INTRO.match(title):
            items.append(("risk", title))
    # Some filers title each risk with a short topic ("MANAGED CARE TRENDS") instead of a sentence. When there are
    # hardly any sentence headings, the short ones that aren't group names ("Risks Related to ...") are the risks.
    if sum(1 for kind, _ in items if kind == "risk") < 5:
        items = [("risk" if kind == "category" and not CATEGORY.match(t) and len(t) >= 8 else kind, t) for kind, t in items]

    risks, categories, category = [], [], None
    for kind, title in items:
        if kind == "category":
            category = title
            categories.append(title)
        else:
            risks.append({"title": title, "category": category})
    return {"categories": categories, "risks": risks, "words": words}


def _norm(s):
    return re.sub(r"[^a-z0-9 ]", "", s.lower()).strip()


def compare(current, prior):
    """Matches this year's headings to last year's. Same wording (98%+ similar) is unchanged, 75-98% is reworded,
    anything else is new (this year only) or removed (last year only)."""
    cur = [_norm(r["title"]) for r in current]
    old = [_norm(r["title"]) for r in prior]
    used, status = set(), []
    for i, c in enumerate(cur):
        best, best_j = 0.0, None
        for j, o in enumerate(old):
            if j in used:
                continue
            sm = SequenceMatcher(None, c, o, autojunk=False)
            if sm.real_quick_ratio() < best or sm.quick_ratio() < best:
                continue
            r = sm.ratio()
            if r > best:
                best, best_j = r, j
        if best >= 0.75:
            used.add(best_j)
            status.append(("unchanged" if best >= 0.98 else "reworded", best_j, best))
        else:
            status.append(("new", None, best))
    removed = [prior[j]["title"] for j in range(len(prior)) if j not in used]
    return status, removed
