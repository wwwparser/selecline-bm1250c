#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
Отправка адресов сайта в IndexNow — протокол мгновенного уведомления поисковиков
об изменениях. Яндекс его поддерживает напрямую, Google — нет (ему нужен Search Console).

Ключ лежит не в корне хоста, а в папке сайта, поэтому он авторизует ровно наши адреса
внутри /selecline-bm1250c/ — этого достаточно и не требует прав на весь github.io.

    python indexnow.py            # отправить все адреса из sitemap.xml
    python indexnow.py --dry      # только показать, что будет отправлено

Запускать после каждого заметного обновления содержимого, а не при каждой правке:
слишком частые пустые отправки поисковики игнорируют.
"""

from __future__ import annotations

import json
import re
import sys
import urllib.error
import urllib.request
from pathlib import Path

ROOT = Path(__file__).parent
KEY = "64a7ea2975ed598b40f76a5649fd96b5"

# Точки приёма. По протоколу достаточно одной — она делится с остальными участниками,
# но Яндексу отправляем и напрямую, чтобы не зависеть от их обмена.
ENDPOINTS = [
    "https://api.indexnow.org/indexnow",
    "https://yandex.com/indexnow",
]


def site_url() -> str:
    return json.loads((ROOT / "data/site.json").read_text(encoding="utf-8"))["site_url"]


def urls_from_sitemap() -> list[str]:
    xml = (ROOT / "docs/sitemap.xml").read_text(encoding="utf-8")
    return re.findall(r"<loc>(.*?)</loc>", xml)


def main() -> None:
    base = site_url()
    host = base.split("//", 1)[1].split("/", 1)[0]
    key_location = f"{base}/{KEY}.txt"
    urls = urls_from_sitemap()

    payload = {
        "host": host,
        "key": KEY,
        "keyLocation": key_location,
        "urlList": urls,
    }

    print(f"хост:   {host}")
    print(f"ключ:   {key_location}")
    print(f"адреса: {len(urls)}")
    if "--dry" in sys.argv:
        for u in urls:
            print("  ", u)
        return

    data = json.dumps(payload, ensure_ascii=False).encode("utf-8")
    for endpoint in ENDPOINTS:
        req = urllib.request.Request(
            endpoint, data=data, method="POST",
            headers={"Content-Type": "application/json; charset=utf-8"},
        )
        try:
            with urllib.request.urlopen(req, timeout=30) as resp:
                body = resp.read().decode("utf-8", "replace").strip()
                print(f"{endpoint} → {resp.status} {resp.reason} {body[:200]}")
        except urllib.error.HTTPError as e:
            body = e.read().decode("utf-8", "replace").strip()
            print(f"{endpoint} → {e.code} {e.reason} {body[:300]}")
        except Exception as e:  # сеть, таймаут
            print(f"{endpoint} → ошибка: {e}")

    print()
    print("200 — приняты, 202 — приняты, ключ ещё проверяется.")
    print("Обход занимает от нескольких часов до нескольких суток.")


if __name__ == "__main__":
    main()
