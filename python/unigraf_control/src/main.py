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
import log_functionality
import translate
import UTCLibrary


class UnigrafServer(usb_tester_service_pb2_grpc.UsbTesterServiceServicer):
    @log_functionality.logger
    def __init__(self):
        self._lib = UTCLibrary.UTCLib()
        # Read the device list on init. This eliminates the need of doing
        # a `GetTesters` first if you already know the serial.
        self._raw_device = self._lib.devices_name_list()
        self._serial_locks = {}
        self._open_devices = {}

        self.SDK_F_MAP = translate.SDK_F_MAP

    @log_functionality.logger
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

    @log_functionality.logger
    def OpenTester(self, request, context):
        """Used to open the serial of the USB tester being used."""
        serial = request.id

        if serial in self._serial_locks or serial in self._open_devices:
            raise ProcessLookupError(f"Serial ${serial} is already open.")

        self._serial_locks[serial] = threading.Lock()
        self._open_devices[serial] = self._lib.open_device(serial_number=serial)

        return usb_tester_service_pb2.OpenTesterReply(err_code=0, error_msg="")

    @log_functionality.logger
    def CloseTester(self, request, context):
        """Used to close the serial of the USB tester being used."""
        serial = request.id

        if serial not in self._serial_locks or serial not in self._open_devices:
            raise ProcessLookupError(f"Serial ${serial} is malformed.")

        del self._serial_locks[serial]
        del self._open_devices[serial]

        self._lib.close_device(serial_num=serial)

        return usb_tester_service_pb2.CloseTesterReply(err_code=0, error_msg="")

    # TODO: add timeout and delay params
    @log_functionality.logger
    def _capability_get(self, serial, attr):
        if serial not in self._open_devices:
            logging.error("Invalid serial %s when taking device", serial)
            raise ValueError(f"No device with serial {serial}")

        if serial not in self._serial_locks:
            logging.error("Invalid serial %s when taking lock", serial)
            raise ValueError(f"No device lock with serial {serial}")

        val = None
        with self._serial_locks[serial]:
            dev = self._open_devices[serial]
            try:
                get_f = getattr(dev.pd, self.SDK_F_MAP[attr][0])
                update_f = getattr(dev.pd, self.SDK_F_MAP[attr][1])
            except Exception as e:
                logging.error(
                    "An error occurred during device reflection: %s", str(e)
                )
                raise e

            update_f()
            val = get_f()

        return val

    # TODO: add timeout and delay params
    @log_functionality.logger
    def _capability_set(self, serial, attr, val):
        if serial not in self._open_devices:
            logging.error("Invalid serial %s when taking device", serial)
            raise ValueError(f"No device with serial {serial}")

        if serial not in self._serial_locks:
            logging.error("Invalid serial %s when taking lock", serial)
            raise ValueError(f"No device lock with serial {serial}")

        with self._serial_locks[serial]:
            dev = self._open_devices[serial]
            try:
                set_f = getattr(dev.pd, self.SDK_F_MAP[attr][2])
                update_f = getattr(dev.pd, self.SDK_F_MAP[attr][1])
            except Exception as e:
                logging.error(
                    "An error occurred during device reflection: %s", str(e)
                )
                raise e

            ret = set_f(val)
            update_f()

            return ret

    @log_functionality.logger
    def GetTesterCapability(self, request, context):
        """This method is used to get the value for: dp pin assignment,
        active cc, power role, data role, usb channel, cable mode, init pd state
        """

        val = self._capability_get(request.id, request.capability)
        reply = usb_tester_service_pb2.GetUsbTesterCapabilityReply(err_code=0)

        # Set the field by looking at the name of the field
        # that was set in the get request.
        setattr(
            reply,
            translate.sdk_capability_to_reply_set_member(request.capability),
            translate.sdk_get_val_to_grcp_get_val(request.capability, val),
        )

        return reply

    @log_functionality.logger
    def SetTesterCapability(self, request, context):
        """This method is used to set the value for: dp pin assignment,
        active cc, power role, data role, usb channel, cable mode, init pd state
        """

        to_set = translate.grcp_set_val_to_sdk_set_val(request)
        ret = self._capability_set(request.id, request.capability, to_set)

        return usb_tester_service_pb2.SetUsbTesterCapabilityReply(
            err_code=ret, error_msg=("set failed" if ret != 0 else "")
        )


@log_functionality.logger
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
    log_functionality.configure_logging()

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
