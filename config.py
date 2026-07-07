import os
import secrets
import string
from pathlib import Path

def _gen_default_password():
    """生成随机默认密码"""
    chars = string.ascii_letters + string.digits
    return ''.join(secrets.choice(chars) for _ in range(12))

class Config:
    BASE_DIR = Path(__file__).resolve().parent.parent
    SQLALCHEMY_DATABASE_URI = f"sqlite:///{BASE_DIR / 'inspection_data.db'}"
    SECRET_KEY = os.environ.get('SECRET_KEY', secrets.token_hex(32))
    APP_PASSWORD = os.environ.get('APP_PASSWORD', _gen_default_password())
    DEBUG = False
    SCRAPER_CWD = str(BASE_DIR)

class DevelopmentConfig(Config):
    DEBUG = True

class ProductionConfig(Config):
    DEBUG = False

config = {
    'development': DevelopmentConfig,
    'production': ProductionConfig,
    'default': DevelopmentConfig
}
