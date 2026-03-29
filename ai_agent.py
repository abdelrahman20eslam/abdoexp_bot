import os
import json
import re
import logging
from datetime import date
import google.generativeai as genai

logger = logging.getLogger(__name__)

GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY")

model = None
if GEMINI_API_KEY:
    try:
        genai.configure(api_key=GEMINI_API_KEY)
        model = genai.GenerativeModel("gemini-2.5-flash")
        logger.info("Gemini model initialized successfully.")
    except Exception as e:
        logger.error(f"Failed to initialize Gemini model: {e}")
else:
    logger.error("GEMINI_API_KEY is missing.")

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

CATEGORIES = ["أكل", "مواصلات", "تسوق", "فواتير", "ترفيه", "صحة", "تعليم"]


def fallback_parse(text: str, today: str) -> dict:
    text = text.strip()

    report_map = {
        "تقرير النهارده": ("day", "النهارده"),
        "تقرير اليوم": ("day", "النهارده"),
        "تقرير الاسبوع": ("week", "الأسبوع"),
        "تقرير الأسبوع": ("week", "الأسبوع"),
        "تقرير الشهر": ("month", "الشهر"),
    }

    normalized = re.sub(r"\s+", " ", text).strip()

    if normalized in report_map:
        period, label = report_map[normalized]
        return {"type": "report", "period": period, "period_label": label}

    amount_match = re.search(r'(\d+(?:\.\d+)?)', normalized)
    if amount_match:
        amount = float(amount_match.group(1))
        category = "أخرى"

        for cat in CATEGORIES:
            if cat in normalized:
                category = cat
                break

        expense_keywords = ["صرفت", "دفعت", "اشتريت", "حساب", "كلفني", "دفعه", "مصروف"]
        if any(word in normalized for word in expense_keywords):
            description = normalized
            for word in expense_keywords:
                description = description.replace(word, "").strip()
            description = re.sub(r'\b\d+(?:\.\d+)?\b', '', description).strip()
            description = description.replace("جنيه", "").strip()
            if not description:
                description = "مصروف"

            return {
                "type": "expense",
                "amount": amount,
                "category": category,
                "description": description,
                "date": today
            }

    return {"type": "unknown"}


async def analyze_message(text: str) -> dict:
    today = date.today().strftime("%Y-%m-%d")
    text = (text or "").strip()

    if not text:
        return {"type": "unknown"}

    if not model:
        logger.error("Gemini model is not available. Using fallback parser.")
        return fallback_parse(text, today)

    prompt = f"{SYSTEM_PROMPT}\n\nتاريخ اليوم: {today}\n\nرسالة المستخدم: {text}"

    try:
        response = model.generate_content(prompt)
        raw = (response.text or "").strip()
        logger.info(f"Gemini raw response: {raw}")

        raw = re.sub(r"```json|```", "", raw).strip()
        result = json.loads(raw)

        if not isinstance(result, dict) or "type" not in result:
            logger.error(f"Invalid Gemini JSON structure: {result}")
            return fallback_parse(text, today)

        if result["type"] == "expense":
            amount = result.get("amount")
            category = result.get("category", "أخرى")
            description = result.get("description", "مصروف")
            msg_date = result.get("date", today)

            try:
                amount = float(amount)
            except (TypeError, ValueError):
                logger.error(f"Invalid amount from Gemini: {amount}")
                return fallback_parse(text, today)

            if category not in CATEGORIES:
                category = "أخرى"

            return {
                "type": "expense",
                "amount": amount,
                "category": category,
                "description": description,
                "date": msg_date
            }

        if result["type"] == "report":
            period = result.get("period")
            period_label = result.get("period_label")

            if period not in ["day", "week", "month"]:
                logger.error(f"Invalid report period from Gemini: {period}")
                return fallback_parse(text, today)

            if not period_label:
                period_label = {
                    "day": "النهارده",
                    "week": "الأسبوع",
                    "month": "الشهر"
                }[period]

            return {
                "type": "report",
                "period": period,
                "period_label": period_label
            }

        return {"type": "unknown"}

    except json.JSONDecodeError as e:
        logger.error(f"JSON decode error: {e}")
        logger.error(f"Raw Gemini response was: {raw if 'raw' in locals() else 'NO RESPONSE'}")
        return fallback_parse(text, today)

    except Exception as e:
        logger.error(f"Gemini failed: {e}")
        return fallback_parse(text, today)
