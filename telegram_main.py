import os
from telegram import (
    Update, InlineKeyboardButton, InlineKeyboardMarkup, InputFile
)
from telegram.ext import (
    Updater, CommandHandler, MessageHandler,
    Filters, CallbackQueryHandler, CallbackContext
)
from dotenv import load_dotenv

# Load token
load_dotenv()
BOT_TOKEN = os.getenv("TELE_MAIN")
ALLOWED_GROUP_ID = -4823776735
REQUIRED_CHANNEL_ID = -1002602397881

MOD_FILES = {
    "car": ["car_mod_v1.zip", "car_mod_v2.zip"],
    "gun": ["ak47_mod.zip", "sniper_mod.zip"]
}

def start(update: Update, context: CallbackContext):
    update.message.reply_text("👋 Send me a mod name to get related files!")

def handle_message(update: Update, context: CallbackContext):
    if update.effective_chat.id != ALLOWED_GROUP_ID:
        return

    query = update.message.text.lower().strip()
    files = MOD_FILES.get(query)

    if not files:
        update.message.reply_text("❌ No files found for this mod.")
        return

    buttons = [[InlineKeyboardButton(f, callback_data=f"{update.effective_user.id}|{f}")]
               for f in files]

    update.message.reply_text(
        f"📁 Files for: {query}",
        reply_markup=InlineKeyboardMarkup(buttons)
    )

def handle_button(update: Update, context: CallbackContext):
    query = update.callback_query
    query.answer()

    try:
        user_id, file_name = query.data.split("|")
        user_id = int(user_id)

        if query.from_user.id != user_id:
            query.edit_message_text("❌ This button is not for you.")
            return

        member = context.bot.get_chat_member(REQUIRED_CHANNEL_ID, user_id)
        if member.status in ["left", "kicked"]:
            raise Exception("User not in channel")

        file_path = f"mods/{file_name}"
        if not os.path.exists(file_path):
            query.edit_message_text("⚠️ File not found on server.")
            return

        context.bot.send_document(
            chat_id=user_id,
            document=open(file_path, "rb"),
            filename=file_name,
            caption=f"✅ Here is your file: {file_name}"
        )
        query.edit_message_text("✅ File sent to your DM.")
    except Exception:
        query.edit_message_text("❌ You must join the required channel to get this file.")

def main():
    updater = Updater(BOT_TOKEN, use_context=True)
    dp = updater.dispatcher

    dp.add_handler(CommandHandler("start", start))
    dp.add_handler(MessageHandler(Filters.text & ~Filters.command, handle_message))
    dp.add_handler(CallbackQueryHandler(handle_button))

    print("✅ Telegram bot running (v13.15)...")
    updater.start_polling()
    updater.idle()

if __name__ == '__main__':
    main()
