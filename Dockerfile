# استخدم Python 3.11
FROM python:3.11-slim

# تعيين مجلد العمل
WORKDIR /app

# نسخ ملفات المشروع
COPY . /app

# تحديث pip وتثبيت المتطلبات
RUN pip install --upgrade pip
RUN pip install -r requirements.txt

# تعيين متغير البيئة للـ Port
ENV PORT=10000

# أمر التشغيل
CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "10000"]