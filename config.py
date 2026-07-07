import os
import secrets
import string
from pathlib import Path

# 先加载 .env 文件（确保环境变量在读 Config 前已设置）
_env_path = Path(__file__).parent / '.env'
if _env_path.exists():
    with open(_env_path, 'r', encoding='utf-8') as _f:
        for _line in _f:
            _line = _line.strip()
            if _line and not _line.startswith('#'):
                if '=' in _line:
                    _k, _v = _line.split('=', 1)
                    _k = _k.strip()
                    _v = _v.strip().strip('"').strip("'")
                    if _k not in os.environ:
                        os.environ[_k] = _v


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
