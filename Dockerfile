FROM python:3.11-slim
WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY . .
CMD ["python", "bot.py"]
```

وعدّل `requirements.txt` لـ:
```
python-telegram-bot==21.3
google-generativeai==0.8.3
