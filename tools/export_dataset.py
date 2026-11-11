"""Pivotiert die Langformat-Tabellen in eine breite ML-Feature-Matrix.

Eine Zeile pro Formulierung. Spalten:
  comp_<komponente>_mol      Molanteil jeder Komponente
  proc_<parameter>           Prozessparameter
  y_<property>               Messwert (Mittel, falls mehrere Messungen; Methode/Bedingung siehe --long)
Aufruf: python tools/export_dataset.py [--source paper|own_experiment] [--out exports/dataset.csv]
"""
from __future__ import annotations

import argparse
import csv
from collections import defaultdict
from statistics import mean

from kblib import ROOT, read_csv


def to_float(v):
    try:
        return float(v)
    except (TypeError, ValueError):
        return v or None


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--source", choices=["paper", "own_experiment", "simulation"])
    ap.add_argument("--out", default="exports/dataset.csv")
    args = ap.parse_args()

    forms = {r["formulation_id"]: r for r in read_csv("data/formulations.csv")
             if not args.source or r["source_type"] == args.source}
    rows: dict[str, dict] = {fid: {"formulation_id": fid, "source_type": f["source_type"],
                                    "source_id": f["source_id"], "formulation_type": f["formulation_type"],
                                    "cargo": f["cargo"]} for fid, f in forms.items()}
    for c in read_csv("data/components.csv"):
        if c["formulation_id"] in rows:
            rows[c["formulation_id"]][f"comp_{c['component']}_mol"] = to_float(c["mol_percent"])
    for p in read_csv("data/process.csv"):
        if p["formulation_id"] in rows:
            rows[p["formulation_id"]][f"proc_{p['parameter']}"] = to_float(p["value"])
    ys: dict[tuple, list] = defaultdict(list)
    for m in read_csv("data/measurements.csv"):
        v = to_float(m["value"])
        if m["formulation_id"] in rows and isinstance(v, float):
            ys[(m["formulation_id"], m["property"])].append(v)
    for (fid, prop), vals in ys.items():
        rows[fid][f"y_{prop}"] = mean(vals)

    cols = sorted({k for r in rows.values() for k in r},
                  key=lambda k: (not k in ("formulation_id", "source_type", "source_id",
                                           "formulation_type", "cargo"),
                                 k.split("_")[0], k))
    out = ROOT / args.out
    out.parent.mkdir(parents=True, exist_ok=True)
    with out.open("w", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(f, fieldnames=cols)
        w.writeheader()
        w.writerows(rows.values())
    print(f"{out.relative_to(ROOT)}: {len(rows)} Formulierungen × {len(cols)} Spalten")


if __name__ == "__main__":
    main()
