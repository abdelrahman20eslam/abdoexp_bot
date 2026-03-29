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
استخدم القيم التالية فقط في type:
- expense
- report
- unknown
ولا تستخدم أي ترجمة عربية في type.
"""

CATEGORIES = ["أكل", "مواصلات", "تسوق", "فواتير", "ترفيه", "صحة", "تعليم"]


def normalize_text(text: str) -> str:
    text = (text or "").strip()
    text = re.sub(r"\s+", " ", text)
    return text


def normalize_type(value: str) -> str:
    if not value:
        return "unknown"

    value = str(value).strip().lower()

    type_map = {
        "expense": "expense",
        "report": "report",
        "unknown": "unknown",
        "تسجيل مصروف": "expense",
        "مصروف": "expense",
        "expense تسجيل": "expense",
        "تقرير": "report",
        "طلب تقرير": "report",
        "غير معروف": "unknown",
        "unknown type": "unknown",
    }

    return type_map.get(value, "unknown")


def extract_category(text: str) -> str:
    for cat in CATEGORIES:
        if cat in text:
            return cat
    return "أخرى"


def fallback_parse(text: str, today: str) -> dict:
    text = normalize_text(text)

    report_map = {
        "تقرير النهارده": ("day", "النهارده"),
        "تقرير اليوم": ("day", "النهارده"),
        "تقرير الاسبوع": ("week", "الأسبوع"),
        "تقرير الأسبوع": ("week", "الأسبوع"),
        "تقرير الشهر": ("month", "الشهر"),
        "النهارده تقرير": ("day", "النهارده"),
        "الاسبوع تقرير": ("week", "الأسبوع"),
        "الأسبوع تقرير": ("week", "الأسبوع"),
        "الشهر تقرير": ("month", "الشهر"),
    }

    if text in report_map:
        period, label = report_map[text]
        return {"type": "report", "period": period, "period_label": label}

    amount_match = re.search(r'(\d+(?:\.\d+)?)', text)
    if amount_match:
        amount = float(amount_match.group(1))
        category = extract_category(text)

        expense_keywords = [
            "صرفت", "دفعت", "اشتريت", "كلفني", "حساب", "مصروف", "دفعه", "دفعتهم"
        ]

        if any(word in text for word in expense_keywords):
            description = text
            for word in expense_keywords:
                description = description.replace(word, " ")
            description = re.sub(r'\b\d+(?:\.\d+)?\b', ' ', description)
            description = description.replace("جنيه", " ")
            description = re.sub(r"\s+", " ", description).strip()

            if not description:
                description = category if category != "أخرى" else "مصروف"

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
    text = normalize_text(text)

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

        if not isinstance(result, dict):
            logger.error(f"Gemini returned non-dict JSON: {result}")
            return fallback_parse(text, today)

        result_type = normalize_type(result.get("type"))
        result["type"] = result_type

        if result_type == "expense":
            amount = result.get("amount")
            category = result.get("category", "أخرى")
            description = result.get("description", "")
            msg_date = result.get("date", today)

            try:
                amount = float(amount)
            except (TypeError, ValueError):
                logger.error(f"Invalid amount from Gemini: {amount}")
                return fallback_parse(text, today)

            if category not in CATEGORIES:
                category = extract_category(text)

            if not description or not str(description).strip():
                description = category if category != "أخرى" else "مصروف"

            return {
                "type": "expense",
                "amount": amount,
                "category": category,
                "description": str(description).strip(),
                "date": msg_date or today
            }

        if result_type == "report":
            period = str(result.get("period", "")).strip().lower()
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

        return fallback_parse(text, today)

    except json.JSONDecodeError as e:
        logger.error(f"JSON decode error: {e}")
        logger.error(f"Raw Gemini response was: {raw if 'raw' in locals() else 'NO RESPONSE'}")
        return fallback_parse(text, today)

    except Exception as e:
        logger.error(f"Gemini failed: {e}")
        return fallback_parse(text, today)
