# استخدم صورة Python
FROM python:3.10-slim

# إعداد مجلد العمل داخل الحاوية
WORKDIR /app

# نسخ الملفات إلى الحاوية
COPY . .

# تثبيت الاعتمادات
RUN pip install --no-cache-dir -r requirements.txt

# تشغيل البوت
CMD ["python", "main.py"]
