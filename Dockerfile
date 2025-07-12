# اسم الصورة الأساسية
FROM python:3.10-slim

# تثبيت المتطلبات الأساسية
RUN apt-get update && apt-get install -y \
    ffmpeg \
    aria2 \
    && apt-get clean

# إعداد مجلد العمل
WORKDIR /app

# نسخ الملفات
COPY . .

# تثبيت باكجات المشروع
RUN pip install --no-cache-dir -r requirements.txt

# أمر التشغيل
CMD ["python", "main.py"]
