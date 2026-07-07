import os
from flask import Flask
from config import config

def create_app(config_name='default'):
    app = Flask(__name__)
    app.config.from_object(config[config_name])
    app.config['SECRET_KEY'] = os.environ.get('SECRET_KEY', app.config['SECRET_KEY'])

    from models.inspection import init_db
    init_db()

    from app_routes import main
    app.register_blueprint(main)

    # 启动时打印默认密码（仅首次随机生成时）
    if not os.environ.get('APP_PASSWORD'):
        app.logger.warning('=' * 60)
        app.logger.warning(f'  默认密码: {app.config["APP_PASSWORD"]}')
        app.logger.warning('  请在 .env 中设置 APP_PASSWORD 自定义密码')
        app.logger.warning('=' * 60)

    return app
