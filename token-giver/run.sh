#!/bin/bash

# Token Giver Bot - Docker Run Script

# Colors for output
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
NC='\033[0m' # No Color

# Configuration
CONTAINER_NAME="token-giver-bot"
IMAGE_NAME="token-giver-bot"
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(dirname "$SCRIPT_DIR")"

echo -e "${GREEN}Token Giver Bot - Docker Runner${NC}"
echo "================================"

# Check if .env file exists
if [ ! -f "$SCRIPT_DIR/.env" ]; then
    echo -e "${RED}Error: .env file not found!${NC}"
    echo "Please create a .env file based on .env.example"
    exit 1
fi

# Stop and remove existing container if running
if [ "$(docker ps -q -f name=$CONTAINER_NAME)" ]; then
    echo -e "${YELLOW}Stopping existing container...${NC}"
    docker stop $CONTAINER_NAME
fi

if [ "$(docker ps -aq -f name=$CONTAINER_NAME)" ]; then
    echo -e "${YELLOW}Removing existing container...${NC}"
    docker rm $CONTAINER_NAME
fi

# Build the image
echo -e "${GREEN}Building Docker image...${NC}"
cd "$PROJECT_ROOT"
docker build -f token-giver/Dockerfile -t $IMAGE_NAME .

if [ $? -ne 0 ]; then
    echo -e "${RED}Build failed!${NC}"
    exit 1
fi

# Create data directory if it doesn't exist
mkdir -p "$SCRIPT_DIR/data"

# Run the container
echo -e "${GREEN}Starting container...${NC}"
docker run -d \
  --name $CONTAINER_NAME \
  --env-file "$SCRIPT_DIR/.env" \
  -v "$SCRIPT_DIR/data:/app/token-giver/data" \
  --restart unless-stopped \
  $IMAGE_NAME

if [ $? -eq 0 ]; then
    echo -e "${GREEN}Container started successfully!${NC}"
    echo ""
    echo "Useful commands:"
    echo "  View logs:    docker logs -f $CONTAINER_NAME"
    echo "  Stop bot:     docker stop $CONTAINER_NAME"
    echo "  Restart bot:  docker restart $CONTAINER_NAME"
    echo "  Remove bot:   docker rm -f $CONTAINER_NAME"
else
    echo -e "${RED}Failed to start container!${NC}"
    exit 1
fi
