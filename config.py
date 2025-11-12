import os
from dotenv import load_dotenv

load_dotenv()

# Discord Bot Configuration
DISCORD_TOKEN = os.getenv('DISCORD_TOKEN')
COMMAND_PREFIX = os.getenv('COMMAND_PREFIX', '!')
BOT_OWNER_ID = int(os.getenv('BOT_OWNER_ID', 0))

# Logging Configuration
LOG_LEVEL = os.getenv('LOG_LEVEL', 'INFO')
LOG_FILE = 'bot.log'

# Features
ENABLE_MODERATION = True
ENABLE_ENTERTAINMENT = True
ENABLE_UTILITY = True

# API Keys (if needed for utility features)
WEATHER_API_KEY = os.getenv('WEATHER_API_KEY', '')
TRANSLATOR_API_KEY = os.getenv('TRANSLATOR_API_KEY', '')

# Database Configuration (optional)
DATABASE_URL = os.getenv('DATABASE_URL', '')

if not DISCORD_TOKEN:
    raise ValueError('DISCORD_TOKEN not found in environment variables')
