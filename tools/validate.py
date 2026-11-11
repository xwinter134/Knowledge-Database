"""Prüft Frontmatter, ID-Eindeutigkeit, Verweise und Tabellen. Exit-Code 1 bei Fehlern."""
from __future__ import annotations

import sys

from kblib import ROOT, as_list, iter_notes, load_yaml, read_csv

LINK_FIELDS = ["related", "methods", "formulations", "ideas", "questions"]


def main() -> int:
    errors: list[str] = []
    warnings: list[str] = []
    note_schema = load_yaml("schemas/notes.yaml")
    table_schema = load_yaml("schemas/tables.yaml")

    # Tabellen laden
    tables = {n: read_csv(f"data/{n}.csv") for n in table_schema}
    vocab = {
        "vocab/components": {r["component"] for r in read_csv("vocab/components.csv")},
        "vocab/properties": {r["property"] for r in read_csv("vocab/properties.csv")},
        "vocab/process_parameters": {r["parameter"] for r in read_csv("vocab/process_parameters.csv")},
    }
    formulation_ids = {r["formulation_id"] for r in tables["formulations"]}

    # Notizen
    ids: dict[str, str] = {}
    notes = []
    for path, fm, _ in iter_notes():
        rel = path.relative_to(ROOT)
        if fm is None:
            errors.append(f"{rel}: kein YAML-Frontmatter")
            continue
        if "_error" in fm:
            errors.append(f"{rel}: YAML-Fehler: {fm['_error']}")
            continue
        t = fm.get("type")
        spec = note_schema["types"].get(t)
        if spec is None:
            errors.append(f"{rel}: unbekannter type '{t}'")
            continue
        for field in note_schema["common"] + spec.get("required", []):
            if field not in fm:
                errors.append(f"{rel}: Pflichtfeld '{field}' fehlt")
        for enum_field in ("status", "source"):
            allowed = spec.get(enum_field)
            if allowed and fm.get(enum_field) not in allowed:
                errors.append(f"{rel}: {enum_field}='{fm.get(enum_field)}' nicht in {allowed}")
        if path.parent.name != spec["dir"]:
            warnings.append(f"{rel}: type '{t}' gehört nach {spec['dir']}/")
        nid = str(fm.get("id", ""))
        if path.stem != nid:
            warnings.append(f"{rel}: Dateiname ≠ id '{nid}'")
        if nid in ids:
            errors.append(f"{rel}: id '{nid}' doppelt (auch in {ids[nid]})")
        ids[nid] = str(rel)
        notes.append((rel, fm))

    known = set(ids) | formulation_ids
    for rel, fm in notes:
        for field in LINK_FIELDS:
            for target in as_list(fm.get(field)):
                if str(target) not in known:
                    warnings.append(f"{rel}: Verweis {field} → '{target}' existiert (noch) nicht")

    # Tabellen prüfen
    for name, spec in table_schema.items():
        rows = tables[name]
        key = spec.get("key")
        seen = set()
        for i, row in enumerate(rows, start=2):
            loc = f"data/{name}.csv:{i}"
            for col in spec.get("required", []):
                if not (row.get(col) or "").strip():
                    errors.append(f"{loc}: Pflichtspalte '{col}' leer")
            if key:
                if row.get(key) in seen:
                    errors.append(f"{loc}: Schlüssel '{row.get(key)}' doppelt")
                seen.add(row.get(key))
            for col, allowed in spec.get("enums", {}).items():
                if (row.get(col) or "") not in allowed:
                    errors.append(f"{loc}: {col}='{row.get(col)}' nicht in {allowed}")
            for col, target in spec.get("refs", {}).items():
                val = row.get(col) or ""
                if target.startswith("vocab/"):
                    pool = vocab[target.split(".")[0]]
                else:
                    pool = formulation_ids
                if val and val not in pool:
                    errors.append(f"{loc}: {col}='{val}' unbekannt (→ {target})")
        if name in ("formulations", "measurements"):
            for i, row in enumerate(rows, start=2):
                sid = row.get("source_id")
                if sid and sid not in ids and not sid.startswith("EXP-"):
                    warnings.append(f"data/{name}.csv:{i}: source_id '{sid}' hat keine Notiz")

    for w in warnings:
        print(f"WARN  {w}")
    for e in errors:
        print(f"FEHLER {e}")
    print(f"{len(ids)} Notizen, {sum(len(r) for r in tables.values())} Tabellenzeilen, "
          f"{len(errors)} Fehler, {len(warnings)} Warnungen")
    return 1 if errors else 0


if __name__ == "__main__":
    sys.exit(main())
