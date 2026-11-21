"""Publish one blog post on a static (ex-WordPress) site: iptvnetherland.com / iptvnetherland.nl.

  python3 tools/publish_post.py --keyword "iptv box" --slug iptv-box --title "IPTV Box" \
      --meta-title "..." --meta-desc "..." --article /tmp/article.html

tools/site.json decides the layout mode:
  "mode": "nl"  -> rich layout (phero hero, TOC, cta-box, related section)  [iptvnetherland.nl]
  "mode": "com" -> minimal self-contained layout (main.doc)                  [iptvnetherland.com]
The page is built from tools/post_template.html (a copy of one existing post of that site).
Writes title/description/canonical/OG/JSON-LD, adds the URL to sitemap.xml, registers the post in
tools/posts.json and (nl) adds a card to the blog index.
"""
import argparse, html, json, os, re, sys
from datetime import datetime, timezone

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
TOOLS = os.path.join(REPO, "tools")
MONTHS = ["januari", "februari", "maart", "april", "mei", "juni", "juli", "augustus", "september",
          "oktober", "november", "december"]


def load(name):
    with open(os.path.join(TOOLS, name), encoding="utf-8") as f:
        return json.load(f)


def text_of(s):
    return html.unescape(re.sub(r"\s+", " ", re.sub(r"<[^>]+>", " ", s))).strip()


def slugify(s):
    s = re.sub(r"[^a-z0-9]+", "-", text_of(s).lower())
    return s.strip("-") or "sectie"


def faq_pairs(article):
    m = re.search(r"<h2[^>]*>[^<]*(FAQ|Veelgestelde|Veel gestelde)[^<]*</h2>(.*?)(?=<h2|\Z)", article, re.I | re.S)
    if not m:
        return []
    out = []
    for q, a in re.findall(r"<h3[^>]*>(.*?)</h3>(.*?)(?=<h3|\Z)", m.group(2), re.S):
        q, a = text_of(q), text_of(a)
        if q and a:
            out.append((q, a))
    return out


def add_h2_ids(article):
    used = set()

    def f(m):
        attrs, inner = m.group(1), m.group(2)
        if "id=" in attrs:
            return m.group(0)
        s = slugify(inner)[:40]
        base, n = s, 2
        while s in used:
            s = f"{base}-{n}"; n += 1
        used.add(s)
        return f'<h2 id="{s}"{attrs}>{inner}</h2>'
    return re.sub(r"<h2([^>]*)>(.*?)</h2>", f, article, flags=re.S)


def sub1(pat, repl, doc, what, flags=re.S):
    doc, n = re.subn(pat, lambda m: repl(m) if callable(repl) else repl, doc, count=1, flags=flags)
    if not n:
        sys.exit(f"ERROR: template has no {what}")
    return doc


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--keyword", required=True); ap.add_argument("--slug", required=True)
    ap.add_argument("--title", required=True); ap.add_argument("--meta-title", required=True)
    ap.add_argument("--meta-desc", required=True); ap.add_argument("--article", default="article.html")
    a = ap.parse_args()

    site, posts = load("site.json"), load("posts.json")
    mode = site["mode"]
    page = os.path.join(REPO, a.slug, "index.html")
    if os.path.exists(page):
        sys.exit(f"ERROR: /{a.slug}/ already exists - pick the next keyword")
    article = open(a.article, encoding="utf-8").read().strip()
    article = re.sub(r"<h1\b[^>]*>.*?</h1>\s*", "", article, flags=re.S | re.I)
    article = add_h2_ids(article)
    n_words = len(text_of(article).split())
    if n_words < int(site.get("min_words", 2000)):
        sys.exit(f"ERROR: article has {n_words} words, minimum is {site.get('min_words', 2000)}. Expand the article "
                 "(more depth per section, more H3 subsections, longer FAQ answers) and run this command again.")

    base = site["base"]
    url = f"{base}/{a.slug}/"
    d = datetime.now(timezone.utc).replace(microsecond=0)
    now = d.isoformat()
    date_nl = f"{d.day} {MONTHS[d.month - 1]} {d.year}"
    mins = max(1, round(n_words / 220))
    title, mt, md = (html.escape(x, quote=True) for x in (a.title, a.meta_title, a.meta_desc))
    doc = open(os.path.join(TOOLS, "post_template.html"), encoding="utf-8").read()

    # ---- head (identical for both modes) ----
    doc = sub1(r"<title>.*?</title>", f"<title>{mt}</title>", doc, "<title>")
    doc = sub1(r'<meta name="description" content="[^"]*">', f'<meta name="description" content="{md}">', doc, "meta description")
    doc = sub1(r'<link rel="canonical" href="[^"]*">', f'<link rel="canonical" href="{url}">', doc, "canonical")
    for attr, name, val in (("property", "og:title", mt), ("property", "og:description", md), ("property", "og:url", url),
                            ("name", "twitter:title", mt), ("name", "twitter:description", md)):
        doc = re.sub(r'(<meta %s="%s" content=")[^"]*(">)' % (attr, re.escape(name)),
                     lambda m, v=val: m.group(1) + v + m.group(2), doc, count=1)

    # ---- recent posts for internal links (3 newest, then fall back to hubs) ----
    recent = posts[-3:][::-1]
    hub_href, hub_label = site["hub_href"], site["hub_label"]

    qa = faq_pairs(article)
    graph_extra = [
        {"@type": "BreadcrumbList", "@id": f"{url}#breadcrumb", "itemListElement": [
            {"@type": "ListItem", "position": 1, "name": site["home_label"], "item": base + "/"},
            {"@type": "ListItem", "position": 2, "name": "Blog", "item": base + "/blog/"} if mode == "nl" else
            {"@type": "ListItem", "position": 2, "name": a.title, "item": url}] + (
            [{"@type": "ListItem", "position": 3, "name": a.title, "item": url}] if mode == "nl" else [])},
        {"@type": "WebPage", "@id": f"{url}#webpage", "url": url, "name": a.meta_title, "datePublished": now,
         "dateModified": now, "isPartOf": {"@id": f"{base}/#website"}, "inLanguage": "nl-NL",
         "breadcrumb": {"@id": f"{url}#breadcrumb"}},
        {"@type": "BlogPosting", "@id": f"{url}#article", "headline": a.title, "keywords": a.keyword,
         "description": a.meta_desc, "datePublished": now, "dateModified": now,
         "author": {"@type": "Organization", "name": site["name"], "url": base + "/"},
         "publisher": {"@id": f"{base}/#organization"}, "mainEntityOfPage": {"@id": f"{url}#webpage"},
         "inLanguage": "nl-NL", "wordCount": n_words},
    ]
    if qa:
        graph_extra.append({"@type": "FAQPage", "@id": f"{url}#faq", "mainEntity": [
            {"@type": "Question", "name": q, "acceptedAnswer": {"@type": "Answer", "text": ans}} for q, ans in qa]})
    org = [{"@type": "Organization", "@id": f"{base}/#organization", "name": site["name"], "url": base},
           {"@type": "WebSite", "@id": f"{base}/#website", "url": base, "name": site["name"],
            "publisher": {"@id": f"{base}/#organization"}, "inLanguage": "nl-NL"}]

    def ld_json():
        # the template's JSON-LD (if any) supplies Organization/WebSite incl. logo; everything else is rebuilt
        keep = []
        m = re.search(r'<script type="application/ld\+json">(.*?)</script>', doc, re.S)
        if m:
            try:
                keep = [n for n in json.loads(m.group(1))["@graph"] if n.get("@type") in ("Organization", "WebSite")]
            except Exception:
                keep = []
        graph = (keep or org) + graph_extra
        return '<script type="application/ld+json">' + json.dumps({"@context": "https://schema.org", "@graph": graph},
                                                                  ensure_ascii=False) + "</script>"

    ld = ld_json()
    doc = re.sub(r'<script type="application/ld\+json">.*?</script>\s*', "", doc, flags=re.S)
    doc = doc.replace("</head>", ld + "\n</head>", 1)

    # ---- body ----
    if mode == "nl":
        doc = sub1(r"<h1>.*?</h1>", f"<h1>{title}</h1>", doc, "<h1>")
        doc = sub1(r'<p class="pmeta">.*?</p>',
                   f'<p class="pmeta">Door redactie {html.escape(site["name"])} · Bijgewerkt op {date_nl} · {mins} min leestijd</p>',
                   doc, "pmeta")
        doc = re.sub(r'<figure class="pimg">.*?</figure>', "", doc, count=1, flags=re.S)
        doc = sub1(r'(<nav class="crumbs"[^>]*>.*?)<span>[^<]*</span>(</nav>)',
                   lambda m: m.group(1) + f"<span>{title}</span>" + m.group(2), doc, "breadcrumb")
        heads = re.findall(r'<h2 id="([^"]+)"[^>]*>(.*?)</h2>', article, re.S)
        toc = "".join(f'<li><a href="#{i}">{text_of(h)}</a></li>' for i, h in heads)
        doc = sub1(r'<nav class="toc"[^>]*>.*?</nav>',
                   f'<nav class="toc" aria-label="Inhoud"><span class="tt">Inhoud</span><ol>{toc}</ol></nav>', doc, "toc")
        doc = sub1(r"<article>.*?</article>", lambda m: "<article>\n" + article + "\n</article>", doc, "<article>")
        links = "".join(f'<a href="/{p["slug"]}/">{html.escape(p["title"])}<small>Lees meer</small></a>' for p in recent)
        links = f'<a href="{hub_href}">{html.escape(hub_label)}<small>Hoofdgids</small></a>' + links
        rel = (f'<section class="related"><h2>Meer over {html.escape(a.keyword)}</h2><div class="links">{links}</div></section>')
        doc = sub1(r'<section class="related">.*?</section>', rel, doc, "related section")
    else:  # com
        links = "".join(f'<li><a href="/{p["slug"]}/">{html.escape(p["title"])}</a></li>' for p in recent)
        links = f'<li><a href="{hub_href}">{html.escape(hub_label)}</a></li>' + links
        main = (f'<main class="doc">\n<h1>{title}</h1>\n<p style="color:var(--muted);font-size:14px">Door redactie · {date_nl} · '
                f'{mins} min leestijd</p>\n{article}\n<div class="gerelateerde-artikelen-block">\n<h3>Gerelateerde artikelen</h3>\n'
                f'<ul>{links}</ul>\n</div>\n</main>')
        doc = sub1(r'<main class="doc">.*?</main>', lambda m: main, doc, "main.doc")

    os.makedirs(os.path.dirname(page), exist_ok=True)
    open(page, "w", encoding="utf-8").write(doc)

    # ---- sitemap, blog index (nl), registry ----
    sm_path = os.path.join(REPO, "sitemap.xml")
    sm = open(sm_path, encoding="utf-8").read()
    if url not in sm:
        sm = sm.replace("</urlset>", f"<url><loc>{url}</loc><lastmod>{now[:10]}</lastmod></url>\n</urlset>")
        open(sm_path, "w", encoding="utf-8").write(sm)
    if mode == "nl":
        bp = os.path.join(REPO, "blog", "index.html")
        if os.path.exists(bp):
            b = open(bp, encoding="utf-8").read()
            card = (f'<a class="bc" href="/{a.slug}/"><strong>{title}</strong><span>{md}</span><em>{date_nl}</em></a>')
            if "<!-- LATEST_START -->" not in b:
                sec = ('<section class="bsec" id="nieuw"><h2>Nieuwste artikelen</h2><div class="bgrid"><!-- LATEST_START -->'
                       '<!-- LATEST_END --></div></section>')
                b = b.replace('<section class="bsec" id="abonnement">', sec + '<section class="bsec" id="abonnement">', 1)
            b = b.replace("<!-- LATEST_START -->", "<!-- LATEST_START -->" + card, 1)
            open(bp, "w", encoding="utf-8").write(b)
    posts.append({"slug": a.slug, "url": url, "title": a.title, "keyword": a.keyword, "date": now[:10]})
    with open(os.path.join(TOOLS, "posts.json"), "w", encoding="utf-8") as f:
        json.dump(posts, f, ensure_ascii=False, indent=1)
    print(f"PUBLISHED {url} | words={n_words} | faq_schema={len(qa)}")


if __name__ == "__main__":
    main()
