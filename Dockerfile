# استخدم Python الرسمي
FROM python:3.10-slim

# تثبيت المتطلبات الأساسية
RUN apt-get update && apt-get install -y \
    build-essential \
    curl \
    ffmpeg \
    && apt-get clean \
    && rm -rf /var/lib/apt/lists/*

# مجلد العمل
WORKDIR /app

# نسخ وتثبيت التبعيات
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# نسخ باقي ملفات المشروع
COPY . .

# متغيرات البيئة
ENV PYTHONUNBUFFERED=1

# تشغيل البوت باستخدام Webhook
CMD ["python", "main.py"]
