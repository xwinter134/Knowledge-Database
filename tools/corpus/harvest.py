"""Korpus-Einsammler auf Basis von OpenAlex.

OpenAlex ist die Quelle für Suche und Metadaten. Lokal gehalten wird nur, was OpenAlex nicht bietet
oder was für Ranking und Volltextsuche ständig gebraucht wird:
  works      OpenAlex-ID, DOI/PMID/PMCID, Titel, Abstract (Cache), Open-Access-Links, Tags,
             Relevanz, Triage- und Wissensbasis-Status
  fulltext   lokal gespeicherte Volltexte (XML aus Europe PMC, PDF aus Open-Access-Quellen)
  works_fts  Volltextsuche über Titel, Abstract, Schlagwörter
Alles Weitere (Zitationen, Autorenprofile …) wird bei Bedarf live bei OpenAlex abgefragt.

Speicherort außerhalb des Repos: $KB_CORPUS_DIR (Standard ~/kb-corpus)
API-Key: $OPENALEX_API_KEY (in Claude-Cloud-Sessions setzt ihn der Proxy, dort Platzhalter genügt)

Beispiele:
  python tools/corpus/harvest.py --from 2024-11-11              # alle Anfragen aus corpus/queries.yaml
  python tools/corpus/harvest.py --since-last                   # wöchentlicher Lauf ab letztem Lauf
  python tools/corpus/harvest.py --only peg_immunity --from 2020-01-01
  python tools/corpus/harvest.py --fulltext xml                 # freie Volltext-XMLs (Europe PMC)
  python tools/corpus/harvest.py --fulltext pdf --min-relevance 0.5 --limit 200
  python tools/corpus/harvest.py --stats
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
OPENALEX = "https://api.openalex.org/works"
EPMC = "https://www.ebi.ac.uk/europepmc/webservices/rest"
UA = "knowledge-database-corpus/0.2 (personal research use)"
TYPES = "article|review|preprint|letter|book-chapter"
SELECT = ("id,doi,ids,title,publication_date,publication_year,type,authorships,primary_location,"
          "open_access,best_oa_location,abstract_inverted_index,cited_by_count,topics,keywords")

SCHEMA = """
CREATE TABLE IF NOT EXISTS works(
  id TEXT PRIMARY KEY, doi TEXT, pmid TEXT, pmcid TEXT, title TEXT, abstract TEXT, authors TEXT,
  venue TEXT, pub_date TEXT, year INTEGER, type TEXT, is_oa INTEGER, oa_status TEXT, oa_url TEXT,
  pdf_url TEXT, license TEXT, cited_by INTEGER, topics TEXT, keywords TEXT, tags TEXT,
  first_seen TEXT, updated TEXT, relevance REAL, triage TEXT, kb_status TEXT);
CREATE INDEX IF NOT EXISTS works_doi ON works(doi);
CREATE TABLE IF NOT EXISTS fulltext(
  work_id TEXT, kind TEXT, path TEXT, status TEXT, fetched TEXT, PRIMARY KEY(work_id, kind));
CREATE TABLE IF NOT EXISTS runs(
  query TEXT, date_from TEXT, date_to TEXT, started TEXT, finished TEXT, hits INTEGER, new INTEGER);
CREATE VIRTUAL TABLE IF NOT EXISTS works_fts USING fts5(
  id UNINDEXED, title, abstract, keywords, tokenize='unicode61 remove_diacritics 2');
"""


# ---------------------------------------------------------------- HTTP

def http(url: str, params: dict | None = None, headers: dict | None = None, tries: int = 5,
         pause: float = 0.2) -> bytes | None:
    if params:
        url = f"{url}?{urllib.parse.urlencode(params)}"
    h = {"User-Agent": UA, **(headers or {})}
    for i in range(tries):
        try:
            with urllib.request.urlopen(urllib.request.Request(url, headers=h), timeout=120) as r:
                data = r.read()
            time.sleep(pause)
            return data
        except urllib.error.HTTPError as e:
            if e.code in (404, 410):
                return None
            if e.code == 429:
                wait = int(e.headers.get("Retry-After", 30))
                if wait > 600:
                    sys.exit(f"OpenAlex-Tageskontingent erschöpft, Reset in {wait // 60} min.")
                time.sleep(wait)
                continue
            if e.code in (401, 403) and "openalex" in url:
                sys.exit("OpenAlex lehnt den Key ab (401/403). OPENALEX_API_KEY prüfen.")
            if i == tries - 1:
                raise
        except (urllib.error.URLError, TimeoutError, ConnectionError):
            if i == tries - 1:
                raise
        time.sleep(2 ** (i + 1))
    return None


def openalex(params: dict) -> dict:
    key = os.environ.get("OPENALEX_API_KEY", "proxy-injected")
    return json.loads(http(OPENALEX, params, {"Authorization": f"Bearer {key}"}))


# ---------------------------------------------------------------- Datenbank

def connect() -> sqlite3.Connection:
    CORPUS.mkdir(parents=True, exist_ok=True)
    for d in ("xml", "pdf"):
        (CORPUS / d).mkdir(exist_ok=True)
    con = sqlite3.connect(CORPUS / "corpus.sqlite")
    con.executescript(SCHEMA)
    return con


def abstract(inv: dict | None) -> str | None:
    if not inv:
        return None
    pos = sorted((p, w) for w, ps in inv.items() for p in ps)
    return " ".join(w for _, w in pos)


def record(w: dict) -> dict:
    ids = w.get("ids") or {}
    pmid = (ids.get("pmid") or "").rsplit("/", 1)[-1] or None
    pmcid = (ids.get("pmcid") or "").rsplit("/", 1)[-1] or None
    if pmcid and not pmcid.upper().startswith("PMC"):
        pmcid = f"PMC{pmcid}"
    oa = w.get("open_access") or {}
    best = w.get("best_oa_location") or {}
    src = ((w.get("primary_location") or {}).get("source") or {}).get("display_name")
    authors = [((a.get("author") or {}).get("display_name") or "") for a in (w.get("authorships") or [])]
    return {
        "id": w["id"].rsplit("/", 1)[-1],
        "doi": (w.get("doi") or "").replace("https://doi.org/", "").lower() or None,
        "pmid": pmid, "pmcid": pmcid, "title": w.get("title"),
        "abstract": abstract(w.get("abstract_inverted_index")),
        "authors": "; ".join(authors[:30]) + (" et al." if len(authors) > 30 else ""),
        "venue": src, "pub_date": w.get("publication_date"), "year": w.get("publication_year"),
        "type": w.get("type"), "is_oa": int(bool(oa.get("is_oa"))), "oa_status": oa.get("oa_status"),
        "oa_url": oa.get("oa_url"), "pdf_url": best.get("pdf_url"), "license": best.get("license"),
        "cited_by": w.get("cited_by_count"),
        "topics": "; ".join(t.get("display_name", "") for t in (w.get("topics") or [])[:5]),
        "keywords": "; ".join(k.get("display_name", "") for k in (w.get("keywords") or [])),
    }


def upsert(con: sqlite3.Connection, rec: dict, tag: str) -> bool:
    now = dt.datetime.now().isoformat(timespec="seconds")
    row = con.execute("SELECT id, tags FROM works WHERE id=? OR (doi IS NOT NULL AND doi=?)",
                      (rec["id"], rec["doi"])).fetchone()
    if row:
        tags = ";".join(sorted(set(filter(None, (row[1] or "").split(";"))) | {tag}))
        upd = {k: v for k, v in rec.items() if k != "id" and v not in (None, "")}
        upd.update(tags=tags, updated=now)
        con.execute(f"UPDATE works SET {', '.join(f'{k}=?' for k in upd)} WHERE id=?", (*upd.values(), row[0]))
        con.execute("DELETE FROM works_fts WHERE id=?", (row[0],))
        wid, new = row[0], False
    else:
        rec = {**rec, "tags": tag, "first_seen": now, "updated": now, "triage": "new"}
        con.execute(f"INSERT INTO works({', '.join(rec)}) VALUES ({','.join('?' * len(rec))})", tuple(rec.values()))
        wid, new = rec["id"], True
    t, a, k = con.execute("SELECT title, abstract, keywords FROM works WHERE id=?", (wid,)).fetchone()
    con.execute("INSERT INTO works_fts VALUES (?,?,?,?)", (wid, t or "", a or "", k or ""))
    return new


# ---------------------------------------------------------------- Einsammeln

def harvest(con, name: str, query: str, date_from: str, date_to: str) -> None:
    if "," in query:
        sys.exit(f"Anfrage {name}: Kommas sind in OpenAlex-Filtern nicht erlaubt.")
    flt = (f"title_and_abstract.search:{query},from_publication_date:{date_from},"
           f"to_publication_date:{date_to},type:{TYPES}")
    started = dt.datetime.now().isoformat(timespec="seconds")
    cursor, hits, new, seen = "*", None, 0, 0
    while cursor:
        d = openalex({"filter": flt, "per-page": 200, "cursor": cursor, "select": SELECT})
        hits = d["meta"]["count"] if hits is None else hits
        for w in d.get("results", []):
            new += upsert(con, record(w), name)
        seen += len(d.get("results", []))
        con.commit()
        print(f"  {name}: {seen}/{hits}, {new} neu", end="\r", flush=True)
        cursor = d["meta"].get("next_cursor") if d.get("results") else None
    con.execute("INSERT INTO runs VALUES (?,?,?,?,?,?,?)",
                (name, date_from, date_to, started, dt.datetime.now().isoformat(timespec="seconds"), hits, new))
    con.commit()
    print(f"  {name}: {hits} Treffer, {new} neu{' ' * 20}")


def last_run_date(con, name: str) -> str | None:
    r = con.execute("SELECT max(date_to) FROM runs WHERE query=?", (name,)).fetchone()
    if not r or not r[0]:
        return None
    # 14 Tage Überlappung: OpenAlex nimmt Paper oft verspätet auf
    return (dt.date.fromisoformat(r[0]) - dt.timedelta(days=14)).isoformat()


# ---------------------------------------------------------------- Volltexte

def fetch_xml(con, limit, min_rel) -> None:
    rows = con.execute(f"""SELECT w.id, w.pmcid FROM works w
        LEFT JOIN fulltext f ON f.work_id=w.id AND f.kind='xml'
        WHERE w.pmcid IS NOT NULL AND f.work_id IS NULL {rel_clause(min_rel)}
        ORDER BY w.relevance DESC, w.pub_date DESC""").fetchall()[: limit or None]
    print(f"{len(rows)} Volltext-XMLs zu laden (Europe PMC)")
    for i, (wid, pmcid) in enumerate(rows, 1):
        data = http(f"{EPMC}/{pmcid}/fullTextXML", pause=0.3)
        store(con, wid, "xml", CORPUS / "xml" / f"{pmcid}.xml", data)
        progress(con, i, len(rows))


def fetch_pdf(con, limit, min_rel) -> None:
    rows = con.execute(f"""SELECT w.id, w.pdf_url FROM works w
        LEFT JOIN fulltext f ON f.work_id=w.id AND f.kind IN ('xml','pdf') AND f.status='ok'
        WHERE w.pdf_url IS NOT NULL AND f.work_id IS NULL {rel_clause(min_rel)}
        ORDER BY w.relevance DESC, w.pub_date DESC""").fetchall()[: limit or None]
    print(f"{len(rows)} PDFs zu laden (Open-Access-Quellen laut OpenAlex)")
    for i, (wid, url) in enumerate(rows, 1):
        try:
            data = http(url, tries=2, pause=1.0)
        except Exception:
            data = None
        if data and not data.startswith(b"%PDF"):
            data = None  # Verlagsseite statt PDF
        store(con, wid, "pdf", CORPUS / "pdf" / f"{wid}.pdf", data)
        progress(con, i, len(rows))


def rel_clause(min_rel) -> str:
    return f"AND w.relevance >= {float(min_rel)}" if min_rel is not None else ""


def store(con, wid, kind, path: Path, data) -> None:
    now = dt.datetime.now().isoformat(timespec="seconds")
    if data:
        path.write_bytes(data)
        con.execute("INSERT OR REPLACE INTO fulltext VALUES (?,?,?,?,?)",
                    (wid, kind, str(path.relative_to(CORPUS)), "ok", now))
    else:
        con.execute("INSERT OR REPLACE INTO fulltext VALUES (?,?,?,?,?)", (wid, kind, None, "missing", now))


def progress(con, i, n) -> None:
    if i % 25 == 0 or i == n:
        con.commit()
        print(f"  {i}/{n}", end="\r" if i < n else "\n", flush=True)


# ---------------------------------------------------------------- Übersicht

def stats(con) -> None:
    one = lambda s: con.execute(s).fetchone()[0]
    print(f"Korpus: {CORPUS}")
    print(f"  Paper gesamt:          {one('SELECT count(*) FROM works')}")
    print(f"  Open Access:           {one('SELECT count(*) FROM works WHERE is_oa=1')}")
    print(f"  mit PMCID (XML mögl.): {one('SELECT count(*) FROM works WHERE pmcid IS NOT NULL')}")
    print(f"  mit PDF-Link:          {one('SELECT count(*) FROM works WHERE pdf_url IS NOT NULL')}")
    for kind, n in con.execute("SELECT kind, count(*) FROM fulltext WHERE status='ok' GROUP BY kind"):
        print(f"  Volltext {kind} geladen:  {n}")
    print(f"  mit Relevanz-Score:    {one('SELECT count(*) FROM works WHERE relevance IS NOT NULL')}")
    print("  Paper je Anfrage:")
    tags: dict[str, int] = {}
    for (t,) in con.execute("SELECT tags FROM works"):
        for x in (t or "").split(";"):
            tags[x] = tags.get(x, 0) + 1
    for t, n in sorted(tags.items(), key=lambda x: -x[1]):
        print(f"    {t:24} {n}")
    size = sum(p.stat().st_size for p in CORPUS.rglob("*") if p.is_file()) / 1e6
    print(f"  Speicher:              {size:.0f} MB")


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--from", dest="date_from", help="Startdatum JJJJ-MM-TT (Erscheinungsdatum)")
    ap.add_argument("--to", dest="date_to", default=dt.date.today().isoformat())
    ap.add_argument("--since-last", action="store_true", help="je Anfrage ab dem letzten Lauf (−14 Tage)")
    ap.add_argument("--only", nargs="*", help="nur diese Anfragen aus corpus/queries.yaml")
    ap.add_argument("--fulltext", choices=["xml", "pdf"], help="Volltexte laden")
    ap.add_argument("--min-relevance", type=float, help="Volltexte nur ab diesem Relevanz-Score")
    ap.add_argument("--limit", type=int, help="max. Anzahl Volltexte")
    ap.add_argument("--stats", action="store_true")
    a = ap.parse_args()
    con = connect()
    if a.date_from or a.since_last:
        queries = yaml.safe_load((REPO / "corpus" / "queries.yaml").read_text(encoding="utf-8"))["queries"]
        for name, spec in queries.items():
            if a.only and name not in a.only:
                continue
            start = a.date_from or last_run_date(con, name)
            if not start:
                print(f"  {name}: noch nie gelaufen, bitte einmal mit --from starten")
                continue
            harvest(con, name, " ".join(spec["query"].split()), start, a.date_to)
    if a.fulltext == "xml":
        fetch_xml(con, a.limit, a.min_relevance)
    elif a.fulltext == "pdf":
        fetch_pdf(con, a.limit, a.min_relevance)
    if a.stats or not (a.date_from or a.since_last or a.fulltext):
        stats(con)
    return 0


if __name__ == "__main__":
    sys.exit(main())
