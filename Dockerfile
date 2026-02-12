FROM python:3.11-slim

WORKDIR /app

COPY . /app

RUN pip install --upgrade pip
RUN pip install -r requirements.txt
RUN pip install gunicorn

ENV PORT=10000

# تشغيل Flask باستخدام Gunicorn مع threads لدعم asyncio
CMD ["gunicorn", "-w", "1", "--threads", "8", "-b", "0.0.0.0:10000", "main:app"]