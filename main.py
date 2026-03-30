#!/usr/bin/env python3
"""
RFQ自动老练系统 - 主程序入口
模块化版本，配置参数在config.yaml中

使用方法：
1. 修改config.yaml中的配置参数
2. 运行: python main.py
3. 通过EPICS设置 AutoC_Start=1 启动老练

作者: Chengye Xu
日期: 2025-11
"""

import logging
import sys
from rfq import get_config, RFQController


def setup_logging(config):
    """
    配置日志系统

    Args:
        config: 配置对象
    """
    log_cfg = config.logging
    logging.basicConfig(
        level=log_cfg.get('level', 'DEBUG'),
        format=log_cfg.get('format', '%(asctime)s [%(levelname)s] %(message)s'),
        handlers=[
            logging.FileHandler(log_cfg.get('file', 'rfq_auto_conditioning.log'), encoding='utf-8'),
            logging.StreamHandler()
        ]
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
