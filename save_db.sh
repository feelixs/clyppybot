#!/bin/bash

# Save database to server using the Clyppy API
# Usage: ./save_db.sh [path_to_db_file] [env]

# Get database file path (default: guild_settings.db in current directory)
DB_FILE="${1:-guild_settings.db}"

# Get environment (default: prod, can be 'test' or 'prod')
ENV="${2:-prod}"

# Check if .env file exists and load it
if [ -f ".env" ]; then
    export $(grep -v '^#' .env | xargs)
fi

# Check if API key is set
if [ -z "$clyppy_post_key" ]; then
    echo "Error: clyppy_post_key environment variable not set"
    echo "Please set it in .env file or export it before running this script"
    exit 1
fi

# Check if database file exists
if [ ! -f "$DB_FILE" ]; then
    echo "Error: Database file '$DB_FILE' not found"
    exit 1
fi

echo "Uploading database to server..."
echo "  File: $DB_FILE"
echo "  Environment: $ENV"

# Upload the database file
response=$(curl -s -w "\n%{http_code}" \
    -X POST \
    -H "X-API-Key: $clyppy_post_key" \
    -F "env=$ENV" \
    -F "file=@$DB_FILE" \
    https://felixcreations.com/api/products/clyppy/save_db/)

# Extract status code (last line) and body (everything else)
http_code=$(echo "$response" | tail -n1)
body=$(echo "$response" | sed '$d')

echo ""
echo "HTTP Status: $http_code"

if [ "$http_code" = "200" ]; then
    echo "✓ Database saved successfully!"
    if [ -n "$body" ]; then
        echo "Response: $body"
    fi
    exit 0
else
    echo "✗ Failed to save database"
    if [ -n "$body" ]; then
        echo "Error: $body"
    fi
    exit 1
fi
