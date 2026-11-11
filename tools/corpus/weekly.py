"""Wochenlauf: neue Paper einsammeln → ranken → Top-Paper nach Zotero → Wochenbericht schreiben.

Läuft zustandslos (z. B. in einer frischen Cloud-Session): Der Korpus wird für das Zeitfenster neu
geholt; was schon übertragen wurde, steht in corpus/state/zotero_pushed.csv (im Repo, wird committet).
Ergebnis: corpus/digests/<JJJJ>-W<KW>.md

  python tools/corpus/weekly.py              # kompletter Lauf
  python tools/corpus/weekly.py --dry-run    # ohne Zotero-Schreiben
"""
from __future__ import annotations

import argparse
import csv
import datetime as dt
import os
import sqlite3
import subprocess
import sys
import tempfile
from pathlib import Path

import yaml

REPO = Path(__file__).resolve().parents[2]
CONFIG = yaml.safe_load((REPO / "corpus" / "config.yaml").read_text(encoding="utf-8"))
TOOLS = REPO / "tools" / "corpus"


def run(*args: str) -> str:
    out = subprocess.run([sys.executable, *args], capture_output=True, text=True, env=os.environ)
    if out.returncode:
        sys.exit(f"Fehler in {args[0]}:\n{out.stdout}\n{out.stderr}")
    return out.stdout.replace("\r", "\n")


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--corpus-dir", help="vorhandenen Korpus nutzen statt temporärem")
    a = ap.parse_args()

    today = dt.date.today()
    start = (today - dt.timedelta(days=CONFIG["weekly"]["lookback_days"])).isoformat()
    corpus = Path(a.corpus_dir) if a.corpus_dir else Path(tempfile.mkdtemp(prefix="kb-weekly-"))
    os.environ["KB_CORPUS_DIR"] = str(corpus)

    log_h = run(str(TOOLS / "harvest.py"), "--from", start)
    log_r = run(str(TOOLS / "rank.py"), "--top", "0")
    push_args = [str(TOOLS / "zotero_push.py"), "--since", start] + (["--dry-run"] if a.dry_run else [])
    log_p = run(*push_args)

    con = sqlite3.connect(corpus / "corpus.sqlite")
    con.row_factory = sqlite3.Row
    pushed_ids = set()
    state = REPO / "corpus" / "state" / "zotero_pushed.csv"
    if state.exists():
        with state.open(encoding="utf-8") as f:
            pushed_ids = {r["openalex_id"] for r in csv.DictReader(f) if r["pushed"] == today.isoformat()}
    if a.dry_run:
        pushed_ids = {r["id"] for r in con.execute(
            "SELECT id FROM works WHERE relevance >= ? AND coalesce(kb_status,'')!='zotero' AND pub_date >= ?",
            (CONFIG["zotero"]["min_relevance"], start))}

    n_all = con.execute("SELECT count(*) FROM works").fetchone()[0]
    top = con.execute(f"""SELECT * FROM works WHERE id IN ({','.join('?' * len(pushed_ids))})
                          ORDER BY relevance DESC LIMIT ?""", (*pushed_ids, CONFIG["weekly"]["digest_top"])
                      ).fetchall() if pushed_ids else []
    tags: dict[str, int] = {}
    for (t,) in con.execute("SELECT tags FROM works WHERE id IN (%s)" % ",".join("?" * len(pushed_ids)),
                            tuple(pushed_ids)) if pushed_ids else []:
        for x in (t or "").split(";"):
            tags[x] = tags.get(x, 0) + 1

    year, week, _ = today.isocalendar()
    out = REPO / "corpus" / "digests" / f"{year}-W{week:02d}.md"
    out.parent.mkdir(parents=True, exist_ok=True)
    lines = [
        f"# Literatur-Wochenbericht {year}-W{week:02d}", "",
        f"Zeitraum: Erscheinungsdatum ab {start} · Lauf am {today.isoformat()}"
        + (" · **Probelauf, nichts nach Zotero geschrieben**" if a.dry_run else ""), "",
        f"- Paper im Zeitfenster gefunden: **{n_all}**",
        f"- Neu nach Zotero („{CONFIG['zotero']['collection']}“, Score ≥ {CONFIG['zotero']['min_relevance']}): "
        f"**{len(pushed_ids)}**",
        "- Themen der neuen Paper: " + (", ".join(f"{k} ({v})" for k, v in sorted(tags.items(), key=lambda x: -x[1]) if k) or "–"),
        "", "## Top-Paper", "",
    ]
    for r in top:
        link = f"https://doi.org/{r['doi']}" if r["doi"] else (r["oa_url"] or "")
        oa = " · OA" if r["is_oa"] else ""
        lines += [f"- **{r['relevance']:.2f}** · [{r['title']}]({link}) · {r['venue'] or '–'} · {r['pub_date']}{oa}",
                  f"  <!-- tags: {r['tags']} -->"]
    if not top:
        lines.append("Keine neuen Paper über der Schwelle.")
    lines += ["", "## Einordnung", "", "<!-- Wird von Claude im Wochen-Task ergänzt: Themen, Bezug zu offenen "
              "Fragen (questions/), Ideen (ideas/). -->", "",
              "<details><summary>Protokoll</summary>", "", "```", log_h.strip(), log_r.strip()[:1500],
              log_p.strip()[:1500], "```", "</details>", ""]
    out.write_text("\n".join(lines), encoding="utf-8")
    print(f"Bericht: {out.relative_to(REPO)} · {n_all} gefunden · {len(pushed_ids)} nach Zotero")
    return 0


if __name__ == "__main__":
    sys.exit(main())
