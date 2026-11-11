# Knowledge Database

Persönliche Forschungs-Wissensbasis: Paper, Methoden, Formulierungsparameter, eigene Experimente,
Projekte, Claude-Sessions, Ideen und Interessen – als Markdown + CSV in Git, mit abgeleitetem
SQLite-Index für Abfragen und ML.

## Aufbau

```
literature/    1 Notiz pro Paper (<citekey>.md), Kernaussagen, Methoden, Limitationen
methods/       Protokolle & Analysemethoden (M-…)
experiments/   eigene Experimente (EXP-…), Verweis auf Rohdaten in OneDrive
projects/      Projekte & GitHub-Repos (P-…)
questions/     Forschungsfragen (Q-…): treiben die gezielte Erweiterung der Datenbasis
ideas/         Ideen & Hypothesen (I-…), Status raw → refined → tested / dropped
sessions/      Zusammenfassungen von Claude-Sessions (S-…)
interests/     Themen außerhalb der Kernforschung
people/        Autoren, Gruppen, Kooperationen
data/          ML-fähige Tabellen: formulations, components, process, measurements
vocab/         kontrolliertes Vokabular (Komponenten, Messgrößen + Einheiten)
schemas/       Pflichtfelder je Notiztyp und Spalten je Tabelle
tools/         build_index.py, validate.py, zotero_sync.py, export_dataset.py
```

Große Dateien (PDFs, Rohdaten) liegen in OneDrive unter `Knowledge-Database/` (siehe `CLAUDE.md`).

## Nutzung

```bash
pip install -r requirements.txt
python tools/validate.py          # Schema- und Referenzprüfung
python tools/build_index.py       # erzeugt kb.sqlite (Volltextsuche + alle Tabellen)
python tools/export_dataset.py    # breite ML-Tabelle → exports/dataset.csv
ZOTERO_USER_ID=… ZOTERO_API_KEY=… python tools/zotero_sync.py   # neue Paper als Notiz-Stubs
```

## Datenmodell für ML (Langformat)

- `formulations.csv` – eine Zeile pro Formulierung (Quelle, Typ, Cargo, Kurzbeschreibung)
- `components.csv` – eine Zeile pro Komponente einer Formulierung (Rolle, Molanteil, Massenverhältnis)
- `process.csv` – Prozessparameter als Name/Wert/Einheit (Mischmethode, Flussrate, N/P, Puffer …)
- `measurements.csv` – eine Zeile pro Messwert (Größe, Wert, Fehler, Einheit, Methode, Bedingung, Fundstelle)

Das Langformat erlaubt neue Parameter ohne Schemaänderung; `export_dataset.py` pivotiert in eine
breite Feature-Matrix.

## Korpus (breite Literaturerfassung)

Getrennt von der kuratierten Wissensbasis: automatisch eingesammelte Paper mit Metadaten, Abstracts
und freien Volltexten. Liegt außerhalb des Repos in `$KB_CORPUS_DIR` (Standard `~/kb-corpus`).

```bash
python tools/corpus/harvest.py --from 2024-11-11   # Anfragen aus corpus/queries.yaml, wiederholbar
python tools/corpus/harvest.py --fulltext          # freie Volltext-XMLs (Europe PMC/PMC)
python tools/corpus/harvest.py --stats
```

Suchanfragen anpassen in `corpus/queries.yaml`. Relevante Paper wandern später als Stub nach `literature/`.
