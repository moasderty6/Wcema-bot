FROM python:3.11-slim
WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY . .
# تفعيل البورت لـ Render
EXPOSE 8080
CMD ["python", "main.py"]
