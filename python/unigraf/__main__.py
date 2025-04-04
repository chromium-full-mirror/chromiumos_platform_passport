# Copyright 2025 The ChromiumOS Authors
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

"""Launches a gRPC server for interacting with Unigraf UTC-274 USB-C testers.

It utilizes the `utc.server` module to provide the server's
implementation and configures logging based on command-line arguments.

The module defines a `serve` function that initializes and starts the gRPC
server, listening on a specified port. The main entry point parses command-line
arguments for port, log level, and log path, then configures logging and starts
the server.
"""

import argparse
from concurrent import futures
import logging

# pylint: disable=import-error
from chromiumos.test.lab.api.passport import usb_tester_service_pb2_grpc
import grpc
from utc274 import server as unigrafctl

from utils import log_functionality


# pylint: enable=import-error


@log_functionality.logger
def serve(port):
    server = grpc.server(futures.ThreadPoolExecutor(max_workers=10))

    usb_tester_service_pb2_grpc.add_UsbTesterServiceServicer_to_server(
        unigrafctl.UnigrafServer(), server
    )

    server.add_insecure_port(f"[::]:{port}")
    server.start()

    logging.info("Server started, listening on %d", port)
    server.wait_for_termination()


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--port",
        nargs="?",
        type=int,
        default=8787,
        help="The port on which to start the server",
    )
    parser.add_argument(
        "--log-level",
        type=str,
        default="INFO",
        choices=["DEBUG", "INFO", "WARN", "ERROR"],
        help="The level to use while logging.",
    )
    parser.add_argument(
        "--log-path",
        type=str,
        default="/tmp/cros-passport/log.txt",
        help="The path to use when logging.",
    )

    args = parser.parse_args()
    log_functionality.configure_logging(args.log_path, args.log_level)

    serve(args.port)
