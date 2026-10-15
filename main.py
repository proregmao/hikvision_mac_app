#!/usr/bin/env python3
"""
海康威视 macOS 桌面管理工具启动入口
"""

import sys
import os

APP_DIR = os.path.dirname(os.path.abspath(__file__))
PROJECT_ROOT = os.path.dirname(APP_DIR)
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)
if APP_DIR not in sys.path:
    sys.path.insert(0, APP_DIR)

try:
    from hikvision_mac_app.web_server import run_app
except ImportError:
    from web_server import run_app

if __name__ == '__main__':
    run_app()

