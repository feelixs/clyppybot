# Use Python 3.12 slim image
FROM python:3.12-slim

# Set working directory
WORKDIR /app

# Copy bot directory for imports
COPY bot/ /app/bot/

# Copy token-giver files
COPY token-giver/main.py /app/token-giver/main.py

# Install dependencies
RUN pip install --no-cache-dir discord-py-interactions dotenv

# Create directory for database
RUN mkdir -p /app/token-giver/data

# Set environment variable for database path (optional, for volume mounting)
ENV DB_PATH=/app/token-giver/data/members.db

# Run the bot
CMD ["python", "/app/token-giver/main.py"]
