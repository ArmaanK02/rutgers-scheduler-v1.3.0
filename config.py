import os
from dotenv import load_dotenv

load_dotenv()

class Config:
    DEBUG = os.getenv('FLASK_DEBUG', 'True') == 'True'
    SECRET_KEY = os.getenv('SECRET_KEY', 'dev-secret-key-change-in-prod')
    # Use provided API key, fallback to env if needed
    GEMINI_API_KEYS = [
        key.strip() for key in os.getenv('GEMINI_API_KEY', 'AIzaSyBuiHjB2k4F3bUcgMqvo5f2yFnE6pBfYjg').split(',') if key.strip()
    ]
    DATA_FILE_PATH = os.getenv('DATA_FILE_PATH', 'rutgers_scheduler_data.json')
    MAX_SCHEDULES = int(os.getenv('MAX_SCHEDULES', '50'))

def get_config():
    return Config

def validate_config():
    issues = []
    if not Config.GEMINI_API_KEYS:
        issues.append("Missing GEMINI_API_KEY in .env file")
    return issues