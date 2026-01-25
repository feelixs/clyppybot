FROM python:3.12-slim

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy bot code as a package
COPY . ./bot/

CMD ["python", "-m", "bot.main"]
