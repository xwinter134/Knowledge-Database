---
name: ingest-paper
description: Ein Paper in die Wissensbasis einpflegen – Notiz schreiben und alle forschungsrelevanten Daten (Formulierungen, Prozessparameter, Messwerte, Methoden) in die Tabellen extrahieren. Nutzen bei "Paper einpflegen", "extrahiere aus", Citekey/DOI/PDF-Angabe oder Paper-Stubs mit status stub.
---

# Paper einpflegen

1. **Quelle finden:** Notiz `literature/<citekey>.md` (Stub aus `zotero_sync.py`) oder per DOI neu aus
   `templates/paper.md` anlegen. Volltext: PDF in OneDrive `Knowledge-Database/literature/<citekey>.pdf`
   (Microsoft-365-Connector), sonst Zotero-/PubMed-/Undermind-Tools. Supplement immer mit prüfen –
   dort stehen die meisten Parameter.
2. **Notiz füllen:** alle Abschnitte des Templates; `status: read`.
3. **Extraktion** (danach `status: extracted`):
   - Jede untersuchte Formulierung → `data/formulations.csv` mit ID `F-<citekey>-NN`
     (`source_type: paper`, `source_id: <citekey>`).
   - Zusammensetzung → `data/components.csv` (eine Zeile je Komponente, Molanteil in %).
   - Herstellung → `data/process.csv` (Namen aus `vocab/process_parameters.csv`).
   - Jeder berichtete Wert → `data/measurements.csv`: `measurement_id` = `<formulation_id>-m<NN>`,
     Einheit in kanonische Einheit umrechnen, `locator` (z. B. „Fig. 3b“, „Tab. S2“),
     `extraction` = text | table | figure_estimate, `condition` z. B. „in vitro HeLa 24 h, 100 ng“.
   - Negative/Null-Ergebnisse genauso eintragen – sie sind für ML wichtig.
   - Neue Methode → `methods/M-….md`; neue Komponente/Größe → zuerst in `vocab/`.
4. **Verknüpfen:** `methods`, `formulations`, `related` im Frontmatter; Bezug zu offenen `questions/`.
5. **Ideen-Funken** notieren; vielversprechende als `ideas/I-NNN.md` (status raw, origin = citekey).
6. `python tools/validate.py` → Fehler beheben → commit `Paper <citekey> eingepflegt`.

Bei vielen Papern: in Batches à 5–10 arbeiten, nach jedem Batch validieren und committen.
Nie Werte schätzen, die nicht im Paper stehen.
