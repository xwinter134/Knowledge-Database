"""Baut kb.sqlite aus Notizen und Tabellen neu auf.

Tabellen:
  notes(id, type, title, path, status, year, created, tags, frontmatter_json, body)
  notes_fts  – FTS5-Volltextindex über title, tags, body
  links(src, dst, field) – alle Verweise aus Frontmatter und [[Wikilinks]]
  + jede CSV aus data/ und vocab/ als eigene Tabelle (vocab_* für Vokabular)
"""
from __future__ import annotations

import json
import sqlite3

from kblib import ROOT, WIKILINK_RE, as_list, iter_notes, read_csv, table_files

LINK_FIELDS = ["related", "methods", "formulations", "ideas", "questions",
               "project", "question", "origin"]
DB = ROOT / "kb.sqlite"


def main() -> None:
    if DB.exists():
        DB.unlink()
    con = sqlite3.connect(DB)
    cur = con.cursor()
    cur.executescript("""
        CREATE TABLE notes(id TEXT PRIMARY KEY, type TEXT, title TEXT, path TEXT, status TEXT,
                           year INTEGER, created TEXT, tags TEXT, frontmatter_json TEXT, body TEXT);
        CREATE VIRTUAL TABLE notes_fts USING fts5(id UNINDEXED, title, tags, body,
                                                  tokenize='unicode61 remove_diacritics 2');
        CREATE TABLE links(src TEXT, dst TEXT, field TEXT);
    """)
    n_notes = 0
    for path, fm, body in iter_notes():
        if not fm or "_error" in fm or "id" not in fm:
            continue
        nid = str(fm["id"])
        tags = " ".join(map(str, as_list(fm.get("tags"))))
        cur.execute("INSERT OR REPLACE INTO notes VALUES (?,?,?,?,?,?,?,?,?,?)", (
            nid, fm.get("type"), fm.get("title"), str(path.relative_to(ROOT)),
            fm.get("status"), fm.get("year"), str(fm.get("created", "")), tags,
            json.dumps(fm, default=str, ensure_ascii=False), body))
        cur.execute("INSERT INTO notes_fts VALUES (?,?,?,?)", (nid, fm.get("title") or "", tags, body))
        for field in LINK_FIELDS:
            for dst in as_list(fm.get(field)):
                if dst:
                    cur.execute("INSERT INTO links VALUES (?,?,?)", (nid, str(dst), field))
        for dst in set(WIKILINK_RE.findall(body)):
            cur.execute("INSERT INTO links VALUES (?,?,?)", (nid, dst.strip(), "wikilink"))
        n_notes += 1

    n_rows = 0
    for name, rel in table_files().items():
        rows = read_csv(rel)
        with (ROOT / rel).open(encoding="utf-8") as f:
            header = f.readline().strip().split(",")
        cols = ", ".join(f'"{c}"' for c in header)
        cur.execute(f'CREATE TABLE "{name}" ({cols})')
        for r in rows:
            vals = [_num(r.get(c)) for c in header]
            cur.execute(f'INSERT INTO "{name}" VALUES ({",".join("?" * len(header))})', vals)
        n_rows += len(rows)

    # Bequeme Sicht: Messwerte mit Formulierungsquelle
    cur.executescript("""
        CREATE VIEW measurements_full AS
        SELECT m.*, f.source_type, f.formulation_type, f.cargo
        FROM measurements m LEFT JOIN formulations f USING (formulation_id);
    """)
    con.commit()
    con.close()
    print(f"kb.sqlite: {n_notes} Notizen, {n_rows} Tabellenzeilen")


def _num(v):
    if v is None or v == "":
        return None
    try:
        return float(v) if any(ch in v for ch in ".eE") else int(v)
    except ValueError:
        return v


if __name__ == "__main__":
    main()
