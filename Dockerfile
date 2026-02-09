# استخدام نسخة بايثون خفيفة
FROM python:3.10-slim

# ضبط مجلد العمل
WORKDIR /app

# نسخ الملفات
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

# تشغيل البوت
CMD ["python", "main.py"]
