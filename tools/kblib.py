"""Gemeinsame Hilfsfunktionen: Notizen und Tabellen einlesen."""
from __future__ import annotations

import csv
import re
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parent.parent
NOTE_DIRS = ["literature", "methods", "experiments", "projects", "questions",
             "ideas", "sessions", "interests", "people"]
FM_RE = re.compile(r"^---\s*\n(.*?)\n---\s*\n?(.*)$", re.S)
WIKILINK_RE = re.compile(r"\[\[([^\]|#]+)")


def load_yaml(rel: str) -> dict:
    return yaml.safe_load((ROOT / rel).read_text(encoding="utf-8"))


def iter_notes():
    """Liefert (path, frontmatter, body) für alle Notizen."""
    for d in NOTE_DIRS:
        for p in sorted((ROOT / d).glob("*.md")):
            text = p.read_text(encoding="utf-8")
            m = FM_RE.match(text)
            if not m:
                yield p, None, text
                continue
            try:
                fm = yaml.safe_load(m.group(1)) or {}
            except yaml.YAMLError as e:
                fm = {"_error": str(e)}
            yield p, fm, m.group(2)


def read_csv(rel: str) -> list[dict]:
    path = ROOT / rel
    if not path.exists():
        return []
    with path.open(encoding="utf-8", newline="") as f:
        return list(csv.DictReader(f))


def table_files() -> dict[str, str]:
    """Name → relativer Pfad aller CSV-Tabellen (data/ und vocab/)."""
    out = {}
    for d in ("data", "vocab"):
        for p in sorted((ROOT / d).glob("*.csv")):
            name = p.stem if d == "data" else f"vocab_{p.stem}"
            out[name] = f"{d}/{p.name}"
    return out


def as_list(v) -> list:
    if v is None or v == "":
        return []
    return v if isinstance(v, list) else [v]
