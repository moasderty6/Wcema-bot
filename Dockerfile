FROM python:3.9-slim
WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY . .
# تفعيل البورت لـ Render
EXPOSE 10000
CMD ["python", "main.py"]
