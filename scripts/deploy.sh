#!/bin/bash

# Discord Bot Deployment Script
# This script helps deploy the bot to Pterodactyl

set -e  # Exit on error

echo "🤖 Discord Bot Deployment Script"
echo "=================================="

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

# Check if we're in a git repository
if [ ! -d ".git" ]; then
    echo -e "${RED}❌ Error: Not in a git repository${NC}"
    exit 1
fi

# Step 1: Pull latest code
echo -e "${YELLOW}📥 Pulling latest code from GitHub...${NC}"
git fetch origin
git pull origin main
if [ $? -eq 0 ]; then
    echo -e "${GREEN}✅ Code pulled successfully${NC}"
else
    echo -e "${RED}❌ Failed to pull code${NC}"
    exit 1
fi

# Step 2: Install dependencies
echo -e "${YELLOW}📦 Installing Python dependencies...${NC}"
if [ -f "requirements.txt" ]; then
    pip install -r requirements.txt
    echo -e "${GREEN}✅ Dependencies installed${NC}"
else
    echo -e "${RED}❌ requirements.txt not found${NC}"
    exit 1
fi

# Step 3: Check environment
echo -e "${YELLOW}🔍 Checking environment...${NC}"
if [ -f ".env" ]; then
    echo -e "${GREEN}✅ .env file found${NC}"
else
    echo -e "${RED}❌ .env file not found. Please create it with DISCORD_TOKEN${NC}"
    exit 1
fi

# Step 4: Restart the bot
echo -e "${YELLOW}🔄 Restarting bot...${NC}"

# Check if bot.py is running and kill it
if pgrep -f "python.*bot.py" > /dev/null; then
    echo "Stopping existing bot process..."
    pkill -f "python.*bot.py"
    sleep 2
fi

# Start the bot
nohup python bot.py > bot.log 2>&1 &
BOT_PID=$!
echo -e "${GREEN}✅ Bot started with PID: $BOT_PID${NC}"

# Wait a moment and check if process is still running
sleep 3
if ps -p $BOT_PID > /dev/null; then
    echo -e "${GREEN}✅ Deployment completed successfully!${NC}"
    echo "📋 Bot logs available in: bot.log"
    tail -f bot.log
else
    echo -e "${RED}❌ Bot failed to start. Check logs for details.${NC}"
    cat bot.log
    exit 1
fi
