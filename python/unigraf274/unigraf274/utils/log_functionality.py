# Copyright 2025 The ChromiumOS Authors
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.
import datetime
from functools import wraps
import logging
import os


def logger(func):
    """
    A decorator function to log information about function calls and their
    results.
    """

    @wraps(func)
    def wrapper(*args, **kwargs):
        """
        The wrapper function that logs function calls and their results.
        """
        logging.info(
            f"Running {func.__name__} with args: {args}, kwargs: {kwargs}".replace(
                "\n", " "
            )
        )
        try:
            result = func(*args, **kwargs)
            logging.info(
                f"Finished {func.__name__} with result: {result}".replace(
                    "\n", " "
                )
            )

        except Exception as e:
            logging.error(f"Error occurred in {func.__name__}: {e}")
            raise

        else:
            return result

    return wrapper


LOG_LEVEL_MAP = {
    "DEBUG": logging.DEBUG,
    "INFO": logging.INFO,
    "WARN": logging.WARNING,
    "ERROR": logging.ERROR,
}


class CustomFormatter(logging.Formatter):
    """Custom log formatter for structured log messages."""

    def format(self, record: logging.LogRecord) -> str:
        """Formats a log record into a structured string.

        Args:
            record: The log record to format.

        Returns:
            A formatted log string.
        """
        now_utc = datetime.datetime.now(datetime.UTC)
        timestamp = now_utc.strftime("%Y-%m-%dT%H:%M:%S.%f")[:23] + "Z"
        level = record.levelname
        source = f"unigraftctl/{record.filename}:{record.lineno}"
        message = record.getMessage()

        return (
            f"time={timestamp} "
            f"level={level} "
            f"source={source} "
            f'msg="{message}"'
        )


def configure_logging(log_path: str, log_level: str) -> None:
    """Configures logging with a custom formatter and specified level.

    Args:
        log_path: The path to the log file.
        log_level: The desired log level (DEBUG, INFO, WARN, ERROR).
    """
    logger = logging.getLogger()
    logger.setLevel(LOG_LEVEL_MAP[log_level])

    stream_handler = logging.StreamHandler()
    stream_handler.setFormatter(CustomFormatter())

    # Ensure log directory exists
    log_dir = os.path.dirname(log_path)
    # create directory if it does not exist.
    if log_dir and not os.path.exists(log_dir):
        os.makedirs(log_dir, exist_ok=True)

    file_handler = logging.FileHandler(log_path)
    file_handler.setFormatter(CustomFormatter())

    logger.addHandler(file_handler)
    logger.addHandler(stream_handler)
