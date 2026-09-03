#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
Генератор статического сайта «Selecline BM1250C — инструкция и рецепты».

Читает данные из data/, шаблоны из templates/, кладёт готовый сайт в docs/.
GitHub Pages раздаёт папку docs/ ветки main без всякой сборки на их стороне.

    python build.py            # собрать
    python build.py --serve    # собрать и поднять локальный сервер на :8000
"""

from __future__ import annotations

import json
import re
import shutil
import sys
from datetime import date
from pathlib import Path

from jinja2 import Environment, FileSystemLoader, select_autoescape

ROOT = Path(__file__).parent
DATA = ROOT / "data"
OUT = ROOT / "docs"

FRONT_MATTER = re.compile(r"^<!--json\s*(\{.*?\})\s*-->\s*", re.DOTALL)

H2 = re.compile(r"<h2(?P<attrs>[^>]*)>(?P<inner>.*?)</h2>", re.DOTALL | re.IGNORECASE)
HAS_ID = re.compile(r"\sid\s*=", re.IGNORECASE)
TAGS = re.compile(r"<[^>]+>")

TRANSLIT = {
    "а": "a", "б": "b", "в": "v", "г": "g", "д": "d", "е": "e", "ё": "e", "ж": "zh",
    "з": "z", "и": "i", "й": "j", "к": "k", "л": "l", "м": "m", "н": "n", "о": "o",
    "п": "p", "р": "r", "с": "s", "т": "t", "у": "u", "ф": "f", "х": "h", "ц": "c",
    "ч": "ch", "ш": "sh", "щ": "sch", "ъ": "", "ы": "y", "ь": "", "э": "e",
    "ю": "yu", "я": "ya",
}


def slugify(text: str) -> str:
    out = []
    for ch in text.lower():
        if ch in TRANSLIT:
            out.append(TRANSLIT[ch])
        elif ch.isalnum() and ch.isascii():
            out.append(ch)
        else:
            out.append("-")
    return re.sub(r"-{2,}", "-", "".join(out)).strip("-")[:60] or "razdel"


def add_anchors(body: str) -> tuple[str, list[dict]]:
    """Проставляет id всем h2 без него и собирает локальное оглавление страницы."""
    toc: list[dict] = []
    used: set[str] = set()

    def repl(m: re.Match) -> str:
        attrs, inner = m.group("attrs"), m.group("inner")
        title = re.sub(r"\s+", " ", TAGS.sub("", inner)).strip()
        found = re.search(r'\sid\s*=\s*"([^"]+)"', attrs)
        if found:
            anchor = found.group(1)
            tag = m.group(0)
        else:
            anchor = slugify(title)
            n = 2
            while anchor in used:
                anchor = f"{slugify(title)}-{n}"
                n += 1
            tag = f'<h2 id="{anchor}"{attrs}>{inner}</h2>'
        used.add(anchor)
        toc.append({"id": anchor, "title": title})
        return tag

    return H2.sub(repl, body), toc


def load_json(name: str):
    return json.loads((DATA / name).read_text(encoding="utf-8"))


def rel_for(url: str) -> str:
    """Префикс к корню сайта для страницы с данным url ('', '../', '../../')."""
    depth = url.count("/")
    return "../" * depth


def write(url: str, html: str) -> Path:
    path = OUT / url / "index.html" if url else OUT / "index.html"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(html, encoding="utf-8")
    return path


# ---------------------------------------------------------------- JSON-LD

def jsonld(obj) -> str:
    return json.dumps(obj, ensure_ascii=False, indent=None)


def breadcrumb_ld(site, crumbs):
    return jsonld({
        "@context": "https://schema.org",
        "@type": "BreadcrumbList",
        "itemListElement": [
            {"@type": "ListItem", "position": i + 1, "name": c["title"],
             "item": f'{site["site_url"]}/{c["url"]}'}
            for i, c in enumerate(crumbs)
        ],
    })


def recipe_ld(site, r):
    total = r["prep_min"] + r["cook_min"]
    return jsonld({
        "@context": "https://schema.org",
        "@type": "Recipe",
        "name": r["h1"],
        "description": r["description"],
        "inLanguage": "ru-RU",
        "url": f'{site["site_url"]}/recepty/{r["slug"]}/',
        "recipeCategory": "Хлеб",
        "recipeCuisine": "Домашняя выпечка",
        "keywords": ", ".join(r["keywords"]),
        "recipeYield": r["yield"],
        "prepTime": f'PT{r["prep_min"]}M',
        "cookTime": f'PT{r["cook_min"]}M',
        "totalTime": f'PT{total}M',
        "cookingMethod": f'Хлебопечка, программа {r["program"]["n"]} {r["program"]["en"]}',
        "recipeIngredient": [
            f'{i["name"]} — {i["qty"]}' for i in r["ingredients"]
        ],
        "recipeInstructions": [
            {"@type": "HowToStep", "position": n + 1, "text": s}
            for n, s in enumerate(r["steps"])
        ],
        "tool": [{"@type": "HowToTool", "name": "Хлебопечка Selecline BM1250C"}],
        "author": {"@type": "Organization", "name": site["site_name"]},
    })


def howto_ld(site, url, name, description, steps):
    return jsonld({
        "@context": "https://schema.org",
        "@type": "HowTo",
        "name": name,
        "description": description,
        "inLanguage": "ru-RU",
        "url": f'{site["site_url"]}/{url}',
        "step": [
            {"@type": "HowToStep", "position": n + 1, "text": s}
            for n, s in enumerate(steps)
        ],
    })


def faq_ld(site, faq):
    return jsonld({
        "@context": "https://schema.org",
        "@type": "FAQPage",
        "mainEntity": [
            {"@type": "Question", "name": q["q"],
             "acceptedAnswer": {"@type": "Answer", "text": re.sub(r"<[^>]+>", "", q["a"]).strip()}}
            for q in faq
        ],
    })


def website_ld(site, machine):
    """Сайт + сущность самой печки в поле about: помогает поисковику связать
    модель, марку Selecline и сеть Ашан в одну сущность."""
    return jsonld({
        "@context": "https://schema.org",
        "@type": "WebSite",
        "name": f'{site["site_name"]} — {site["site_tagline"]}',
        "url": site["site_url"] + "/",
        "inLanguage": "ru-RU",
        "about": {
            "@type": "Product",
            "name": f'Хлебопечка {machine["model"]}',
            "category": "Хлебопечка",
            "model": "BM1250C",
            "brand": {"@type": "Brand", "name": machine["brand"]},
            "alternateName": machine["aka"],
            "description": (
                f'Хлебопечка {machine["model"]} — модель под собственной маркой '
                f'{machine["brand"]} торговой сети {machine["retailer"]}. 15 программ, '
                "размеры буханки 700 г и 900 г."
            ),
        },
    })


# ---------------------------------------------------------------- сборка

def build(serve: bool = False) -> None:
    site = load_json("site.json")
    machine = load_json("machine.json")
    recipes = load_json("recipes.json")
    faq = load_json("faq.json")

    env = Environment(
        loader=FileSystemLoader(ROOT / "templates"),
        autoescape=select_autoescape(["html"]),
        trim_blocks=True,
        lstrip_blocks=True,
    )

    if OUT.exists():
        shutil.rmtree(OUT)
    OUT.mkdir(parents=True)

    base_ctx = dict(
        site=site,
        machine=machine,
        programs=machine["programs"],
        buttons=machine["buttons"],
        sizes=machine["sizes"],
        measures=machine["measures"],
        recipes=recipes,
        faq=faq,
        today=date.today().isoformat(),
    )

    urls: list[tuple[str, str]] = []  # (url, priority)

    # ---- главная
    home_crumbs = [{"url": "", "title": "Главная"}]
    main_recipe = next(r for r in recipes if r["slug"] == "belyj-hleb")
    html = env.get_template("index.html").render(
        **base_ctx,
        url="",
        rel="",
        breadcrumbs=None,
        main_recipe=main_recipe,
        page_title="Хлебопечка Selecline BM1250C (Ашан): инструкция, 15 программ и рецепты на русском",
        page_description=(
            "Инструкция к хлебопечке Selecline BM1250C из Ашана: расшифровка всех 15 программ, порядок "
            "закладки продуктов, настройки панели и рабочие рецепты хлеба в граммах и миллилитрах."
        ),
        keywords=["selecline bm1250c", "хлебопечка ашан", "хлебопечка auchan selecline",
                  "хлебопечка selecline инструкция", "рецепты для хлебопечки selecline",
                  "bm1250c программы", "хлебопечка ашан рецепты", "selecline bm1250-c"],
        og_type="website",
        jsonld=[website_ld(site, machine), faq_ld(site, faq), breadcrumb_ld(site, home_crumbs)],
    )
    write("", html)
    urls.append(("", "1.0"))

    # ---- контентные страницы
    for src in sorted((DATA / "pages").glob("*.html")):
        raw = src.read_text(encoding="utf-8")
        m = FRONT_MATTER.match(raw)
        if not m:
            raise SystemExit(f"{src.name}: нет блока <!--json ... -->")
        meta = json.loads(m.group(1))
        body_src = raw[m.end():]
        url = meta["url"]
        rel = rel_for(url)

        body = env.from_string(body_src).render(**base_ctx, rel=rel, url=url)
        body, toc = add_anchors(body)
        # оглавление показываем только на длинных страницах и только там, где его нет в тексте
        if not meta.get("toc", True) or len(toc) < 4:
            toc = []
        crumbs = [{"url": "", "title": "Главная"}, {"url": url, "title": meta["h1"]}]

        blocks = [breadcrumb_ld(site, crumbs)]
        if meta.get("howto"):
            blocks.append(howto_ld(
                site, url, "Как испечь хлеб в хлебопечке Selecline BM1250C",
                "Порядок закладки продуктов и настройка панели",
                ["Установите лопатку в ведёрко",
                 "Влейте воду",
                 "Добавьте масло, соль и сахар",
                 "Засыпьте сверху всю муку",
                 "Сделайте в муке небольшую ямку",
                 "Всыпьте в ямку дрожжи",
                 "MENU → нужная программа, LOAF SIZE → размер, COLOUR → корочка",
                 "Нажмите START и через 10–15 минут проверьте колобок"],
            ))

        html = env.get_template("page.html").render(
            **base_ctx,
            url=url, rel=rel, breadcrumbs=crumbs,
            h1=meta["h1"], lead=meta.get("lead"), body=body, toc=toc,
            page_title=meta["title"], page_description=meta["description"],
            keywords=meta.get("keywords"), jsonld=blocks,
        )
        write(url, html)
        urls.append((url, meta.get("priority", "0.6")))

    # ---- индекс рецептов
    url = "recepty/"
    crumbs = [{"url": "", "title": "Главная"}, {"url": url, "title": "Рецепты"}]
    html = env.get_template("recipes_index.html").render(
        **base_ctx, url=url, rel=rel_for(url), breadcrumbs=crumbs,
        page_title="Рецепты для хлебопечки Selecline BM1250C — 7 рецептов под её программы",
        page_description=("Рецепты хлеба для Selecline BM1250C в граммах и миллилитрах: белый, французский, "
                          "цельнозерновой, сладкий, сэндвичный, с травами. С указанием программы и размера буханки."),
        keywords=["рецепты для хлебопечки selecline", "хлебопечка bm1250c рецепты", "рецепт хлеба в хлебопечке в граммах"],
        jsonld=[breadcrumb_ld(site, crumbs), jsonld({
            "@context": "https://schema.org", "@type": "ItemList",
            "itemListElement": [
                {"@type": "ListItem", "position": i + 1, "name": r["h1"],
                 "url": f'{site["site_url"]}/recepty/{r["slug"]}/'}
                for i, r in enumerate(recipes)
            ],
        })],
    )
    write(url, html)
    urls.append((url, "0.9"))

    # ---- рецепты
    for r in recipes:
        url = f'recepty/{r["slug"]}/'
        crumbs = [{"url": "", "title": "Главная"},
                  {"url": "recepty/", "title": "Рецепты"},
                  {"url": url, "title": r["h1"]}]
        html = env.get_template("recipe.html").render(
            **base_ctx, url=url, rel=rel_for(url), breadcrumbs=crumbs,
            r=r, others=[o for o in recipes if o["slug"] != r["slug"]][:3],
            page_title=r["title"], page_description=r["description"], keywords=r["keywords"],
            jsonld=[recipe_ld(site, r), breadcrumb_ld(site, crumbs)],
        )
        write(url, html)
        urls.append((url, "0.8" if r.get("featured") else "0.7"))

    # ---- статика и служебные файлы
    # вся папка static/ ложится в корень сайта (style.css, manual/*.pdf и т. д.)
    shutil.copytree(ROOT / "static", OUT, dirs_exist_ok=True)
    (OUT / ".nojekyll").write_text("", encoding="utf-8")

    today = date.today().isoformat()
    sitemap = ['<?xml version="1.0" encoding="UTF-8"?>',
               '<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">']
    for u, prio in urls:
        sitemap.append(
            f'  <url><loc>{site["site_url"]}/{u}</loc><lastmod>{today}</lastmod>'
            f'<changefreq>monthly</changefreq><priority>{prio}</priority></url>'
        )
    sitemap.append("</urlset>")
    (OUT / "sitemap.xml").write_text("\n".join(sitemap) + "\n", encoding="utf-8")

    (OUT / "robots.txt").write_text(
        "User-agent: *\nAllow: /\n\n"
        f'Sitemap: {site["site_url"]}/sitemap.xml\n',
        encoding="utf-8",
    )

    if "USERNAME" in site["site_url"]:
        print("ВНИМАНИЕ: в data/site.json поле site_url всё ещё содержит USERNAME.")
        print("          Впишите свой адрес GitHub Pages — от него зависят canonical, OG и sitemap.xml.")
        print()

    print(f"Готово: {len(urls)} страниц в {OUT}")
    for u, _ in urls:
        print(f"  /{u}")

    if serve:
        import http.server
        import socketserver
        import os
        os.chdir(OUT)
        with socketserver.TCPServer(("", 8000), http.server.SimpleHTTPRequestHandler) as httpd:
            print("\nhttp://localhost:8000/  (Ctrl+C — остановить)")
            httpd.serve_forever()


if __name__ == "__main__":
    build(serve="--serve" in sys.argv)
