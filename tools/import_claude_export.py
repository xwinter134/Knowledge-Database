"""Zerlegt einen claude.ai-Datenexport (conversations.json) in eine Markdown-Datei pro Chat.

Ausgabe: sessions/_import/<datum>-<titel>.md (nicht versioniert, siehe .gitignore).
Danach mit dem Skill log-session das Forschungsrelevante als Session-Notiz übernehmen.
Aufruf: python tools/import_claude_export.py conversations.json [--since JJJJ-MM-TT]
"""
from __future__ import annotations

import argparse
import json
import re
from pathlib import Path

from kblib import ROOT


def text_of(msg: dict) -> str:
    if msg.get("text"):
        return msg["text"]
    parts = msg.get("content") or []
    return "\n".join(p.get("text", "") for p in parts if isinstance(p, dict) and p.get("type") == "text")


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("export", type=Path)
    ap.add_argument("--since", default="")
    args = ap.parse_args()
    convs = json.loads(args.export.read_text(encoding="utf-8"))
    out = ROOT / "sessions" / "_import"
    out.mkdir(parents=True, exist_ok=True)
    n = 0
    for c in convs:
        date = (c.get("created_at") or "")[:10]
        if args.since and date < args.since:
            continue
        title = c.get("name") or "ohne-titel"
        slug = re.sub(r"[^a-z0-9]+", "-", title.lower()).strip("-")[:50] or "chat"
        lines = [f"# {title}", f"uuid: {c.get('uuid', '')}  ", f"datum: {date}", ""]
        for m in c.get("chat_messages", []):
            who = "Ich" if m.get("sender") == "human" else "Claude"
            lines += [f"## {who}", text_of(m).strip(), ""]
        (out / f"{date}-{slug}.md").write_text("\n".join(lines), encoding="utf-8")
        n += 1
    print(f"{n} Chats nach {out.relative_to(ROOT)}/ geschrieben")


if __name__ == "__main__":
    main()
