# استخدم Python 3.11
FROM python:3.11-slim

# إعداد مجلد العمل
WORKDIR /app

# نسخ الملفات
COPY . /app

# تثبيت المتطلبات
RUN pip install --no-cache-dir --upgrade pip \
    && pip install --no-cache-dir -r requirements.txt

# exposed port
EXPOSE 10000

# أمر التشغيل
CMD ["uvicorn", "main:api", "--host", "0.0.0.0", "--port", "10000"]