# استخدام Python الرسمي
FROM python:3.10-slim

# تثبيت المتطلبات الأساسية
RUN apt-get update && apt-get install -y \
    build-essential \
    curl \
    && apt-get clean \
    && rm -rf /var/lib/apt/lists/*

# تعيين مجلد العمل
WORKDIR /app

# نسخ الملفات إلى الحاوية
COPY . .

# تثبيت التبعيات
RUN pip install --no-cache-dir -r requirements.txt

# تعيين المتغيرات البيئية
ENV PYTHONUNBUFFERED=1

# تشغيل البوت
CMD ["python", "main.py"]
