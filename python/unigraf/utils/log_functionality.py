# Copyright 2025 The ChromiumOS Authors
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

"""This module provides utilities for logging.

It includes:

-   A `logger` decorator for logging function calls, arguments, results, and
    exceptions.
-   A `CustomFormatter` class for creating structured log messages with
    timestamps, log levels, source file information, and formatted messages.
-   A `configure_logging` function for setting up logging to both a file and
    the console with the custom formatter and specified log level.
-   A `LOG_LEVEL_MAP` dictionary for mapping log level strings to logging
    module constants.

The module is designed to simplify and standardize logging practices within
the unigrafctl project.
"""

import datetime
import functools
import logging
import os
import traceback


def logger(func):
    """Helper logger.

    A decorator function to log information about function calls and their
    results.
    """

    @functools.wraps(func)
    def wrapper(*args, **kwargs):
        """Helper logging function.

        The wrapper function that logs function calls and their results.
        """

        log_msg = f"Running {func.__name__} with args: {args}, kwargs: {kwargs}"
        logging.info(log_msg.replace("\n", " "))

        try:
            result = func(*args, **kwargs)
            logging.info(
                f"Finished {func.__name__} with result: {result}".replace(
                    "\n", " "
                )
            )

        except Exception as e:
            logging.error("Error trace: %s", traceback.format_exc())
            logging.error("Error occurred in %s: %s", func.__name__, e)
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
            f"source=[{record.process}]{source} "
            f'msg="{message}"'
        )


def configure_logging(log_path: str, log_level: str) -> None:
    """Configures logging with a custom formatter and specified level.

    Args:
        log_path: The path to the log file.
        log_level: The desired log level (DEBUG, INFO, WARN, ERROR).
    """
    custom_logger = logging.getLogger()
    custom_logger.setLevel(LOG_LEVEL_MAP[log_level])

    stream_handler = logging.StreamHandler()
    stream_handler.setFormatter(CustomFormatter())

    # Ensure log directory exists
    log_dir = os.path.dirname(log_path)
    # create directory if it does not exist.
    if log_dir and not os.path.exists(log_dir):
        os.makedirs(log_dir, exist_ok=True)

    file_handler = logging.FileHandler(log_path)
    file_handler.setFormatter(CustomFormatter())

    custom_logger.addHandler(file_handler)
    custom_logger.addHandler(stream_handler)
