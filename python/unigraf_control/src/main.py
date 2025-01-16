# Copyright 2025 The ChromiumOS Authors
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

import argparse
from concurrent import futures
import logging
import threading

from chromiumos.test.lab.api.passport import usb_tester_service_pb2
from chromiumos.test.lab.api.passport import usb_tester_service_pb2_grpc
import grpc


class UnigrafServer(usb_tester_service_pb2_grpc.UsbTesterServiceServicer):
    def __init__(self):
        logging.error("Server not implemented.")


def serve(port):
    server = grpc.server(futures.ThreadPoolExecutor(max_workers=10))

    usb_tester_service_pb2_grpc.add_UsbTesterServiceServicer_to_server(
        UnigrafServer(), server
    )

    server.add_insecure_port(f"[::]:{port}")
    server.start()

    logging.info("Server started, listening on %d", port)
    server.wait_for_termination()


if __name__ == "__main__":
    logging.basicConfig()

    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--port",
        nargs="?",
        const=1,
        type=int,
        default=8787,
        help="The port on which to start the server",
    )
    args = parser.parse_args()

    serve(args.port)
