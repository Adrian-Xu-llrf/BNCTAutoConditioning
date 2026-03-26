"""
pytest 配置 - 添加项目根目录到 Python 路径
"""

import sys
import os

# 将项目根目录添加到 sys.path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))
