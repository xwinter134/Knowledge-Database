---
name: log-session
description: Die aktuelle Claude-Session (oder einen eingefügten/exportierten claude.ai-Chat) als Session-Notiz in die Wissensbasis übernehmen. Nutzen am Ende jeder inhaltlichen Session, bei "protokolliere", "speichere die Session", "übernimm diesen Chat".
---

# Session protokollieren

1. `sessions/S-JJJJ-MM-TT-<thema>.md` aus `templates/session.md`; `source` = claude_code | claude_ai.
2. Nur Destillat, kein Transkript: Ziel, Ergebnisse, Entscheidungen (mit Begründung), neue Quellen,
   offene Punkte. Konkrete Zahlen/Parameter zusätzlich in `data/` eintragen.
3. Jede Idee aus der Session → `ideas/I-NNN.md` (origin = Session-ID); IDs im Feld `ideas`.
4. Berührte Einträge in `related` verlinken und dort ggf. ergänzen (z. B. Status einer Frage).
5. Bei Import mehrerer exportierter Chats (`conversations.json` aus dem claude.ai-Datenexport):
   `python tools/import_claude_export.py <datei>` legt Rohzusammenfassungen in `sessions/_import/` ab;
   danach je Chat dieses Skill anwenden und nur Forschungsrelevantes übernehmen.
6. `python tools/validate.py`, commit `Session S-…`.
