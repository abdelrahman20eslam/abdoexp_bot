import os
import json
import re
from datetime import date
import google.generativeai as genai

GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY")
genai.configure(api_key=GEMINI_API_KEY)
model = genai.GenerativeModel("gemini-1.5-flash")

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

رد فقط بـ JSON صحيح بدون أي نص إضافي، مثال:
{"type": "expense", "amount": 150, "category": "أكل", "description": "غداء", "date": "2024-01-15"}
{"type": "report", "period": "month", "period_label": "الشهر"}
{"type": "unknown"}
"""


async def analyze_message(text: str) -> dict:
    today = date.today().strftime("%Y-%m-%d")
    prompt = f"{SYSTEM_PROMPT}\n\nتاريخ اليوم: {today}\n\nرسالة المستخدم: {text}"

    try:
        response = model.generate_content(prompt)
        raw = response.text.strip()

        # تنظيف الرد من أي markdown
        raw = re.sub(r"```json|```", "", raw).strip()

        result = json.loads(raw)
        return result

    except json.JSONDecodeError:
        return {"type": "unknown"}
    except Exception as e:
        return {"type": "unknown"}
