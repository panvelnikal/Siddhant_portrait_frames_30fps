"""Turn a rough idea into a LinkedIn post and an Instagram caption using Claude."""
import json
import re
from pathlib import Path

from .config import settings

SYSTEM = """You write social posts for a college student building their personal brand.
Imitate the voice in the tone samples. Be concrete and honest; never invent achievements,
numbers, names, or events that are not in the user's notes.
Return ONLY JSON: {"linkedin": "...", "instagram": "...", "hashtags": ["..."]}
- linkedin: 600-1300 chars, strong first line (hook), short paragraphs, at most 3 hashtags at the end.
- instagram: 100-300 chars, casual, ends with a question or call to action. No hashtags inside; put 5-10 in "hashtags" (without #)."""


def _tone() -> str:
    p = Path(settings.tone_path)
    return p.read_text()[:4000] if p.exists() else ""


def draft(idea: str) -> dict:
    if not settings.anthropic_key:
        return _fallback(idea)
    import anthropic

    client = anthropic.Anthropic(api_key=settings.anthropic_key)
    msg = client.messages.create(
        model=settings.claude_model,
        max_tokens=1500,
        system=SYSTEM,
        messages=[{"role": "user", "content": f"<tone_samples>\n{_tone()}\n</tone_samples>\n\n<notes>\n{idea}\n</notes>"}],
    )
    text = "".join(b.text for b in msg.content if b.type == "text")
    return _parse(text)


def _parse(text: str) -> dict:
    m = re.search(r"\{.*\}", text, re.S)
    data = json.loads(m.group(0)) if m else {}
    tags = [t.lstrip("#") for t in data.get("hashtags", [])][:10]
    ig = data.get("instagram", "").strip()
    if tags:
        ig += "\n\n" + " ".join(f"#{t}" for t in tags)
    return {"linkedin": data.get("linkedin", "").strip(), "instagram": ig, "hashtags": tags}


def _fallback(idea: str) -> dict:
    """No API key: simple template so the pipeline stays usable."""
    return {
        "linkedin": f"{idea.strip()}\n\nWhat's one thing you learned recently? Tell me below.",
        "instagram": f"{idea.strip()[:250]}\n\nThoughts?",
        "hashtags": [],
    }
