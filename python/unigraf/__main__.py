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
import sys

# pylint: disable=import-error
from chromiumos.test.lab.api.passport import usb_tester_service_pb2_grpc
from chromiumos.test.lab.api.passport import video_tester_service_pb2_grpc
import grpc
from metrics import telemetry
from ucd import ucd422
from ucd import ucd500
from utc274 import fwupdate as utc274fwup
from utc274 import server as utc274ctl

from utils import constants
from utils import log_functionality


# pylint: enable=import-error


@log_functionality.logger
def serve(port, device_type, port_scan_pattern):
    telemetry_interceptor = telemetry.GlobalMetricsInterceptor(
        telemetry.MetricsService()
    )

    server = grpc.server(
        futures.ThreadPoolExecutor(max_workers=10),
        options=[
            ("grpc.max_receive_message_length", 256 * 1024 * 1024),
            ("grpc.max_send_message_length", 256 * 1024 * 1024),
        ],
        interceptors=[
            telemetry_interceptor,
        ],
    )

    if device_type in ["ALL", "UTC274"]:
        usb_tester_service_pb2_grpc.add_UsbTesterServiceServicer_to_server(
            utc274ctl.UnigrafServer(), server
        )

    if device_type in ["ALL", "UCD500"]:
        video_tester_service_pb2_grpc.add_VideoTesterServiceServicer_to_server(
            ucd500.Ucd500Server(), server
        )

    if device_type in ["ALL", "UCD422"]:
        video_tester_service_pb2_grpc.add_VideoTesterServiceServicer_to_server(
            ucd422.Ucd422Server(), server
        )

    run_port = server.add_insecure_port(f"[::]:{port}")

    server.start()
    # Do not remove or change this line.
    logging.info("%s:%d", port_scan_pattern, run_port)

    server.wait_for_termination()


@log_functionality.logger
def fwupdate(device_type, fw_update, force_update, device_serial, fw_version):
    logging.info("Check for FW updates")
    if device_type in ["ALL", "UTC274"] and fw_update:
        logging.info("The UTC-274s will be updated.")

        fwup = utc274fwup.Utc274FwUpdater(force_update, fw_version)
        if device_serial != "":
            fwup.update_device(device_serial)
        else:
            fwup.update_all_devices()

    if fw_update:
        logging.info("FW updated, terminating")
        sys.exit()


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
        "--port-scan-pattern",
        type=str,
        default="PORT_BOUND",
        help="Pattern to enable run port scanning by a parent app.",
    )
    parser.add_argument(
        "--log-level",
        type=str,
        default="INFO",
        choices=["DEBUG", "INFO", "WARN", "ERROR"],
        help="The level to use while logging.",
    )
    parser.add_argument(
        "--device",
        type=str,
        required=True,
        choices=["ALL", "UTC274", "UCD500", "UCD422"],
        help="The device model to be controlled",
    )
    parser.add_argument(
        "--log-path",
        type=str,
        default="/tmp/cros-passport/log.txt",
        help="The path to use when logging.",
    )
    parser.add_argument(
        "--fwupdate",
        default=False,
        action="store_true",
        help="Do a FW update on the specified class of devices"
        "before starting the server. ALL devices from the class"
        "will be updated. The class is specified with the --device argument.",
    )
    parser.add_argument(
        "--fw-version",
        default=constants.UTC_274_LATEST_FW,
        choices=list(constants.UTC_274_FW.keys()),
        help="Optional to specify the FW version",
    )
    parser.add_argument(
        "--force-update",
        default=False,
        action="store_true",
        help="Enable FW downgrades.",
    )
    parser.add_argument(
        "--device-serial",
        type=str,
        default="",
        help="The serial of the device to perform targeted fw update.",
    )

    args = parser.parse_args()
    log_functionality.configure_logging(args.log_path, args.log_level)

    fwupdate(
        args.device,
        args.fwupdate,
        args.force_update,
        args.device_serial,
        args.fw_version,
    )

    serve(args.port, args.device, args.port_scan_pattern)
