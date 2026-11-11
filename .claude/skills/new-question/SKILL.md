---
name: new-question
description: Eine neue Forschungsfrage aufnehmen und die Datenbasis gezielt dafür erweitern. Nutzen bei "neue Fragestellung", "ich will wissen ob", "was wissen wir über", oder wenn eine Frage Daten braucht, die noch fehlen.
---

# Neue Fragestellung

1. `python tools/build_index.py`, dann `questions/Q-NNN.md` aus `templates/question.md` (nächste freie Nummer).
2. **Bestand abfragen** (kb.sqlite): Volltext (`notes_fts MATCH …`), relevante Zeilen in
   `measurements_full`, `components`, `process`. Ergebnis mit IDs unter „Was die Datenbasis schon sagt“.
3. **Lücken benennen:** fehlende Größen, Komponenten, Wertebereiche, Bedingungen → `data_needs`.
   Prüfen, ob schon vorhandene Paper (status stub/read) die Lücke füllen würden → diese zuerst extrahieren.
4. **Erweitern:** gezielte Literatursuche (Zotero, PubMed, Consensus, Undermind); Treffer dem Nutzer
   als Liste vorschlagen, nach Zustimmung in Zotero/als Stub anlegen und mit `ingest-paper` einpflegen.
   Fehlt ein Feld im Schema, `vocab/` bzw. `schemas/` erweitern (Langformat macht das ohne Umbau möglich).
5. Vorläufige Antwort und daraus folgende Ideen festhalten; commit `Q-NNN …`.
