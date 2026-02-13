# استخدام نسخة بايثون خفيفة
FROM python:3.10-slim

# تحديد مجلد العمل داخل الحاوية
WORKDIR /app

# نسخ ملف المكتبات أولاً لتسريع عملية البناء (Caching)
COPY requirements.txt .

# تثبيت المكتبات المطلوبة
RUN pip install --no-cache-dir -r requirements.txt

# نسخ ملف الكود وبقية الملفات
COPY . .

# إخبار دوكر بأن التطبيق سيعمل على بورت 10000 (الافتراضي لريندر)
EXPOSE 10000

# أمر التشغيل
CMD ["python", "main.py"]
