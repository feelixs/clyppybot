#!/bin/bash
set -e

cd /home/ubuntu/insightbot

echo "Pulling latest changes..."
sudo git pull

echo "Rebuilding and restarting bot..."
cd bot
docker compose up -d --build

echo "Deployment complete!"
docker compose ps
