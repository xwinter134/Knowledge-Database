"""Relevanz-Ranking des Korpus anhand der eigenen Zotero-Bibliothek.

Idee: Die Paper in Zotero sind „relevant“ (positiv). Ein TF-IDF-Modell mit logistischer Regression lernt,
wie sie sich vom Rest des Korpus unterscheiden, und vergibt jedem Korpus-Paper einen Score 0–1.
Paper, die schon in Zotero sind, bekommen kb_status='zotero' (über DOI oder Titel abgeglichen).

Zugang: ZOTERO_USER_ID und ZOTERO_API_KEY (Cloud-Session: Key setzt der Proxy, Platzhalter genügt).
Die Zotero-Einträge werden in $KB_CORPUS_DIR/zotero_items.jsonl zwischengespeichert (--refresh lädt neu).

  python tools/corpus/rank.py            # Ranking berechnen, Top 25 anzeigen
  python tools/corpus/rank.py --top 50 --since 2026-10-01
  python tools/corpus/rank.py --refresh  # Zotero neu laden
  python tools/corpus/rank.py --exclude-venue "Nature Methods"   # fachfremde Zotero-Einträge ignorieren
"""
from __future__ import annotations

import argparse
import json
import os
import re
import sqlite3
import sys
import urllib.request
from pathlib import Path

import numpy as np
import yaml
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.linear_model import LogisticRegression
from sklearn.model_selection import cross_val_predict
from sklearn.metrics import roc_auc_score

CORPUS = Path(os.environ.get("KB_CORPUS_DIR", Path.home() / "kb-corpus")).expanduser()
REPO = Path(__file__).resolve().parents[2]
CONFIG = yaml.safe_load((REPO / "corpus" / "config.yaml").read_text(encoding="utf-8"))
BACKGROUND = REPO / "corpus" / "background.jsonl.gz"   # feste Stichprobe als Negativbeispiele
CACHE = CORPUS / "zotero_items.jsonl"
SKIP = {"attachment", "note", "annotation"}


def norm_title(t: str | None) -> str:
    return re.sub(r"[^a-z0-9]", "", (t or "").lower())[:80]


def load_zotero(refresh: bool) -> list[dict]:
    if CACHE.exists() and not refresh:
        return [json.loads(l) for l in CACHE.open(encoding="utf-8")]
    uid = os.environ.get("ZOTERO_USER_ID") or str(CONFIG["zotero"]["user_id"])
    key = os.environ.get("ZOTERO_API_KEY", "proxy-injected")
    if not uid:
        sys.exit("ZOTERO_USER_ID setzen (Zahl von zotero.org/settings/keys).")
    items, start = [], 0
    while True:
        req = urllib.request.Request(
            f"https://api.zotero.org/users/{uid}/items/top?format=json&limit=100&start={start}",
            headers={"Zotero-API-Key": key, "Zotero-API-Version": "3"})
        page = json.load(urllib.request.urlopen(req, timeout=60))
        items += [p["data"] for p in page if p["data"].get("itemType") not in SKIP]
        if len(page) < 100:
            break
        start += 100
    CACHE.parent.mkdir(parents=True, exist_ok=True)
    with CACHE.open("w", encoding="utf-8") as f:
        for it in items:
            f.write(json.dumps(it, ensure_ascii=False) + "\n")
    return items


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--refresh", action="store_true")
    ap.add_argument("--top", type=int, default=25)
    ap.add_argument("--since", help="Top-Liste nur ab diesem Erscheinungsdatum")
    ap.add_argument("--exclude-venue", nargs="*", default=CONFIG["ranking"]["exclude_venues"],
                    help="Zotero-Einträge dieser Zeitschriften nicht als Positivbeispiele nutzen")
    a = ap.parse_args()

    con = sqlite3.connect(CORPUS / "corpus.sqlite")
    zot = load_zotero(a.refresh)
    zdois = {(z.get("DOI") or "").lower().strip() for z in zot} - {""}
    ztitles = {norm_title(z.get("title")) for z in zot} - {""}

    rows = con.execute("SELECT id, doi, title, abstract, keywords FROM works").fetchall()
    in_zot = [(r[1] in zdois) or (norm_title(r[2]) in ztitles) for r in rows]
    con.executemany("UPDATE works SET kb_status='zotero' WHERE id=?",
                    [(r[0],) for r, z in zip(rows, in_zot) if z])

    text = lambda t, ab, kw: f"{t or ''} {t or ''} {ab or ''} {kw or ''}"   # Titel doppelt gewichtet
    # Positive: alle Zotero-Einträge mit Text (auch ältere, die nicht im Korpus sind)
    excl = {v.lower() for v in a.exclude_venue}
    kb_coll = CONFIG["zotero"].get("collection_key")
    # Unbestätigte Kandidaten (nur in der KB-Sammlung) nicht als Positivbeispiel lernen,
    # sonst bestätigt sich das Ranking selbst. In eine eigene Sammlung verschoben = bestätigt.
    confirmed = [z for z in zot if not (kb_coll and z.get("collections") == [kb_coll])]
    pos = [text(z.get("title"), z.get("abstractNote"), " ".join(t["tag"] for t in z.get("tags", [])))
           for z in confirmed if z.get("title") and (z.get("publicationTitle") or "").lower() not in excl]
    neg_rows = [r for r, z in zip(rows, in_zot) if not z]
    neg = [text(r[2], r[3], r[4]) for r in neg_rows]
    if len(neg) < 5000 and BACKGROUND.exists():
        # Kleiner Korpus (z. B. Wochenlauf): mit fester Hintergrund-Stichprobe auffüllen
        import gzip
        with gzip.open(BACKGROUND, "rt", encoding="utf-8") as f:
            neg += [text(b.get("title"), b.get("abstract"), b.get("keywords")) for b in map(json.loads, f)
                    if b.get("doi") not in zdois and norm_title(b.get("title")) not in ztitles]
    X_text = pos + neg
    y = np.array([1] * len(pos) + [0] * len(neg))

    vec = TfidfVectorizer(ngram_range=(1, 2), min_df=2, max_df=0.5, sublinear_tf=True,
                          stop_words="english", max_features=200_000)
    X = vec.fit_transform(X_text)
    clf = LogisticRegression(C=4.0, class_weight="balanced", max_iter=2000)

    # Güte grob schätzen: Wie gut trennt das Modell Zotero-Paper vom Rest? (5-fach Kreuzvalidierung)
    cv = cross_val_predict(clf, X, y, cv=5, method="predict_proba")[:, 1]
    auc = roc_auc_score(y, cv)
    clf.fit(X, y)

    all_text = [text(r[2], r[3], r[4]) for r in rows]
    scores = clf.predict_proba(vec.transform(all_text))[:, 1]
    con.executemany("UPDATE works SET relevance=? WHERE id=?",
                    [(round(float(s), 4), r[0]) for s, r in zip(scores, rows)])
    con.commit()

    print(f"Zotero: {len(zot)} Einträge ({len(zot) - len(confirmed)} unbestätigte Kandidaten), "
          f"davon {sum(in_zot)} im Korpus wiedergefunden")
    print(f"Modell: {len(pos)} positive, {len(neg)} übrige Paper, Trennschärfe (AUC, Kreuzvalidierung) {auc:.2f}")
    s = np.array(scores)[[not z for z in in_zot]]
    for thr in (0.9, 0.7, 0.5, 0.3):
        print(f"  Score ≥ {thr}: {int((s >= thr).sum())} Paper (nicht in Zotero)")

    # Wichtigste Begriffe des Modells (zur Kontrolle)
    names = np.array(vec.get_feature_names_out())
    top = names[np.argsort(clf.coef_[0])[-30:]][::-1]
    print("Stärkste Relevanz-Signale:", ", ".join(top))

    where = "AND pub_date >= ?" if a.since else ""
    args = (a.since,) if a.since else ()
    print(f"\nTop {a.top} Kandidaten (nicht in Zotero){' ab ' + a.since if a.since else ''}:")
    for rid, rel, date, venue, title in con.execute(
            f"""SELECT id, relevance, pub_date, venue, title FROM works
                WHERE coalesce(kb_status,'') != 'zotero' {where}
                ORDER BY relevance DESC LIMIT ?""", (*args, a.top)):
        print(f"  {rel:.2f}  {date}  {(venue or '')[:28]:28}  {(title or '')[:95]}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
