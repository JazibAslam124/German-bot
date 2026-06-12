# bot.py - German Interview Practice Bot

import os
import io
from dotenv import load_dotenv
load_dotenv(override=True)

from telegram import Update
from telegram.ext import Application, MessageHandler, CommandHandler, filters, ContextTypes

from brain import InterviewBrain
from memory import MemoryManager
import tts
import stt

TELEGRAM_TOKEN  = os.getenv("TELEGRAM_BOT_TOKEN", "")
ALLOWED_USER_ID = int(os.getenv("TELEGRAM_USER_ID", "0"))


class InterviewBot:
    def __init__(self):
        self.brain      = InterviewBrain(personality_file="personality.txt")
        self.memory     = MemoryManager()
        self.turn_count = 0
        self.in_session = False
        print("   [Bot] Interview bot ready.")

    # ── Auth ──────────────────────────────────────────────────────────────────

    def _allowed(self, update: Update) -> bool:
        if ALLOWED_USER_ID and update.effective_user.id != ALLOWED_USER_ID:
            return False
        return True

    # ── Commands ──────────────────────────────────────────────────────────────

    async def cmd_start(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        if not self._allowed(update):
            return
        await update.message.reply_text(
            "German interview practice bot.\n\n"
            "/interview — start a mock interview session\n"
            "/memory    — show what I remember about your German\n"
            "/reset     — reset current session\n"
            "/wipe      — wipe ALL memory and start fresh\n"
            "/help      — show this message"
        )

    async def cmd_interview(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        if not self._allowed(update):
            return

        # Save previous session before starting new one
        if self.in_session and self.turn_count > 0:
            self.memory.extract_from_session()
            await update.message.reply_text("Previous session saved.")

        self.brain.reset()
        self.memory.clear_session()
        self.turn_count = 0
        self.in_session = True

        await update.message.reply_text("Starting interview session…")

        # Inject persistent memory into opening context
        memory_context = self.memory.get_context()
        opener_prompt  = "Begin the interview. Introduce yourself briefly as the interviewer in one sentence, then ask the first question in German."
        if memory_context:
            opener_prompt += f"\n\nContext from previous sessions:\n{memory_context}"

        opener = await self.brain.chat(opener_prompt)
        await self._send_response(update, opener)

    async def cmd_end(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """End session, extract memory, show summary."""
        if not self._allowed(update):
            return
        if not self.in_session or self.turn_count == 0:
            await update.message.reply_text("No active session to end.")
            return

        await update.message.reply_text("Ending session and saving memory…")
        self.memory.extract_from_session()
        self.in_session = False

        summary = self.memory.summary()
        await update.message.reply_text(f"Session saved.\n\n{summary}")

    async def cmd_memory(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        if not self._allowed(update):
            return
        await update.message.reply_text(self.memory.summary())

    async def cmd_reset(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        if not self._allowed(update):
            return
        # Save session before resetting
        if self.in_session and self.turn_count > 0:
            self.memory.extract_from_session()
        self.brain.reset()
        self.memory.clear_session()
        self.turn_count = 0
        self.in_session = False
        await update.message.reply_text("Session reset. Memory from this session was saved.\nSend /interview to start again.")

    async def cmd_wipe(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Nuclear option — wipe all persistent memory."""
        if not self._allowed(update):
            return
        self.brain.reset()
        self.memory.full_reset()
        self.turn_count = 0
        self.in_session = False
        await update.message.reply_text("All memory wiped. Fresh start.")

    async def cmd_help(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        if not self._allowed(update):
            return
        await update.message.reply_text(
            "/interview — start a new mock interview\n"
            "/end       — end session and save memory\n"
            "/memory    — show tracked errors and weak topics\n"
            "/reset     — reset session (saves memory first)\n"
            "/wipe      — wipe ALL memory\n"
            "/help      — show this message\n\n"
            "Reply by text or voice. Speak German — even imperfect German.\n"
            "Corrections appear under [KORREKTUR], next question under [FRAGE]."
        )

    # ── Message handlers ──────────────────────────────────────────────────────

    async def on_text(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        if not self._allowed(update):
            return
        user_text = update.message.text.strip()
        if not user_text:
            return
        if not self.in_session:
            await update.message.reply_text("Send /interview to start a session first.")
            return
        await self._process(update, user_text)

    async def on_voice(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        if not self._allowed(update):
            return
        if not self.in_session:
            await update.message.reply_text("Send /interview to start a session first.")
            return

        voice_file  = await update.message.voice.get_file()
        audio_bytes = bytes(await voice_file.download_as_bytearray())

        await update.message.reply_text("🎙 Transcribing…")

        user_text = await stt.transcribe(audio_bytes, hint_language="de")
        if not user_text:
            await update.message.reply_text("Couldn't understand the audio. Please try again.")
            return

        await update.message.reply_text(f"You said: {user_text}")
        await self._process(update, user_text)

    # ── Core logic ────────────────────────────────────────────────────────────

    async def _process(self, update: Update, user_text: str):
        memory_context = self.memory.get_context()
        response = await self.brain.chat(user_text, memory_context=memory_context)

        self.memory.add_turn(user_text, response)
        self.turn_count += 1

        await self._send_response(update, response)

    async def _send_response(self, update: Update, response: str):
        """Send text reply + German TTS audio for the [FRAGE] part only."""
        await update.message.reply_text(response)

        audio = await tts.synthesize(response)
        if audio:
            voice_io      = io.BytesIO(audio)
            voice_io.name = "question.mp3"
            await update.message.reply_voice(voice=voice_io)


# ── Entry point ───────────────────────────────────────────────────────────────

def main():
    if not TELEGRAM_TOKEN:
        print("❌ TELEGRAM_BOT_TOKEN not set in .env")
        return

    print("\n=== German Interview Bot ===\n")

    bot = InterviewBot()
    app = Application.builder().token(TELEGRAM_TOKEN).build()

    app.add_handler(CommandHandler("start",     bot.cmd_start))
    app.add_handler(CommandHandler("interview", bot.cmd_interview))
    app.add_handler(CommandHandler("end",       bot.cmd_end))
    app.add_handler(CommandHandler("memory",    bot.cmd_memory))
    app.add_handler(CommandHandler("reset",     bot.cmd_reset))
    app.add_handler(CommandHandler("wipe",      bot.cmd_wipe))
    app.add_handler(CommandHandler("help",      bot.cmd_help))
    app.add_handler(MessageHandler(filters.TEXT  & ~filters.COMMAND, bot.on_text))
    app.add_handler(MessageHandler(filters.VOICE, bot.on_voice))

    print("✅ Bot is online. Ctrl+C to stop.\n")
    app.run_polling(drop_pending_updates=True)


if __name__ == "__main__":
    main()