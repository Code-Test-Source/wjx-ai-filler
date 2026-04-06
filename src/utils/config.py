"""
Configuration management for WJX AI Survey Filler
Supports environment variables and .env file
"""

import os
import json
from pathlib import Path

# Get project root - handle both package and script execution
try:
    PROJECT_ROOT = Path(__file__).parent.parent.parent
except NameError:
    PROJECT_ROOT = Path.cwd()

class Config:
    """Configuration class for the application"""

    # Project root path
    PROJECT_ROOT = Path(__file__).parent.parent.parent

    def __init__(self):
        # Load .env file first if exists
        self.load_env_file()

        # Then override with environment variables
        # OpenAI-compatible API (works with DeepSeek, OpenAI, etc.)
        self.API_URL = os.getenv('API_URL', '')
        self.API_KEY = os.getenv('API_KEY', '')
        self.API_MODEL = os.getenv('API_MODEL', 'deepseek-chat')
        # WJX Activity URL - REQUIRED, no default
        self.WJX_ACTIVITY_URL = os.getenv('WJX_ACTIVITY_URL', '')
        self.CHROMEDRIVER_PATH = os.getenv('CHROMEDRIVER_PATH', str(PROJECT_ROOT / 'chromedriver.exe'))
        self.MIN_DELAY = float(os.getenv('MIN_DELAY', '1.5'))
        self.MAX_DELAY = float(os.getenv('MAX_DELAY', '3.0'))
        self.COOKIES_FILE = os.getenv('COOKIES_FILE', str(PROJECT_ROOT / 'cookies.json'))
        self.SURVEY_LINKS_FILE = os.getenv('SURVEY_LINKS_FILE', str(PROJECT_ROOT / 'survey_links.txt'))

        # Load JSON config if exists
        self.load_json_config()

    def load_env_file(self):
        """Load .env file"""
        env_file = PROJECT_ROOT / '.env'
        if env_file.exists():
            with open(env_file, 'r', encoding='utf-8') as f:
                for line in f:
                    line = line.strip()
                    if line and '=' in line and not line.startswith('#'):
                        key, value = line.split('=', 1)
                        os.environ[key.strip()] = value.strip()

    def load_json_config(self):
        """Load configuration from config.json if exists"""
        config_file = PROJECT_ROOT / 'config.json'
        if config_file.exists():
            with open(config_file, 'r', encoding='utf-8') as f:
                data = json.load(f)
                for key, value in data.items():
                    upper_key = key.upper()
                    if hasattr(self, upper_key) and value:
                        setattr(self, upper_key, value)

    def save_json_config(self, data):
        """Save configuration to config.json"""
        config_file = PROJECT_ROOT / 'config.json'
        save_data = {k: v for k, v in data.items()
                    if 'key' not in k.lower() and 'password' not in k.lower()}
        with open(config_file, 'w', encoding='utf-8') as f:
            json.dump(save_data, f, indent=2, ensure_ascii=False)

    def get(self, key, default=None):
        """Get configuration value"""
        return getattr(self, key.upper(), default)

    def is_configured(self):
        """Check if minimum configuration is set"""
        return bool(self.API_KEY and Path(self.COOKIES_FILE).exists())

    def print_status(self):
        """Print current configuration status"""
        print("\nConfiguration Status:")
        print(f"  API_URL: {'[SET]' if self.API_URL else '[NOT SET]'}")
        print(f"  API_KEY: {'[SET]' if self.API_KEY else '[NOT SET]'}")
        print(f"  API_MODEL: {self.API_MODEL}")
        print(f"  COOKIES_FILE: {self.COOKIES_FILE}")
        print(f"  CHROMEDRIVER_PATH: {self.CHROMEDRIVER_PATH}")
        default_wjx = "https://www.wjx.cn/wjx/promote/joinbacklist.aspx?activity=..."
        print(f"  WJX_ACTIVITY_URL: {self.WJX_ACTIVITY_URL if self.WJX_ACTIVITY_URL else '[REQUIRED - NOT SET]'}")
        print(f"  API configured: {'Yes' if self.is_configured() else 'NO'}")
        print(f"  MIN_DELAY: {self.MIN_DELAY}s")
        print(f"  MAX_DELAY: {self.MAX_DELAY}s")

# Global config instance
config = Config()