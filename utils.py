# -*- coding: utf-8 -*-
import logging
import logging.handlers
from config import LOGGING_LEVEL

def setup_logging(log_path):
    logger = logging.getLogger("")
    logger.setLevel(LOGGING_LEVEL)

    formatter = logging.Formatter(fmt="%(asctime)-15s %(levelname)s %(message)s")
    handler = logging.handlers.RotatingFileHandler(log_path,
            maxBytes=1024*1024, backupCount=3)
    handler.setFormatter(formatter)
    logger.addHandler(handler)

    handler = logging.StreamHandler()
    handler.setFormatter(formatter)
    logger.addHandler(handler)

