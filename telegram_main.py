import os
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup, InputFile
from telegram.ext import (
    ApplicationBuilder, CommandHandler, MessageHandler,
    CallbackQueryHandler, ContextTypes, filters
)

# ========== CONFIG ==========
BOT_TOKEN = "7843415712:AAGpETAivvPNFthHMqEusW8tqld1ge4c_v0"
ALLOWED_GROUP_ID = -4823776735  # Replace with your Telegram group ID
REQUIRED_CHANNEL_USERNAME = -1002602397881  # Replace with your channel username

# Simulated database of mods
MOD_FILES = {
    "car": ["car_mod_v1.zip", "car_mod_v2.zip"],
    "gun": ["ak47_mod.zip", "sniper_mod.zip"]
}

# ========== COMMANDS ==========
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("👋 Send me a mod name to get related files!")

# ========== MESSAGES ==========
async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = update.effective_chat.id
    user = update.effective_user

    # Only allow messages from the specific group
    if chat_id != ALLOWED_GROUP_ID:
        return

    mod_query = update.message.text.lower().strip()
    matching_files = MOD_FILES.get(mod_query)

    if not matching_files:
        await update.message.reply_text("❌ No files found for this mod.")
        return

    # Create buttons for each file
    buttons = [
        [InlineKeyboardButton(file_name, callback_data=f"{user.id}|{file_name}")]
        for file_name in matching_files
    ]
    reply_markup = InlineKeyboardMarkup(buttons)

    await update.message.reply_text(
        f"📁 Files for: {mod_query}", reply_markup=reply_markup
    )

# ========== INLINE BUTTON HANDLER ==========
async def handle_button(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    try:
        user_id, file_name = query.data.split("|")
        user_id = int(user_id)

        if query.from_user.id != user_id:
            await query.edit_message_text("❌ This button is not for you.")
            return

        # Check if user is a member of the required channel
        member = await context.bot.get_chat_member(REQUIRED_CHANNEL_USERNAME, user_id)
        if member.status in ("left", "kicked"):
            raise Exception("Not joined")

        file_path = f"mods/{file_name}"
        if not os.path.exists(file_path):
            await query.edit_message_text("⚠️ File not found on server.")
            return

        # Send file in DM
        await context.bot.send_document(
            chat_id=user_id,
            document=InputFile(file_path),
            caption=f"✅ Here is your file: {file_name}"
        )
        await query.edit_message_text("✅ File sent to your DM.")

    except Exception as e:
        await query.edit_message_text(f"❌ You must join {REQUIRED_CHANNEL_USERNAME} to get this file.")

# ========== MAIN ==========
if __name__ == "__main__":
    app = ApplicationBuilder().token(BOT_TOKEN).build()

    app.add_handler(CommandHandler("start", start))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))
    app.add_handler(CallbackQueryHandler(handle_button))

    print("✅ Bot started...")
    app.run_polling()
