#!/usr/bin/env python3
"""OCR 管理工具 - 启动隐藏的管理页面来调整识别模型参数"""

import argparse
import sys
import os
from pathlib import Path

def main():
    parser = argparse.ArgumentParser(
        description='OCR 识别模型管理工具',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog='''
示例:
  python ocr.py                    启动管理页面 (端口 5001)
  python ocr.py --port 5002        指定端口
  python ocr.py --no-browser       不自动打开浏览器
        '''
    )
    parser.add_argument('--port', type=int, default=5001, help='服务端口 (默认: 5001)')
    parser.add_argument('--host', default='127.0.0.1', help='监听地址 (默认: 127.0.0.1)')
    parser.add_argument('--no-browser', action='store_true', help='不自动打开浏览器')
    parser.add_argument('--debug', action='store_true', help='启用调试模式')

    args = parser.parse_args()

    os.chdir(Path(__file__).parent)

    from app_factory import create_app
    app = create_app()

    url = f'http://{args.host}:{args.port}/ocr-admin'

    print(f'''
╔══════════════════════════════════════════╗
║     OCR 识别模型管理工具                 ║
╠══════════════════════════════════════════╣
║  管理页面: {url:<29}║
║  按 Ctrl+C 停止服务                      ║
╚══════════════════════════════════════════╝
''')

    if not args.no_browser:
        import webbrowser
        import threading
        def open_browser():
            import time
            time.sleep(1.5)
            webbrowser.open(url)
        threading.Thread(target=open_browser, daemon=True).start()

    app.run(host=args.host, port=args.port, debug=args.debug)


if __name__ == '__main__':
    main()
