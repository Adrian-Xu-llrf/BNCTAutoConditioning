#!/usr/bin/env python3
import os
import sys
from pathlib import Path
import logging

ROOT = Path(__file__).resolve().parents[3]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from rfq import RFQController, get_config


def main():
    config_file = os.environ.get("RFQ_CONFIG_FILE", "config.yaml")
    config = get_config(config_file)
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(message)s",
        handlers=[logging.StreamHandler()],
    )
    controller = RFQController(config)
    controller.run()


if __name__ == "__main__":
    main()
