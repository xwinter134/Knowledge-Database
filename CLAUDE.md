# Knowledge Database – Regeln für Claude

Persönliche Forschungs-Wissensbasis (ein Nutzer). Ziel: (1) alles Forschungsrelevante strukturiert
festhalten, (2) maschinenlesbare Daten für KI/ML-Experimente liefern, (3) neue Ideen erzeugen.

## Grundprinzipien

1. **Git-Repo = Quelle der Wahrheit** für Text, Metadaten und Tabellen. Die SQLite-Datei
   `kb.sqlite` wird nur abgeleitet (`python tools/build_index.py`) und nie committet.
2. **Große Dateien liegen in OneDrive** (`Knowledge-Database/`), im Repo steht nur der Verweis
   (Feld `files:` im Frontmatter, relativer Pfad ab `Knowledge-Database/`).
3. **Zahlen gehören in `data/*.csv`, nicht in Fließtext.** Jede extrahierte Messgröße bekommt eine
   Zeile in `data/measurements.csv` mit Quelle (`source_id`) und Fundstelle (`locator`, z. B. „Tab. 2“).
4. **Kontrolliertes Vokabular:** Komponenten nur mit Namen aus `vocab/components.csv`, Messgrößen
   nur aus `vocab/properties.csv` (mit kanonischer Einheit). Neue Begriffe dort zuerst eintragen.
5. **Nie erfinden.** Werte, die im Paper nicht stehen, bleiben leer. Abgelesene Werte aus Abbildungen
   bekommen `extraction: figure_estimate`. Unsicherheiten ins Feld `notes`.
6. **Herkunft trennen:** `source_type` ist `paper`, `own_experiment` oder `simulation`.

## IDs (stabil, nie umbenennen)

| Typ | Muster | Beispiel |
|---|---|---|
| Paper | Citekey `nachnameJAHRwort` | `hald2022lipid` |
| Formulierung | `F-<quelle>-<nr>` | `F-hald2022lipid-03`, `F-EXP-2026-014-01` |
| Experiment | `EXP-JJJJ-NNN` | `EXP-2026-014` |
| Methode | `M-<kurzname>` | `M-saxs-lnp` |
| Projekt | `P-<kurzname>` | `P-ml-lnp-screening` |
| Frage | `Q-NNN` | `Q-001` |
| Idee | `I-NNN` | `I-012` |
| Session | `S-JJJJ-MM-TT-<thema>` | `S-2026-11-11-kb-setup` |

Verknüpfungen stehen im Frontmatter als Listen von IDs (`related:`, `methods:`, `formulations:` …).
Im Text gern zusätzlich `[[ID]]` (Obsidian-kompatibel).

## Workflows (Skills in `.claude/skills/`)

- **Paper einpflegen** → `ingest-paper`: Notiz in `literature/`, Formulierungen und Messwerte in `data/`.
- **Neue Fragestellung** → `new-question`: Frage anlegen, Lücken in der Datenbasis bestimmen, gezielt erweitern.
- **Ideen erzeugen** → `generate-ideas`: Querverbindungen und Lücken aus Index + Daten, Ergebnis nach `ideas/`.
- **Session protokollieren** → `log-session`: am Ende jeder inhaltlichen Session Zusammenfassung nach `sessions/`.

**Standardverhalten:** Wenn in einer Session etwas Forschungsrelevantes entstanden ist (Entscheidung,
Ergebnis, Idee, neue Quelle), am Ende ungefragt `log-session` ausführen und vorgeschlagene Ideen
zusätzlich als `ideas/I-NNN.md` anlegen (Status `raw`).

Vor dem Commit immer: `python tools/validate.py`. Commit-Nachrichten auf Deutsch, kurz, mit ID(s).

## OneDrive (Microsoft-365-Connector, persönliches Konto)

driveId `352A4C8A7A3FF5C5`, Wurzelordner `Knowledge-Database`
(itemId `352A4C8A7A3FF5C5!sd556946529ef48bf885ac58651049206`). Unterordner:

| Ordner | itemId | Inhalt |
|---|---|---|
| `00_inbox` | `352A4C8A7A3FF5C5!sec28545c65c045ffa22f84e9d181178d` | Unsortiertes, wird von Claude einsortiert |
| `literature` | `352A4C8A7A3FF5C5!s083dd0b7baa34c32b8a55207c9abef96` | PDFs/Supplements: `<citekey>.pdf`, `<citekey>_SI.pdf` |
| `experiments` | `352A4C8A7A3FF5C5!s713b07b8684041178b2972930e9e6a4d` | Rohdaten je `EXP-…/raw/` |
| `datasets` | `352A4C8A7A3FF5C5!s7b04f58c38a64cd5a9e65ce683030529` | Exportierte ML-Datensätze (Snapshots) |
| `figures` | `352A4C8A7A3FF5C5!s251343c6be924e1bbfa97989fa5bf056` | Abbildungen |
| `backups` | `352A4C8A7A3FF5C5!sb437024e236d4968aad1f3616ab50e21` | z. B. `kb.sqlite`-Snapshots, Zotero-Export |
