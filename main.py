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
import re
import sys
from logging.handlers import TimedRotatingFileHandler
from rfq import get_config, RFQController, __version__


def get_base_dir():
    """获取程序根目录（兼容打包后的exe和直接运行）"""
    if getattr(sys, 'frozen', False):
        return os.path.dirname(sys.executable)
    return os.path.dirname(os.path.abspath(__file__))


def setup_logging(config):
    """
    配置日志系统

    Args:
        config: 配置对象
    """
    # 从配置中读取日志级别和格式，若未指定则使用默认值
    log_cfg = config.logging
    log_level = log_cfg.get('level', 'DEBUG')
    log_format = log_cfg.get('format', '%(asctime)s [%(levelname)s] %(message)s')

    # 在项目根目录下创建 logs 文件夹用于存放日志文件
    log_dir = os.path.join(get_base_dir(), 'logs')
    os.makedirs(log_dir, exist_ok=True)

    # 构造主日志文件路径: logs/rfq_conditioning.log
    base_name = 'rfq_conditioning'
    log_file = os.path.join(log_dir, f'{base_name}.log')

    def log_namer(default_name):
        """
        自定义日志文件命名器，将轮转后的日志文件重命名为
        rfq_conditioning_YYYY-MM-DD.log 的格式。

        TimedRotatingFileHandler 默认命名规则为 <basename>.<suffix>，
        此函数将其改为 <basename>_<suffix>.log，使文件名更直观。

        Args:
            default_name: Handler 生成的默认轮转文件名
        """
        filename = os.path.basename(default_name)
        # 以最后一个 '.' 分割，尝试分离文件名与日期后缀
        parts = filename.rsplit('.', 1)
        if len(parts) == 2 and re.match(r'\d{4}-\d{2}-\d{2}', parts[1]):
            # 情况1: 文件名形如 rfq_conditioning.2025-04-11，日期在后缀部分
            date_part = parts[1]
        else:
            # 情况2: 文件名形如 rfq_conditioning_2025-04-11.log，日期在主名部分
            date_part = parts[0].replace(base_name, '')
            if date_part.startswith('_'):
                date_part = date_part[1:]
        return os.path.join(log_dir, f'{base_name}_{date_part}.log')

    # 创建按天轮转的文件处理器：每天午夜轮转，最多保留 30 个备份
    file_handler = TimedRotatingFileHandler(
        filename=log_file,
        when='midnight',
        interval=1,
        backupCount=30,
        encoding='utf-8',
    )
    # 设置轮转文件的后缀格式和匹配正则，确保只匹配日期格式的文件
    file_handler.suffix = '%Y-%m-%d'
    file_handler.extMatch = r'^\d{4}-\d{2}-\d{2}$'
    file_handler.namer = log_namer

    # 同时输出到文件和控制台
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
    print(f"  RFQ自动老练系统 v{__version__} - 模块化版本")
    print("="*60)
    print("\n配置参数:")
    print(f"  版本号: {__version__}")
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
        config_path = os.path.join(get_base_dir(), 'config.yaml')
        config = get_config(config_path)

        # 配置日志
        setup_logging(config)

        # 打印欢迎信息
        print_welcome(config)

        # 在日志中记录版本号，便于现场确认运行的是哪个版本
        logging.info(f"RFQ自动老练系统 v{__version__} 启动")
        logging.info(f"配置文件: {config.config_file}")

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
