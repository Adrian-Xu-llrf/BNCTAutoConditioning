#!/usr/bin/env python3
"""
RFQ自动老练系统 - 主程序入口
模块化版本，配置参数在config.yaml中

使用方法：
1. 修改config.yaml中的配置参数
2. 运行: python main.py
3. 通过EPICS设置 AutoC_Start=1 启动老练

作者: Chengye Xu
日期: 2026-03
"""

import logging
import os
import sys
from logging.handlers import TimedRotatingFileHandler
from rfq import get_config, RFQController


def setup_logging(config):
    """
    配置日志系统

    Args:
        config: 配置对象
    """
    log_cfg = config.logging
    log_level = log_cfg.get('level', 'DEBUG')
    log_format = log_cfg.get('format', '%(asctime)s [%(levelname)s] %(message)s')

    log_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'logs')
    os.makedirs(log_dir, exist_ok=True)

    base_name = 'rfq_conditioning'
    log_file = os.path.join(log_dir, f'{base_name}.log')

    def log_namer(default_name):
        filename = os.path.basename(default_name)
        parts = filename.rsplit('.', 1)
        if len(parts) == 2 and parts[1].startswith('2026'):
            date_part = parts[1]
        else:
            date_part = parts[0].replace(base_name, '')
            if date_part.startswith('_'):
                date_part = date_part[1:]
        return os.path.join(log_dir, f'{base_name}_{date_part}.log')

    file_handler = TimedRotatingFileHandler(
        filename=log_file,
        when='midnight',
        interval=1,
        backupCount=30,
        encoding='utf-8',
    )
    file_handler.suffix = '%Y-%m-%d'
    file_handler.extMatch = r'^\d{4}-\d{2}-\d{2}$'
    file_handler.namer = log_namer

    logging.basicConfig(
        level=log_level,
        format=log_format,
        handlers=[
            file_handler,
            logging.StreamHandler(),
        ],
    )


def print_welcome(config):
    """
    打印欢迎信息

    Args:
        config: 配置对象
    """
    print("\n" + "="*60)
    print("  RFQ自动老练系统 - 模块化版本")
    print("="*60)
    print("\n配置参数:")
    print(f"  目标功率等参数将从EPICS PV读取")
    print(f"  真空阈值: {config.vacuum['threshold']:.2e} Pa")
    print(f"  配置文件: {config.config_file}")
    print("\n启动步骤:")
    print("  1. 通过EPICS设置目标功率、初始Drive等参数")
    print("  2. 运行本程序")
    print(f"  3. 执行: caput {config.get_pv('control.start')} 1")
    print("\n按Ctrl+C可随时停止")
    print("="*60 + "\n")


def main():
    """主函数"""
    try:
        # 加载配置
        config = get_config('config.yaml')

        # 配置日志
        setup_logging(config)

        # 打印欢迎信息
        print_welcome(config)

        # 等待用户确认
        input("按Enter键开始运行...")

        # 创建并运行控制器
        controller = RFQController(config)
        controller.run()

    except FileNotFoundError as e:
        print(f"错误: {e}")
        print("请确保config.yaml文件存在")
        sys.exit(1)

    except KeyboardInterrupt:
        print("\n程序被用户中断")
        sys.exit(0)

    except Exception as e:
        print(f"发生错误: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)


if __name__ == '__main__':
    main()
