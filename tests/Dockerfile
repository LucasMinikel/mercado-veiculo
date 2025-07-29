FROM python:3.11-alpine
ENV PYTHONUNBUFFERED=1
WORKDIR /app
RUN apk add --no-cache curl
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY . .
CMD ["python", "-m", "pytest", "-v", "--tb=short"]