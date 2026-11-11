"""Korpus-Einsammler: holt Metadaten (Europe PMC) und freie Volltext-XMLs in eine lokale SQLite.

Der Korpus liegt AUSSERHALB des Repos (groß, abgeleitet): $KB_CORPUS_DIR, Standard ~/kb-corpus
  corpus.sqlite        works, fulltext, runs + Volltextsuche (works_fts)
  xml/<PMCID>.xml      freie Volltexte (JATS-XML, schon gegliedert, kein GROBID nötig)

Beispiele:
  python tools/corpus/harvest.py --from 2024-11-11                 # alle Anfragen aus corpus/queries.yaml
  python tools/corpus/harvest.py --from 2026-11-01 --only rna_immuno
  python tools/corpus/harvest.py --fulltext                        # fehlende Volltext-XMLs laden
  python tools/corpus/harvest.py --stats
Wiederholbar: bekannte Paper werden aktualisiert, nicht doppelt angelegt.
"""
from __future__ import annotations

import argparse
import datetime as dt
import json
import os
import sqlite3
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

import yaml

REPO = Path(__file__).resolve().parents[2]
CORPUS = Path(os.environ.get("KB_CORPUS_DIR", Path.home() / "kb-corpus")).expanduser()
API = "https://www.ebi.ac.uk/europepmc/webservices/rest"
UA = "knowledge-database-corpus/0.1 (personal research use)"
PAUSE = 0.3  # Sekunden zwischen Anfragen

SCHEMA = """
CREATE TABLE IF NOT EXISTS works(
  id TEXT PRIMARY KEY, doi TEXT UNIQUE, pmid TEXT UNIQUE, pmcid TEXT, epmc_id TEXT, source TEXT,
  title TEXT, abstract TEXT, authors TEXT, journal TEXT, pub_date TEXT, year INTEGER,
  pub_types TEXT, keywords TEXT, mesh TEXT, is_oa INTEGER, in_epmc INTEGER, has_pdf INTEGER,
  cited_by INTEGER, tags TEXT, first_seen TEXT, updated TEXT,
  relevance REAL, triage TEXT, kb_status TEXT);
CREATE TABLE IF NOT EXISTS fulltext(
  work_id TEXT, kind TEXT, path TEXT, status TEXT, fetched TEXT, PRIMARY KEY(work_id, kind));
CREATE TABLE IF NOT EXISTS runs(
  query TEXT, date_from TEXT, date_to TEXT, started TEXT, finished TEXT, hits INTEGER, new INTEGER);
CREATE VIRTUAL TABLE IF NOT EXISTS works_fts USING fts5(
  id UNINDEXED, title, abstract, keywords, mesh, tokenize='unicode61 remove_diacritics 2');
"""


def get(url: str, params: dict | None = None, raw: bool = False, tries: int = 4):
    if params:
        url = f"{url}?{urllib.parse.urlencode(params)}"
    for i in range(tries):
        try:
            req = urllib.request.Request(url, headers={"User-Agent": UA})
            with urllib.request.urlopen(req, timeout=90) as r:
                data = r.read()
            time.sleep(PAUSE)
            return data if raw else json.loads(data)
        except urllib.error.HTTPError as e:
            if e.code == 404:
                return None
            if i == tries - 1:
                raise
        except (urllib.error.URLError, TimeoutError):
            if i == tries - 1:
                raise
        time.sleep(2 ** (i + 1))


def connect() -> sqlite3.Connection:
    CORPUS.mkdir(parents=True, exist_ok=True)
    (CORPUS / "xml").mkdir(exist_ok=True)
    con = sqlite3.connect(CORPUS / "corpus.sqlite")
    con.executescript(SCHEMA)
    return con


def record(r: dict) -> dict:
    doi = (r.get("doi") or "").lower().strip() or None
    pmid = r.get("pmid") or None
    authors = [a.get("fullName", "") for a in (r.get("authorList") or {}).get("author", [])]
    journal = ((r.get("journalInfo") or {}).get("journal") or {}).get("title") or r.get("bookOrReportDetails", {}).get("publisher", "")
    kw = (r.get("keywordList") or {}).get("keyword", [])
    mesh = [m.get("descriptorName", "") for m in (r.get("meshHeadingList") or {}).get("meshHeading", [])]
    ptypes = (r.get("pubTypeList") or {}).get("pubType", [])
    date = r.get("firstPublicationDate") or ""
    return {
        "id": f"doi:{doi}" if doi else (f"pmid:{pmid}" if pmid else f"epmc:{r.get('source')}:{r.get('id')}"),
        "doi": doi, "pmid": pmid, "pmcid": r.get("pmcid"), "epmc_id": f"{r.get('source')}:{r.get('id')}",
        "source": r.get("source"), "title": r.get("title"), "abstract": r.get("abstractText"),
        "authors": "; ".join(authors), "journal": journal, "pub_date": date,
        "year": int(date[:4]) if date[:4].isdigit() else None,
        "pub_types": "; ".join(ptypes), "keywords": "; ".join(kw), "mesh": "; ".join(mesh),
        "is_oa": int(r.get("isOpenAccess") == "Y"), "in_epmc": int(r.get("inEPMC") == "Y"),
        "has_pdf": int(r.get("hasPDF") == "Y"), "cited_by": r.get("citedByCount"),
    }


def upsert(con: sqlite3.Connection, rec: dict, tag: str) -> bool:
    """Fügt ein oder aktualisiert. True, wenn neu. Abgleich über id, DOI oder PMID."""
    row = con.execute("SELECT id, tags, doi, pmid FROM works WHERE id=? OR (doi IS NOT NULL AND doi=?) "
                      "OR (pmid IS NOT NULL AND pmid=?)", (rec["id"], rec["doi"], rec["pmid"])).fetchone()
    now = dt.datetime.now().isoformat(timespec="seconds")
    if row:
        tags = set(filter(None, (row[1] or "").split(";"))) | {tag}
        upd = {k: v for k, v in rec.items() if k != "id" and v not in (None, "")}
        upd.update(tags=";".join(sorted(tags)), updated=now)
        # Eindeutige Kennungen nicht überschreiben, wenn sie zu einem anderen Eintrag gehören
        for k in ("doi", "pmid"):
            if k in upd and row[2 if k == "doi" else 3] not in (None, upd[k]):
                upd.pop(k)
        sets = ", ".join(f"{k}=?" for k in upd)
        con.execute(f"UPDATE works SET {sets} WHERE id=?", (*upd.values(), row[0]))
        con.execute("DELETE FROM works_fts WHERE id=?", (row[0],))
        wid, new = row[0], False
    else:
        rec = {**rec, "tags": tag, "first_seen": now, "updated": now}
        cols = ", ".join(rec)
        con.execute(f"INSERT INTO works({cols}) VALUES ({','.join('?' * len(rec))})", tuple(rec.values()))
        wid, new = rec["id"], True
    w = con.execute("SELECT title, abstract, keywords, mesh FROM works WHERE id=?", (wid,)).fetchone()
    con.execute("INSERT INTO works_fts VALUES (?,?,?,?,?)", (wid, *[x or "" for x in w]))
    return new


def harvest(con, name: str, query: str, date_from: str, date_to: str) -> None:
    q = f"({query}) AND FIRST_PDATE:[{date_from} TO {date_to}]"
    started = dt.datetime.now().isoformat(timespec="seconds")
    cursor, hits, new, seen = "*", None, 0, 0
    while True:
        d = get(f"{API}/search", {"query": q, "format": "json", "resultType": "core",
                                   "pageSize": 500, "cursorMark": cursor})
        hits = d["hitCount"] if hits is None else hits
        results = d.get("resultList", {}).get("result", [])
        for r in results:
            new += upsert(con, record(r), name)
        seen += len(results)
        con.commit()
        print(f"  {name}: {seen}/{hits} verarbeitet, {new} neu", end="\r")
        nxt = d.get("nextCursorMark")
        if not results or not nxt or nxt == cursor:
            break
        cursor = nxt
    con.execute("INSERT INTO runs VALUES (?,?,?,?,?,?,?)",
                (name, date_from, date_to, started, dt.datetime.now().isoformat(timespec="seconds"), hits, new))
    con.commit()
    print(f"  {name}: {hits} Treffer, {new} neu{' ' * 20}")


def fetch_fulltext(con, limit: int | None) -> None:
    rows = con.execute("""SELECT w.id, w.pmcid FROM works w
                          LEFT JOIN fulltext f ON f.work_id = w.id AND f.kind = 'xml'
                          WHERE w.pmcid IS NOT NULL AND w.in_epmc = 1 AND f.work_id IS NULL
                          ORDER BY w.pub_date DESC""").fetchall()
    rows = rows[:limit] if limit else rows
    print(f"{len(rows)} Volltext-XMLs zu laden")
    for i, (wid, pmcid) in enumerate(rows, 1):
        data = get(f"{API}/{pmcid}/fullTextXML", raw=True)
        now = dt.datetime.now().isoformat(timespec="seconds")
        if data:
            path = CORPUS / "xml" / f"{pmcid}.xml"
            path.write_bytes(data)
            con.execute("INSERT OR REPLACE INTO fulltext VALUES (?,?,?,?,?)",
                        (wid, "xml", str(path.relative_to(CORPUS)), "ok", now))
        else:
            con.execute("INSERT OR REPLACE INTO fulltext VALUES (?,?,?,?,?)", (wid, "xml", None, "missing", now))
        if i % 50 == 0:
            con.commit()
            print(f"  {i}/{len(rows)}", end="\r")
    con.commit()
    print(f"  fertig{' ' * 20}")


PPR = "SELECT count(*) FROM works WHERE source='PPR'"
FT_OK = "SELECT count(*) FROM fulltext WHERE kind='xml' AND status='ok'"


def stats(con) -> None:
    q = lambda s: con.execute(s).fetchone()[0]
    print(f"Korpus: {CORPUS}")
    print(f"  Paper gesamt:        {q('SELECT count(*) FROM works')}")
    print(f"  mit DOI:             {q('SELECT count(*) FROM works WHERE doi IS NOT NULL')}")
    print(f"  Preprints:           {q(PPR)}")
    print(f"  Volltext frei (EPMC):{q('SELECT count(*) FROM works WHERE in_epmc=1 AND pmcid IS NOT NULL')}")
    print(f"  Volltext geladen:    {q(FT_OK)}")
    for tag, n in con.execute("SELECT tags, count(*) FROM works GROUP BY tags ORDER BY 2 DESC LIMIT 10"):
        print(f"  Tags {tag}: {n}")
    size = sum(p.stat().st_size for p in CORPUS.rglob("*") if p.is_file()) / 1e6
    print(f"  Speicher:            {size:.0f} MB")


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--from", dest="date_from", help="Startdatum JJJJ-MM-TT")
    ap.add_argument("--to", dest="date_to", default=dt.date.today().isoformat())
    ap.add_argument("--only", nargs="*", help="nur diese Anfragen aus queries.yaml")
    ap.add_argument("--fulltext", action="store_true", help="fehlende Volltext-XMLs laden")
    ap.add_argument("--limit", type=int, help="max. Anzahl Volltexte")
    ap.add_argument("--stats", action="store_true")
    a = ap.parse_args()
    con = connect()
    if a.date_from:
        queries = yaml.safe_load((REPO / "corpus" / "queries.yaml").read_text(encoding="utf-8"))["queries"]
        for name, spec in queries.items():
            if a.only and name not in a.only:
                continue
            harvest(con, name, " ".join(spec["query"].split()), a.date_from, a.date_to)
    if a.fulltext:
        fetch_fulltext(con, a.limit)
    if a.stats or not (a.date_from or a.fulltext):
        stats(con)
    return 0


if __name__ == "__main__":
    sys.exit(main())
