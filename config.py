import os
import secrets
import shutil
import string
from pathlib import Path

MODULE_DIR = Path(__file__).resolve().parent

# 桌面版（Electron 托盘）通过 IV_DATA_DIR 注入可写数据目录；
# 未设置时保持原有布局：json/日志/备份在代码目录，SQLite 在代码目录上一级
IV_DATA_DIR = os.environ.get('IV_DATA_DIR')
DATA_DIR = Path(IV_DATA_DIR) if IV_DATA_DIR else MODULE_DIR
if IV_DATA_DIR:
    DATA_DIR.mkdir(parents=True, exist_ok=True)

# 先加载 .env 文件（确保环境变量在读 Config 前已设置）；桌面版优先读数据目录里的 .env
for _env_path in (DATA_DIR / '.env', MODULE_DIR / '.env'):
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
        break


def data_file(filename):
    """数据文件路径。桌面版模式下放在 IV_DATA_DIR，首次缺失时从程序目录复制默认值"""
    if not IV_DATA_DIR:
        return MODULE_DIR / filename
    target = DATA_DIR / filename
    default = MODULE_DIR / filename
    if not target.exists() and default.exists():
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(default, target)
    return target


def data_subdir(name):
    """数据子目录路径。桌面版模式下放在 IV_DATA_DIR 并自动创建"""
    if not IV_DATA_DIR:
        return MODULE_DIR / name
    d = DATA_DIR / name
    d.mkdir(parents=True, exist_ok=True)
    return d


def _gen_default_password():
    """生成随机默认密码"""
    chars = string.ascii_letters + string.digits
    return ''.join(secrets.choice(chars) for _ in range(12))


def _resolve_app_password():
    pw = os.environ.get('APP_PASSWORD')
    if pw:
        return pw
    pw = _gen_default_password()
    # 桌面版没有控制台可打印，把生成的密码落到数据目录供托盘提示
    try:
        (DATA_DIR / 'initial_password.txt').write_text(
            f'本次启动生成的默认密码：{pw}\n'
            f'建议在 {"数据目录" if IV_DATA_DIR else "程序目录"}的 .env 中设置 APP_PASSWORD=你的密码，'
            '设置后重启即固定且本文件不再更新\n',
            encoding='utf-8')
    except OSError:
        pass
    return pw


class Config:
    BASE_DIR = MODULE_DIR.parent
    _db_path = (DATA_DIR / 'inspection_data.db') if IV_DATA_DIR else (BASE_DIR / 'inspection_data.db')
    SQLALCHEMY_DATABASE_URI = f"sqlite:///{_db_path}"
    SECRET_KEY = os.environ.get('SECRET_KEY', secrets.token_hex(32))
    APP_PASSWORD = _resolve_app_password()
    # 未在 .env/环境变量配置 APP_PASSWORD 时为 True(登录页据此显示默认密码提示)
    APP_PASSWORD_IS_DEFAULT = not os.environ.get('APP_PASSWORD')
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
