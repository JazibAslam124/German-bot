# memory.py - Rule-based session memory, zero LLM calls

import json
import os
import re
from datetime import datetime

MEMORY_FILE = "memory.json"

# Interview topics we track weakness on
TOPIC_KEYWORDS = {
    "motivation":    ["motivation", "warum", "wieso", "weshalb", "interesse", "why", "reason"],
    "experience":    ["erfahrung", "gearbeitet", "projekt", "stelle", "position", "experience", "worked"],
    "strengths":     ["stärke", "strength", "gut", "können", "fähigkeit", "skill"],
    "weaknesses":    ["schwäche", "weakness", "verbessern", "improve", "schwierig"],
    "situational":   ["situation", "problem", "konflikt", "conflict", "lösung", "solution", "beispiel"],
    "teamwork":      ["team", "kollege", "zusammen", "together", "gruppe", "group"],
    "goals":         ["ziel", "goal", "zukunft", "future", "plan", "vorhaben"],
}


class MemoryManager:
    def __init__(self):
        self.turns:        list[dict] = []   # current session turns
        self.errors:       list[str]  = []   # persistent grammar/vocab errors
        self.weak_topics:  list[str]  = []   # persistent weak interview topics
        self.session_count: int       = 0
        self._load()

    # ── Persistence ───────────────────────────────────────────────────────────

    def _load(self):
        if not os.path.exists(MEMORY_FILE):
            return
        try:
            with open(MEMORY_FILE, "r", encoding="utf-8") as f:
                data = json.load(f)
            self.errors       = data.get("errors", [])
            self.weak_topics  = data.get("weak_topics", [])
            self.session_count = data.get("session_count", 0)
            print(f"   [Memory] Loaded — {len(self.errors)} error(s), "
                  f"{len(self.weak_topics)} weak topic(s), "
                  f"{self.session_count} session(s).")
        except Exception as e:
            print(f"   [Memory] Load failed: {e}")

    def _save(self):
        try:
            with open(MEMORY_FILE, "w", encoding="utf-8") as f:
                json.dump({
                    "errors":        self.errors[-30:],
                    "weak_topics":   self.weak_topics,
                    "session_count": self.session_count,
                    "updated":       datetime.now().isoformat(),
                }, f, ensure_ascii=False, indent=2)
        except Exception as e:
            print(f"   [Memory] Save failed: {e}")

    # ── Turn tracking ─────────────────────────────────────────────────────────

    def add_turn(self, user: str, assistant: str):
        self.turns.append({"user": user, "assistant": assistant})
        if len(self.turns) > 30:
            self.turns = self.turns[-30:]

    # ── Rule-based extraction (no LLM) ────────────────────────────────────────

    def extract_from_session(self):
        """
        Parse [KORREKTUR] blocks from assistant turns to extract:
        - German grammar/vocab errors
        - Weak interview topics
        No API calls. Called at session end.
        """
        new_errors  = []
        weak_topics = set(self.weak_topics)

        for turn in self.turns:
            assistant_text = turn.get("assistant", "")
            user_text      = turn.get("user", "")

            # Extract corrections from [KORREKTUR] blocks
            korrektur_match = re.search(
                r'\[KORREKTUR\](.*?)(?:\[FRAGE\]|$)',
                assistant_text,
                re.IGNORECASE | re.DOTALL
            )
            if korrektur_match:
                correction = korrektur_match.group(1).strip()
                if correction and len(correction) > 5:
                    # Deduplicate similar corrections
                    if not any(correction[:30] in e for e in self.errors):
                        new_errors.append(correction)

                # Detect which topic this question was about
                combined = (assistant_text + user_text).lower()
                for topic, keywords in TOPIC_KEYWORDS.items():
                    if any(kw in combined for kw in keywords):
                        weak_topics.add(topic)
                        break

        # Merge new findings
        if new_errors:
            self.errors.extend(new_errors)
            print(f"   [Memory] Extracted {len(new_errors)} new correction(s).")

        self.weak_topics  = list(weak_topics)
        self.session_count += 1
        self._save()

    # ── Context injection ─────────────────────────────────────────────────────

    def get_context(self, query: str = "") -> str:
        """
        Build a compact context string to inject into the system prompt.
        Keeps it tight — max ~200 tokens worth.
        """
        parts = []

        if self.weak_topics:
            topics = ", ".join(self.weak_topics)
            parts.append(f"Weak interview topics from past sessions: {topics}. Focus on these.")

        if self.errors:
            # Only show the 4 most recent distinct errors
            recent = self.errors[-4:]
            error_lines = "\n".join(f"  - {e}" for e in recent)
            parts.append(f"Recurring German errors to watch for:\n{error_lines}")

        return "\n".join(parts) if parts else ""

    # ── Session control ───────────────────────────────────────────────────────

    def clear_session(self):
        self.turns = []
        print("   [Memory] Session turns cleared.")

    def full_reset(self):
        """Wipe everything including persistent memory."""
        self.turns        = []
        self.errors       = []
        self.weak_topics  = []
        self.session_count = 0
        if os.path.exists(MEMORY_FILE):
            os.remove(MEMORY_FILE)
        print("   [Memory] Full reset — all memory wiped.")

    # ── Debug ─────────────────────────────────────────────────────────────────

    def summary(self) -> str:
        if not self.errors and not self.weak_topics:
            return "No memory yet — complete a session first."
        lines = [f"Sessions completed: {self.session_count}"]
        if self.weak_topics:
            lines.append(f"Weak topics: {', '.join(self.weak_topics)}")
        if self.errors:
            lines.append(f"Tracked errors ({len(self.errors)}):")
            for e in self.errors[-5:]:
                lines.append(f"  • {e}")
        return "\n".join(lines)