---
name: generate-ideas
description: Aus der Wissensbasis neue Forschungsideen und Hypothesen erzeugen – Querverbindungen, Widersprüche, unerforschte Parameterbereiche, Methodentransfer. Nutzen bei "Ideen", "Brainstorming", "was könnte ich als nächstes", "Hypothesen".
---

# Ideen erzeugen

`python tools/build_index.py`, dann systematisch suchen (nicht nur frei assoziieren):

1. **Lücken im Parameterraum:** Welche Kombinationen aus Komponenten/Prozessparametern kommen in
   `components`/`process` nie vor, liegen aber zwischen gut performenden Formulierungen?
2. **Widersprüche:** gleiche Formulierung/Bedingung, abweichende Messwerte zwischen Quellen.
3. **Methodentransfer:** Methoden (`methods/`) aus einem Teilgebiet, die in einem anderen nie genutzt wurden.
4. **Brücken zu Interessen:** Konzepte aus `interests/` und `projects/` auf offene `questions/` anwenden.
5. **Vernachlässigte Ideen:** `ideas/` mit status raw und hohem impact – weiterentwickeln.
6. **ML-Ansätze:** Wo reicht die Datenmenge (`export_dataset.py`) für ein Modell, welche Zielgröße,
   welches Feature fehlt am meisten?

Für jede Idee `ideas/I-NNN.md` (origin `generate-ideas`), mit stützenden IDs, Gegenargumenten und
kleinstem Test; novelty/feasibility/impact 0–3 ehrlich bewerten. Dem Nutzer die Top 3–5 vorstellen.
Vor dem Anlegen prüfen, ob es die Idee schon gibt (Volltextsuche).
