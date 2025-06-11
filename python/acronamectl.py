# Copyright 2025 The ChromiumOS Authors
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

"""Launches a gRPC server for interacting with Brainstem devices."""

import argparse
from concurrent import futures
import logging

from acroname import switch_service

# pylint: disable=import-error
from chromiumos.test.lab.api.passport import switch_service_pb2_grpc
from common import log_functionality
import grpc


# pylint: enable=import-error


@log_functionality.logger
def serve(port):
    server = grpc.server(
        futures.ThreadPoolExecutor(max_workers=10),
    )

    switch_service_pb2_grpc.add_SwitchServiceServicer_to_server(
        switch_service.SwitchService(), server
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
        default=9494,
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
