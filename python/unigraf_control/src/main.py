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
import translate
import UTCLibrary


class UnigrafServer(usb_tester_service_pb2_grpc.UsbTesterServiceServicer):
    def __init__(self):
        self._lib = UTCLibrary.UTCLib()
        # Read the device list on init. This eliminates the need of doing
        # a `GetTesters` first if you already know the serial.
        self._raw_device = self._lib.devices_name_list()
        self._serial_locks = {}
        self._open_devices = {}

        self.SDK_F_MAP = translate.SDK_F_MAP

    def GetTesters(self, request, context):
        """GetTesters probes all testers connected to the host device."""
        # This call will returns a list of tuples:
        # (printable_name, lock status, serial_number).
        # We do a re-read here in order to refresh the list of devices.
        self._raw_device = self._lib.devices_name_list()

        testers = []
        for device in self._raw_device:
            # Raw device list has the type: (printable_name, locked, serial)
            testers.append(
                usb_tester_service_pb2.UsbTester(id=device[2], name="UTC-274")
            )

        return usb_tester_service_pb2.GetTestersReply(testers=testers)

    def OpenTester(self, request, context):
        """Used to open the serial of the USB tester being used."""
        serial = request.id

        if serial in self._serial_locks or serial in self._open_devices:
            raise ProcessLookupError(f"Serial ${serial} is already open.")

        self._serial_locks[serial] = threading.Lock()
        self._open_devices[serial] = self._lib.open_device(serial_number=serial)

        return usb_tester_service_pb2.OpenTesterReply(err_code=0, error_msg="")

    def CloseTester(self, request, context):
        """Used to close the serial of the USB tester being used."""
        serial = request.id

        if serial not in self._serial_locks or serial not in self._open_devices:
            raise ProcessLookupError(f"Serial ${serial} is malformed.")

        del self._serial_locks[serial]
        del self._open_devices[serial]

        self._lib.close_device(serial_num=serial)

        return usb_tester_service_pb2.CloseTesterReply(err_code=0, error_msg="")


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
