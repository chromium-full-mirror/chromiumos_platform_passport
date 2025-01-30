# Copyright 2025 The ChromiumOS Authors
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.
from functools import wraps
import logging


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


def configure_logging():
    logging.basicConfig(
        filename="unigraf_server.log",
        format="[%(asctime)s] {%(pathname)s:%(lineno)d} %(levelname)s - %(message)s",
        level=logging.INFO,
    )
