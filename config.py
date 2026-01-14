import os

# Load .env file if it exists
try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass  # python-dotenv not installed, rely on system env vars

class Config:
    """
    Centralized configuration management.
    All sensitive values are loaded from environment variables.
    """
    # File Paths
    BASE_DIR = os.path.dirname(os.path.abspath(__file__))
    DATA_FILE_PATH = os.path.join(BASE_DIR, 'rutgers_scheduler_data.json')
    MAJOR_REQUIREMENTS_PATH = os.path.join(BASE_DIR, 'major_requirements.json')
    
    # Scheduling Parameters
    MAX_SCHEDULES = 50
    SEMESTER_CODE = os.environ.get("SEMESTER_CODE", "92025")  # Fall 2025
    CAMPUS_CODE = os.environ.get("CAMPUS_CODE", "NB")  # New Brunswick
    LEVEL_CODE = os.environ.get("LEVEL_CODE", "U,G")  # Undergrad + Grad

    # AI Configuration - API keys loaded from environment
    # Users should set GEMINI_API_KEY or GEMINI_API_KEY_1, GEMINI_API_KEY_2, etc.
    @classmethod
    def get_api_keys(cls):
        """Get API keys from environment variables (deduplicated)."""
        keys = []
        seen = set()
        
        def add_key(key):
            if key and key not in seen:
                keys.append(key)
                seen.add(key)
        
        # Check for single key first
        add_key(os.environ.get("GEMINI_API_KEY"))
        
        # Check for numbered keys (for fallback support)
        for i in range(1, 10):
            add_key(os.environ.get(f"GEMINI_API_KEY_{i}"))
        
        return keys if keys else None
    
    GEMINI_API_KEYS = None  # Will be populated at runtime
    
    # Session Configuration
    SECRET_KEY = os.environ.get("SECRET_KEY", "dev_key_change_in_production")
    
    # Logging
    LOG_LEVEL = os.environ.get("LOG_LEVEL", "INFO")

class DevelopmentConfig(Config):
    DEBUG = True
    LOG_LEVEL = "DEBUG"

class ProductionConfig(Config):
    DEBUG = False
    LOG_LEVEL = "WARNING"

class TestConfig(Config):
    DEBUG = True
    TESTING = True
    # Use mock data for testing
    DATA_FILE_PATH = os.path.join(Config.BASE_DIR, 'test_data', 'mock_courses.json')

def get_config():
    """Get configuration based on environment."""
    env = os.environ.get('FLASK_ENV', 'development')
    
    config_map = {
        'production': ProductionConfig,
        'development': DevelopmentConfig,
        'testing': TestConfig
    }
    
    config = config_map.get(env, DevelopmentConfig)
    
    # Load API keys at runtime
    config.GEMINI_API_KEYS = config.get_api_keys()
    
    return config


def validate_config():
    """Validate that required configuration is present."""
    config = get_config()
    issues = []
    
    if not config.GEMINI_API_KEYS:
        issues.append("No Gemini API keys found. Set GEMINI_API_KEY environment variable.")
    
    if config.SECRET_KEY == "dev_key_change_in_production" and os.environ.get('FLASK_ENV') == 'production':
        issues.append("Using default SECRET_KEY in production. Set SECRET_KEY environment variable.")
    
    return issues
