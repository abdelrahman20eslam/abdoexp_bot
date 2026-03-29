import os
import logging
from telegram import Update
from telegram.ext import Application, MessageHandler, CommandHandler, filters, ContextTypes
from database import init_db, save_expense, get_report
from ai_agent import analyze_message

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

TELEGRAM_TOKEN = os.environ.get("TELEGRAM_TOKEN")
ALLOWED_USER_ID = int(os.environ.get("ALLOWED_USER_ID", "0"))


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "👋 أهلاً! أنا وكيل المصاريف بتاعك.\n\n"
        "ابعتلي أي مصروف مثلاً:\n"
        "• صرفت 150 جنيه أكل\n"
        "• دفعت 500 مواصلات\n"
        "• اشتريت كتاب بـ 200\n\n"
        "أو اطلب تقرير:\n"
        "• تقرير النهارده\n"
        "• تقرير الأسبوع\n"
        "• تقرير الشهر"
    )


async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id

    if ALLOWED_USER_ID != 0 and user_id != ALLOWED_USER_ID:
        await update.message.reply_text("⛔ مش مصرح ليك تستخدم البوت ده.")
        return

    user_text = update.message.text
    logger.info(f"Message from {user_id}: {user_text}")

    await update.message.reply_text("⏳ بفكر...")

    result = await analyze_message(user_text)

    if result["type"] == "expense":
        save_expense(
            user_id=user_id,
            amount=result["amount"],
            category=result["category"],
            description=result["description"],
            date=result["date"]
        )
        await update.message.reply_text(
            f"✅ تم التسجيل!\n\n"
            f"💰 المبلغ: {result['amount']} جنيه\n"
            f"📂 الفئة: {result['category']}\n"
            f"📝 الوصف: {result['description']}\n"
            f"📅 التاريخ: {result['date']}"
        )

    elif result["type"] == "report":
        report_data = get_report(user_id, result["period"])
        if not report_data:
            await update.message.reply_text("📭 مفيش مصاريف مسجلة في الفترة دي.")
            return

        report_text = f"📊 تقرير {result['period_label']}\n\n"
        total = 0
        categories = {}

        for row in report_data:
            cat = row["category"]
            amt = row["amount"]
            total += amt
            categories[cat] = categories.get(cat, 0) + amt

        for cat, amt in sorted(categories.items(), key=lambda x: -x[1]):
            report_text += f"• {cat}: {amt:.0f} جنيه\n"

        report_text += f"\n💵 الإجمالي: {total:.0f} جنيه"
        await update.message.reply_text(report_text)

    elif result["type"] == "unknown":
        await update.message.reply_text(
            "🤔 مش فاهم قصدك.\n\nجرب تقول:\n• صرفت 200 جنيه أكل\n• تقرير الشهر"
        )


def main():
    init_db()
    app = Application.builder().token(TELEGRAM_TOKEN).build()
    app.add_handler(CommandHandler("start", start))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))
    logger.info("Bot is running...")
    app.run_polling()


if __name__ == "__main__":
    main()
