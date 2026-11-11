"""Überträgt relevante Korpus-Paper als Einträge in eine Zotero-Sammlung.

- Nur Paper mit relevance >= min_relevance, die noch nicht in Zotero sind (kb_status != 'zotero')
  und nicht schon früher übertragen wurden (corpus/state/zotero_pushed.csv im Repo).
- Sammlung, Schwelle, Tag und Obergrenze aus corpus/config.yaml.
- Jeder Eintrag bekommt Tags: kb-korpus, Relevanz-Stufe und die Suchanfragen, die ihn gefunden haben.

  python tools/corpus/zotero_push.py --dry-run            # nur anzeigen
  python tools/corpus/zotero_push.py --since 2024-11-11 --max 250
"""
from __future__ import annotations

import argparse
import csv
import datetime as dt
import json
import os
import sqlite3
import sys
import time
import urllib.request
import uuid
from pathlib import Path

import yaml

REPO = Path(__file__).resolve().parents[2]
CORPUS = Path(os.environ.get("KB_CORPUS_DIR", Path.home() / "kb-corpus")).expanduser()
CONFIG = yaml.safe_load((REPO / "corpus" / "config.yaml").read_text(encoding="utf-8"))
STATE = REPO / "corpus" / "state" / "zotero_pushed.csv"
API = "https://api.zotero.org"


def zot(method: str, path: str, body=None, write_token: str | None = None):
    key = os.environ.get("ZOTERO_API_KEY", "proxy-injected")
    h = {"Zotero-API-Key": key, "Zotero-API-Version": "3", "Content-Type": "application/json"}
    if write_token:
        h["Zotero-Write-Token"] = write_token
    data = json.dumps(body).encode() if body is not None else None
    for i in range(4):
        try:
            req = urllib.request.Request(f"{API}{path}", data=data, headers=h, method=method)
            with urllib.request.urlopen(req, timeout=60) as r:
                if r.headers.get("Backoff"):
                    time.sleep(int(r.headers["Backoff"]))
                return json.loads(r.read() or b"null")
        except urllib.error.HTTPError as e:
            if e.code in (429, 503):
                time.sleep(int(e.headers.get("Retry-After", 10)))
                continue
            sys.exit(f"Zotero-Fehler {e.code}: {e.read()[:300]!r}")
    sys.exit("Zotero nicht erreichbar.")


def collection_key(uid: str, name: str) -> str:
    for c in zot("GET", f"/users/{uid}/collections?limit=100"):
        if c["data"]["name"] == name:
            return c["key"]
    res = zot("POST", f"/users/{uid}/collections", [{"name": name}], uuid.uuid4().hex)
    return res["successful"]["0"]["key"]


def item(row: dict, coll: str, tag: str) -> dict:
    itype = "preprint" if row["type"] == "preprint" else "journalArticle"
    creators = []
    for name in (row["authors"] or "").replace(" et al.", "").split("; ")[:25]:
        if not name.strip():
            continue
        parts = name.strip().rsplit(" ", 1)
        creators.append({"creatorType": "author", "firstName": parts[0] if len(parts) == 2 else "",
                         "lastName": parts[-1]})
    rel = row["relevance"]
    tags = [tag, f"kb-relevanz-{'hoch' if rel >= 0.8 else 'mittel' if rel >= 0.6 else 'basis'}"]
    tags += [f"kb-q:{t}" for t in (row["tags"] or "").split(";") if t]
    it = {
        "itemType": itype, "title": row["title"] or "", "creators": creators,
        "abstractNote": row["abstract"] or "", "date": row["pub_date"] or "",
        "DOI": row["doi"] or "", "url": f"https://doi.org/{row['doi']}" if row["doi"] else row["oa_url"] or "",
        "extra": f"OpenAlex: {row['id']}\nKB-Relevanz: {rel:.2f}" + (f"\nPMID: {row['pmid']}" if row["pmid"] else ""),
        "tags": [{"tag": t} for t in tags], "collections": [coll],
    }
    if itype == "journalArticle":
        it["publicationTitle"] = row["venue"] or ""
    else:
        it["repository"] = row["venue"] or ""
    return it


def load_state() -> set[str]:
    if not STATE.exists():
        return set()
    with STATE.open(encoding="utf-8") as f:
        rows = list(csv.DictReader(f))
    return {r["openalex_id"] for r in rows} | {r["doi"] for r in rows if r["doi"]}


def main() -> int:
    cfg = CONFIG["zotero"]
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--min-relevance", type=float, default=cfg["min_relevance"])
    ap.add_argument("--max", type=int, default=cfg["max_per_run"])
    ap.add_argument("--since", help="nur Paper ab diesem Erscheinungsdatum")
    ap.add_argument("--dry-run", action="store_true")
    a = ap.parse_args()

    con = sqlite3.connect(CORPUS / "corpus.sqlite")
    con.row_factory = sqlite3.Row
    done = load_state()
    where = "AND pub_date >= ?" if a.since else ""
    rows = [r for r in con.execute(
        f"""SELECT * FROM works WHERE relevance >= ? AND coalesce(kb_status,'') NOT IN ('zotero','pushed')
            {where} ORDER BY relevance DESC""", (a.min_relevance, *([a.since] if a.since else [])))
        if r["id"] not in done and (r["doi"] or "") not in done][: a.max]
    print(f"{len(rows)} Paper für Zotero (Score ≥ {a.min_relevance})")
    if a.dry_run or not rows:
        for r in rows[:20]:
            print(f"  {r['relevance']:.2f}  {r['pub_date']}  {(r['title'] or '')[:100]}")
        return 0

    uid = str(cfg["user_id"])
    coll = collection_key(uid, cfg["collection"])
    STATE.parent.mkdir(parents=True, exist_ok=True)
    new_file = not STATE.exists()
    pushed = 0
    with STATE.open("a", encoding="utf-8", newline="") as f:
        w = csv.writer(f)
        if new_file:
            w.writerow(["openalex_id", "doi", "zotero_key", "relevance", "pushed", "title"])
        for i in range(0, len(rows), 50):          # Zotero: max. 50 Einträge pro Anfrage
            batch = rows[i:i + 50]
            res = zot("POST", f"/users/{uid}/items", [item(r, coll, cfg["tag"]) for r in batch], uuid.uuid4().hex)
            for idx, key in (res.get("successful") or {}).items():
                r = batch[int(idx)]
                k = key["key"] if isinstance(key, dict) else key
                w.writerow([r["id"], r["doi"] or "", k, f"{r['relevance']:.3f}", dt.date.today().isoformat(),
                            (r["title"] or "")[:150]])
                con.execute("UPDATE works SET kb_status='pushed' WHERE id=?", (r["id"],))
                pushed += 1
            for idx, err in (res.get("failed") or {}).items():
                print(f"  fehlgeschlagen: {batch[int(idx)]['title'][:80]} – {err.get('message')}")
            con.commit()
    print(f"{pushed} Einträge in Zotero-Sammlung „{cfg['collection']}“ angelegt")
    return 0


if __name__ == "__main__":
    sys.exit(main())
