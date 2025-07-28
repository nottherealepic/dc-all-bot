# telegram_main.py

import os
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup, InputFile
from telegram.ext import (
    ApplicationBuilder, CommandHandler, MessageHandler,
    CallbackQueryHandler, ContextTypes, filters
)
from dotenv import load_dotenv

# Load environment variables if using .env
load_dotenv()
BOT_TOKEN = os.getenv("BOT_TOKEN") or "7843415712:AAGpETAivvPNFthHMqEusW8tqld1ge4c_v0"
ALLOWED_GROUP_ID = -4823776735
REQUIRED_CHANNEL_USERNAME = -1002602397881  # should be channel ID, not @username

MOD_FILES = {
    "car": ["car_mod_v1.zip", "car_mod_v2.zip"],
    "gun": ["ak47_mod.zip", "sniper_mod.zip"]
}

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("👋 Send me a mod name to get related files!")

async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_chat.id != ALLOWED_GROUP_ID:
        return

    query = update.message.text.lower().strip()
    files = MOD_FILES.get(query)

    if not files:
        await update.message.reply_text("❌ No files found for this mod.")
        return

    buttons = [[InlineKeyboardButton(f, callback_data=f"{update.effective_user.id}|{f}")]
               for f in files]
    await update.message.reply_text(
        f"📁 Files for: {query}",
        reply_markup=InlineKeyboardMarkup(buttons)
    )

async def handle_button(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    try:
        user_id, file_name = query.data.split("|")
        user_id = int(user_id)

        if query.from_user.id != user_id:
            await query.edit_message_text("❌ This button is not for you.")
            return

        member = await context.bot.get_chat_member(REQUIRED_CHANNEL_USERNAME, user_id)
        if member.status in ("left", "kicked"):
            raise Exception("User not in channel")

        file_path = f"mods/{file_name}"
        if not os.path.exists(file_path):
            await query.edit_message_text("⚠️ File not found on server.")
            return

        await context.bot.send_document(
            chat_id=user_id,
            document=InputFile(file_path),
            caption=f"✅ Here is your file: {file_name}"
        )
        await query.edit_message_text("✅ File sent to your DM.")
    except Exception:
        await query.edit_message_text(
            f"❌ You must join the required channel to get this file."
        )

def main():
    app = ApplicationBuilder().token(BOT_TOKEN).build()

    app.add_handler(CommandHandler("start", start))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))
    app.add_handler(CallbackQueryHandler(handle_button))

    print("✅ Telegram bot is running...")
    app.run_polling()

if __name__ == "__main__":
    main()
