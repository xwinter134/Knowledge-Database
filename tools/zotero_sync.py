"""Holt neue/geänderte Einträge aus Zotero (Web-API) und legt Notiz-Stubs in literature/ an.

Bestehende Notizen werden nie überschrieben (Abgleich über zotero_key).
Umgebungsvariablen: ZOTERO_USER_ID, ZOTERO_API_KEY (zotero.org → Settings → Security → API keys)
Optional:           ZOTERO_COLLECTION (Collection-Key, um nur eine Sammlung zu synchronisieren)
Zustand (letzte Bibliotheksversion) in .zotero_state.json → inkrementeller Abgleich.
"""
from __future__ import annotations

import datetime as dt
import json
import os
import re
import sys
import unicodedata
import urllib.request

import yaml

from kblib import ROOT, iter_notes

API = "https://api.zotero.org"
STATE = ROOT / ".zotero_state.json"
SKIP_TYPES = {"attachment", "note", "annotation"}
STOP = {"a", "an", "the", "on", "of", "in", "for", "and", "to", "with", "der", "die", "das"}


def fetch(path: str, key: str) -> tuple[list, dict]:
    req = urllib.request.Request(f"{API}{path}", headers={"Zotero-API-Key": key, "Zotero-API-Version": "3"})
    with urllib.request.urlopen(req, timeout=60) as r:
        return json.load(r), dict(r.headers)


def slug(s: str) -> str:
    s = unicodedata.normalize("NFKD", s).encode("ascii", "ignore").decode()
    return re.sub(r"[^a-z0-9]", "", s.lower())


def citekey(d: dict, taken: set) -> str:
    creators = d.get("creators") or [{}]
    last = slug(creators[0].get("lastName") or creators[0].get("name") or "anon")
    year = (re.search(r"\d{4}", d.get("date", "")) or [""])[0] if d.get("date") else ""
    word = next((slug(w) for w in d.get("title", "").split() if slug(w) and slug(w) not in STOP), "x")
    base = f"{last}{year}{word}"
    key, n = base, 1
    while key in taken:
        n += 1
        key = f"{base}{chr(96 + n)}"
    return key


def main() -> int:
    uid, key = os.environ.get("ZOTERO_USER_ID"), os.environ.get("ZOTERO_API_KEY")
    if not uid or not key:
        print("ZOTERO_USER_ID und ZOTERO_API_KEY setzen.", file=sys.stderr)
        return 2
    coll = os.environ.get("ZOTERO_COLLECTION")
    since = json.loads(STATE.read_text())["version"] if STATE.exists() else 0

    existing, taken = set(), set()
    for p, fm, _ in iter_notes():
        if fm and fm.get("zotero_key"):
            existing.add(fm["zotero_key"])
        taken.add(p.stem)

    base = f"/users/{uid}/collections/{coll}/items" if coll else f"/users/{uid}/items"
    start, created, version = 0, 0, since
    while True:
        items, headers = fetch(f"{base}?format=json&limit=100&start={start}&since={since}", key)
        version = int(headers.get("Last-Modified-Version", version))
        for it in items:
            d = it["data"]
            if d.get("itemType") in SKIP_TYPES or d["key"] in existing:
                continue
            ck = citekey(d, taken)
            taken.add(ck)
            fm = {
                "id": ck, "type": "paper", "title": d.get("title", ""),
                "authors": [f"{c.get('lastName', c.get('name', ''))}, {c.get('firstName', '')}".strip(", ")
                            for c in d.get("creators", [])],
                "year": int(m[0]) if (m := re.search(r"\d{4}", d.get("date", ""))) else None,
                "journal": d.get("publicationTitle", ""), "doi": d.get("DOI", ""),
                "zotero_key": d["key"], "status": "stub",
                "created": dt.date.today().isoformat(),
                "tags": [t["tag"] for t in d.get("tags", [])],
                "relevance": 0, "methods": [], "formulations": [], "related": [],
                "files": [f"literature/{ck}.pdf"],
            }
            abstract = d.get("abstractNote", "").strip()
            body = f"\n## Abstract\n{abstract}\n\n## Kernaussage\n\n## Methoden\n\n## Ergebnisse\n\n" \
                   f"## Limitationen & offene Punkte\n\n## Bezug zu meiner Forschung\n\n## Ideen-Funken\n"
            (ROOT / "literature" / f"{ck}.md").write_text(
                "---\n" + yaml.safe_dump(fm, allow_unicode=True, sort_keys=False) + "---\n" + body,
                encoding="utf-8")
            created += 1
        if len(items) < 100:
            break
        start += 100
    STATE.write_text(json.dumps({"version": version}))
    print(f"{created} neue Paper-Stubs, Bibliotheksversion {version}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
