import os

from app_factory import create_app

app = create_app()

if __name__ == '__main__':
    if os.environ.get('IV_ELECTRON') == '1':
        # 托盘桌面版：waitress 生产服务器，地址/端口由 Electron 注入
        from waitress import serve
        serve(app,
              host=os.environ.get('IV_HOST', '0.0.0.0'),
              port=int(os.environ.get('IV_PORT', '5001')),
              threads=8)
    else:
        app.run(debug=True, host='127.0.0.1', port=5001)
