from __future__ import annotations

import logging
from pathlib import Path


def configure_logger(log_file_path: Path) -> logging.Logger:
    logger = logging.getLogger("editais_bot")
    logger.setLevel(logging.INFO)

    if logger.handlers:
        return logger

    log_file_path.parent.mkdir(parents=True, exist_ok=True)

    formatter = logging.Formatter("%(asctime)s [%(levelname)s] %(message)s")

    stream_handler = logging.StreamHandler()
    stream_handler.setFormatter(formatter)
    logger.addHandler(stream_handler)

    file_handler = logging.FileHandler(log_file_path, encoding="utf-8")
    file_handler.setFormatter(formatter)
    logger.addHandler(file_handler)

    return logger
