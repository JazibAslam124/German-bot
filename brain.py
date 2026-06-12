# brain.py - Interview brain via Groq with key rotation

import os
import re
from groq import AsyncGroq
from dotenv import load_dotenv
load_dotenv(override=True)

GROQ_KEYS = [
    k for k in [
        os.getenv("GROQ_API_KEY", ""),
        os.getenv("GROQ_API_KEY_2", ""),
        os.getenv("GROQ_API_KEY_3", ""),
    ] if k
]

if not GROQ_KEYS:
    print("   [Brain] ERROR: No GROQ_API_KEY set in .env")
else:
    print(f"   [Brain] {len(GROQ_KEYS)} Groq key(s) loaded.")

# Short reminder injected after turn 2 to save tokens.
# Keeps the interviewer on-rails without resending the full prompt.
SHORT_PROMPT = (
    "You are a professional German interview coach. "
    "Ask questions in German. "
    "Correct errors briefly in English under [KORREKTUR]. "
    "Next question under [FRAGE]. "
    "Neutral tone. No praise. No padding."
)


def _load_personality(filename: str = "personality.txt") -> str:
    path = os.path.join(os.path.dirname(os.path.abspath(__file__)), filename)
    try:
        with open(path, "r", encoding="utf-8") as f:
            content = f.read().strip()
            print(f"   [Brain] Personality loaded from {filename}")
            return content
    except FileNotFoundError:
        print(f"   [Brain] WARNING: {filename} not found.")
        return SHORT_PROMPT


class InterviewBrain:
    def __init__(self, personality_file: str = "personality.txt"):
        self.full_prompt   = _load_personality(personality_file)
        self.history       = []
        self.turn_count    = 0
        self._key_index    = 0
        self._clients      = [AsyncGroq(api_key=k) for k in GROQ_KEYS]
        self.ready         = bool(self._clients)

        if self.ready:
            print(f"   [Brain] Ready (llama-3.3-70b) — {len(self._clients)} key(s).")
        else:
            print("   [Brain] ERROR: No Groq clients.")

    # ── Key rotation ──────────────────────────────────────────────────────────

    def _client(self) -> AsyncGroq:
        return self._clients[self._key_index]

    def _rotate(self) -> bool:
        nxt = (self._key_index + 1) % len(self._clients)
        if nxt == self._key_index:
            return False
        self._key_index = nxt
        print(f"   [Brain] Rotated to key {self._key_index + 1}/{len(self._clients)}")
        return True

    # ── System prompt selection ───────────────────────────────────────────────

    def _system(self, memory_context: str = "") -> str:
        # Full prompt for first 2 turns so the model has full context.
        # Compressed reminder after that to save tokens.
        if self.turn_count <= 2:
            prompt = self.full_prompt
            if memory_context:
                prompt += f"\n\n[MEMORY]\n{memory_context[:400]}"
        else:
            prompt = SHORT_PROMPT
        return prompt

    # ── Main chat ─────────────────────────────────────────────────────────────

    async def chat(self, user_text: str, memory_context: str = "") -> str:
        if not self.ready:
            return "Brain not ready — check GROQ_API_KEY in .env"

        self.history.append({"role": "user", "content": user_text})
        if len(self.history) > 10:
            self.history = self.history[-10:]

        messages = [{"role": "system", "content": self._system(memory_context)}] + self.history

        for _ in range(len(self._clients)):
            try:
                response = await self._client().chat.completions.create(
                    model="llama-3.3-70b-versatile",
                    messages=messages,
                    max_tokens=200,
                    temperature=0.7,
                )
                result = response.choices[0].message.content.strip()
                self.history.append({"role": "assistant", "content": result})
                self.turn_count += 1
                return result

            except Exception as e:
                err = str(e)
                if "429" in err:
                    print(f"   [Brain] Key {self._key_index + 1} rate limited.")
                    if self._rotate():
                        continue
                    match = re.search(r'try again in (\d+)', err)
                    wait = match.group(1) if match else "60"
                    return f"Rate limited — try again in {wait}s."
                else:
                    print(f"   [Brain] Error: {e}")
                    return "Something went wrong. Try again."

        return "All API keys rate limited. Try again later."

    def reset(self):
        self.history    = []
        self.turn_count = 0
        print("   [Brain] Session reset.")