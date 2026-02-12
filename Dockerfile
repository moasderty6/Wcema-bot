FROM python:3.11-slim

WORKDIR /app

# تثبيت الأدوات اللازمة لـ asyncpg
RUN apt-get update && apt-get install -y gcc libpq-dev && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

# تشغيل البوت مباشرة
CMD ["python", "main.py"]
