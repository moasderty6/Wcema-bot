# استخدام Python الرسمي
FROM python:3.10-slim

# تثبيت المتطلبات الأساسية بالإضافة إلى ffmpeg
RUN apt-get update && apt-get install -y \
    build-essential \
    curl \
    ffmpeg \ # <--- الإضافة الأساسية هنا
    && apt-get clean \
    && rm -rf /var/lib/apt/lists/*

# تعيين مجلد العمل
WORKDIR /app

# نسخ الملفات إلى الحاوية
# الأفضل نسخ ملف المتطلبات أولاً للاستفادة من التخزين المؤقت (caching)
COPY requirements.txt .

# تثبيت التبعيات
RUN pip install --no-cache-dir -r requirements.txt

# نسخ باقي ملفات المشروع
COPY . .

# تعيين المتغيرات البيئية
ENV PYTHONUNBUFFERED=1

# تشغيل البوت (تأكد من أن اسم الملف صحيح)
CMD ["python", "main.py"]
