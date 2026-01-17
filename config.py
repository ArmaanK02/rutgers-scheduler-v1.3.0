import os
try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass

class Config:
    DEBUG = os.getenv('FLASK_DEBUG', 'True') == 'True'
    SECRET_KEY = os.getenv('SECRET_KEY', 'dev-secret-key-change-in-prod')
    
    # SECURITY UPDATE: Keys must be loaded from environment variables for safety.
    GEMINI_API_KEYS = [
        key.strip() for key in os.getenv('GEMINI_API_KEY', '').split(',') if key.strip()
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