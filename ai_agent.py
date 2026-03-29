import os
import json
import re
import logging
from datetime import date
import google.generativeai as genai

logger = logging.getLogger(__name__)

GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY")

if GEMINI_API_KEY:
    genai.configure(api_key=GEMINI_API_KEY)
    model = genai.GenerativeModel("gemini-1.5-flash")
else:
    model = None

SYSTEM_PROMPT = """أنت مساعد ذكي لتسجيل المصاريف الشخصية.

مهمتك: تحليل رسالة المستخدم وتحديد نوعها.

النوع 1 - تسجيل مصروف:
إذا كان المستخدم يخبرك بمصروف، استخرج:
- amount: المبلغ رقم فقط
- category: فئة من (أكل، مواصلات، تسوق، فواتير، ترفيه، صحة، تعليم، أخرى)
- description: وصف قصير
- date: تاريخ اليوم بصيغة YYYY-MM-DD

النوع 2 - طلب تقرير:
إذا طلب تقريراً، حدد الفترة:
- period: "day" أو "week" أو "month"
- period_label: "النهارده" أو "الأسبوع" أو "الشهر"

النوع 3 - غير معروف:
إذا لم تفهم الرسالة.

رد فقط بـ JSON صحيح بدون أي نص إضافي.
"""

def fallback_parse(text: str, today: str) -> dict:
    text = text.strip()

    report_map = {
        "تقرير النهارده": ("day", "النهارده"),
        "تقرير اليوم": ("day", "النهارده"),
        "تقرير الأسبوع": ("week", "الأسبوع"),
        "تقرير الاسبوع": ("week", "الأسبوع"),
        "تقرير الشهر": ("month", "الشهر"),
    }

    if text in report_map:
        period, label = report_map[text]
        return {"type": "report", "period": period, "period_label": label}

    categories = ["أكل", "مواصلات", "تسوق", "فواتير", "ترفيه", "صحة", "تعليم"]
    amount_match = re.search(r'(\d+)', text)

    if amount_match:
        amount = int(amount_match.group(1))
        category = "أخرى"
        for cat in categories:
            if cat in text:
                category = cat
                break

        if any(word in text for word in ["صرفت", "دفعت", "اشتريت", "حساب", "كلفني"]):
            return {
                "type": "expense",
                "amount": amount,
                "category": category,
                "description": text,
                "date": today
            }

    return {"type": "unknown"}


async def analyze_message(text: str) -> dict:
    today = date.today().strftime("%Y-%m-%d")

    if not model:
        logger.error("GEMINI_API_KEY is missing")
        return fallback_parse(text, today)

    prompt = f"{SYSTEM_PROMPT}\n\nتاريخ اليوم: {today}\n\nرسالة المستخدم: {text}"

    try:
        response = model.generate_content(prompt)
        raw = response.text.strip()
        logger.info(f"Gemini raw response: {raw}")

        raw = re.sub(r"```json|```", "", raw).strip()
        result = json.loads(raw)
        return result

    except Exception as e:
        logger.error(f"Gemini failed: {e}")
        return fallback_parse(text, today)
