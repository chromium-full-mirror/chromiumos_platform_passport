# Copyright 2025 The ChromiumOS Authors
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

"""This module provides a gRPC server for interacting with Unigraf UTC-274.

It encapsulates the Unigraf UTC library, providing gRPC endpoints to manage
tester connections, retrieve and set tester capabilities, and perform various
hardware operations such as cable replugging, hard resets, and EDID loading.
"""

import logging
import operator
import tempfile
import threading

# pylint: disable=import-error
from chromiumos.test.lab.api.passport import usb_tester_service_pb2
from chromiumos.test.lab.api.passport import usb_tester_service_pb2_grpc
from utc274 import translate
import UTCLibrary

from utils import log_functionality


# pylint: enable=import-error


class UnigrafServer(usb_tester_service_pb2_grpc.UsbTesterServiceServicer):
    """gRPC service for interacting with Unigraf UTC 274.

    Provides a gRPC service for interacting with Unigraf USB-C testers,
    managing device connections, capabilities, and operations.
    """

    @log_functionality.logger
    def __init__(self):
        self._lib = UTCLibrary.UTCLib()
        # Read the device list on init. This eliminates the need of doing
        # a `GetTesters` first if you already know the serial.
        self._raw_device = self._lib.devices_name_list()
        self._serial_locks = {}
        self._open_devices = {}

        self.SDK_F_MAP = translate.SDK_F_MAP

        logging.info("UsbTesterServiceServicer init done")

    @log_functionality.logger
    def GetTesters(self, _request, _context):
        """GetTesters probes all testers connected to the host device."""
        # This call will returns a list of tuples:
        # (printable_name, lock status, serial_number).
        # We do a re-read here in order to refresh the list of devices.
        self._raw_device = self._lib.devices_name_list()

        testers = []
        for device in self._raw_device:
            # Raw device list has the type: (printable_name, locked, serial)
            if "UTC-274" not in device[0]:
                continue

            testers.append(
                usb_tester_service_pb2.UsbTester(id=device[2], name="UTC-274")
            )

        return usb_tester_service_pb2.GetTestersReply(testers=testers)

    @log_functionality.logger
    def OpenTester(self, request, _context):
        """Mark the device as in use and initialize it.

        Used to open the serial of the USB tester being used.
        """
        serial = request.id

        if serial in self._serial_locks or serial in self._open_devices:
            logging.info("Device serials locks are: %s", self._serial_locks)
            logging.info("Open devices are: %s", self._open_devices)
            raise ProcessLookupError(f"Serial {serial} is already open.")

        self._serial_locks[serial] = threading.Lock()
        self._open_devices[serial] = self._lib.open_device(serial_number=serial)

        return usb_tester_service_pb2.OpenTesterReply(err_code=0, error_msg="")

    @log_functionality.logger
    def CloseTester(self, request, _context):
        """Free the device resources.

        Used to close the serial of the USB tester being used.
        """
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
                get_f = operator.attrgetter(self.SDK_F_MAP[attr][0])(dev)
                update_f = operator.attrgetter(self.SDK_F_MAP[attr][1])(dev)
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
                set_f = operator.attrgetter(self.SDK_F_MAP[attr][2])(dev)
                update_f = operator.attrgetter(self.SDK_F_MAP[attr][1])(dev)
            except Exception as e:
                logging.error(
                    "An error occurred during device reflection: %s", str(e)
                )
                raise e

            ret = set_f(val)
            update_f()

            return ret

    @log_functionality.logger
    def GetTesterCapability(self, request, _context):
        """This method retrieves various USB-C connection details.

        This method is used to get the value for: dp pin assignment,
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
    def SetTesterCapability(self, request, _context):
        """Manipulate unigraf's capabilities.

        This method is used to set the value for: dp pin assignment,
        active cc, power role, data role, usb channel, cable mode, init pd state
        """

        to_set = translate.grcp_set_val_to_sdk_set_val(request)
        ret = self._capability_set(request.id, request.capability, to_set)

        return usb_tester_service_pb2.SetUsbTesterCapabilityReply(
            err_code=ret, error_msg=("set failed" if ret != 0 else "")
        )

    @log_functionality.logger
    def GetDpInfo(self, request, _context):
        serial = request.id

        if serial not in self._open_devices:
            logging.error("Invalid serial %s when taking device", serial)
            raise ValueError(f"No device with serial {serial}")

        if serial not in self._serial_locks:
            logging.error("Invalid serial %s when taking lock", serial)
            raise ValueError(f"No device lock with serial {serial}")

        ret = 0
        dp_val = {}
        with self._serial_locks[serial]:
            dev = self._open_devices[serial]

            ret = dev.dp.update_dp_info()
            dp_val = dev.dp.dp_info()

        if ret != 0:
            return usb_tester_service_pb2.GetDpInfoReply(
                err_code=ret, error_msg="Failed to update DP info in the SDK"
            )

        reply = usb_tester_service_pb2.GetDpInfoReply(err_code=0)

        logging.info(dp_val)

        for key, val in dp_val.items():
            # Make spelling compatible.
            key = key.lower()
            if key == "lnk_rate":
                key = "link_rate"

            setattr(
                reply,
                key,
                translate.sdk_dp_info_value_map_grcp_value(key, val),
            )

        return reply

    @log_functionality.logger
    def GetActivePort(self, request, _context):
        """Get details about the testing port.

        This method is used to get the active test port on the testing device.
        """
        serial = request.id

        if serial not in self._open_devices:
            logging.error("Invalid serial %s when taking device", serial)
            raise ValueError(f"No device with serial {serial}")

        if serial not in self._serial_locks:
            logging.error("Invalid serial %s when taking lock", serial)
            raise ValueError(f"No device lock with serial {serial}")

        update_stat = self._open_devices[serial].hw.update_port()
        active_port = self._open_devices[serial].hw.port()

        # Build the reply. The UTC-274 has 2 test ports.
        reply = usb_tester_service_pb2.GetActivePortReply(
            err_code=update_stat,
            port_id=active_port,
            max_num_ports=2,
        )

        if update_stat != 0:
            reply.error_msg = "the SDK failed the update"

        return reply

    @log_functionality.logger
    def SetActivePort(self, request, _context):
        """Manipulate the testing port.

        This method is used to set the active test port on the testing device.
        """
        serial = request.id

        if serial not in self._open_devices:
            logging.error("Invalid serial %s when taking device", serial)
            raise ValueError(f"No device with serial {serial}")

        if serial not in self._serial_locks:
            logging.error("Invalid serial %s when taking lock", serial)
            raise ValueError(f"No device lock with serial {serial}")

        dev = self._open_devices[serial]
        set_status = 0
        active_port = dev.hw.port()
        if active_port != request.port_id:
            set_status = dev.hw.select_port(request.port_id)

        dev.hw.update_port()

        reply = usb_tester_service_pb2.SetActivePortReply(
            err_code=set_status,
            error_msg=("the sdk failed to set port" if set_status else ""),
        )

        return reply

    @log_functionality.logger
    def ReplugCable(self, request, _context):
        """Simulate cable replug.

        Simulate the physical disconnect and reconnect of the cable between
        thetester and the DUT.
        """
        serial = request.id

        if serial not in self._open_devices:
            logging.error("Invalid serial %s when taking device", serial)
            raise ValueError(f"No device with serial {serial}")

        if serial not in self._serial_locks:
            logging.error("Invalid serial %s when taking lock", serial)
            raise ValueError(f"No device lock with serial {serial}")

        ret = 0
        with self._serial_locks[serial]:
            dev = self._open_devices[serial]

            ret = dev.pd.replug()

        return usb_tester_service_pb2.DoCableReplugReply(
            err_code=ret,
            error_msg=("" if ret == 0 else "failed to do replug in the SDK"),
        )

    @log_functionality.logger
    def HardResetTester(self, request, _context):
        """This method is used to do a hard reset."""
        serial = request.id

        if serial not in self._open_devices:
            logging.error("Invalid serial %s when taking device", serial)
            raise ValueError(f"No device with serial {serial}")

        if serial not in self._serial_locks:
            logging.error("Invalid serial %s when taking lock", serial)
            raise ValueError(f"No device lock with serial {serial}")

        ret = 0
        with self._serial_locks[serial]:
            dev = self._open_devices[serial]

            ret = dev.sys_reboot()

        return usb_tester_service_pb2.HardResetTesterReply(
            err_code=ret,
            error_msg=(
                "" if ret == 0 else "failed to do hard reset in the SDK"
            ),
        )

    def ResetPd(self, request, context):
        """This method is used to issue power delivery resets."""
        serial = request.id

        if serial not in self._open_devices:
            logging.error("Invalid serial %s when taking device", serial)
            raise ValueError(f"No device with serial {serial}")

        if serial not in self._serial_locks:
            logging.error("Invalid serial %s when taking lock", serial)
            raise ValueError(f"No device lock with serial {serial}")

        ret = 0
        with self._serial_locks[serial]:
            dev = self._open_devices[serial]

            if request.soft:
                ret = dev.pd.soft_reset()
            else:
                ret = dev.pd.hard_reset()

        return usb_tester_service_pb2.HardResetTesterReply(
            err_code=ret,
            error_msg=("" if ret == 0 else "failed to do PD reset in the SDK"),
        )

    @log_functionality.logger
    def LoadEdid(self, request, _context):
        """This method is used to load an EDID."""

        # pylint: disable=R1732
        tmp = tempfile.NamedTemporaryFile(suffix=".bin")

        # Open the file for writing.
        with open(tmp.name, "wb") as f:
            f.write(request.edid)

        logging.info("Temp file name was %s", tmp.name)

        serial = request.id
        if serial not in self._open_devices:
            logging.error("Invalid serial %s when taking device", serial)
            raise ValueError(f"No device with serial {serial}")

        if serial not in self._serial_locks:
            logging.error("Invalid serial %s when taking lock", serial)
            raise ValueError(f"No device lock with serial {serial}")

        ret = 0
        with self._serial_locks[serial]:
            dev = self._open_devices[serial]
            ret = dev.hw.load_edid(tmp.name)

        return usb_tester_service_pb2.LoadEdidReply(
            err_code=ret, error_msg=("" if ret == 0 else "failed to load edid")
        )

    @log_functionality.logger
    def GetPdos(self, request, _context):
        """This method is used to do a hard reset."""
        serial = request.id

        if serial not in self._open_devices:
            logging.error("Invalid serial %s when taking device", serial)
            raise ValueError(f"No device with serial {serial}")

        if serial not in self._serial_locks:
            logging.error("Invalid serial %s when taking lock", serial)
            raise ValueError(f"No device lock with serial {serial}")

        with self._serial_locks[serial]:
            dev = self._open_devices[serial]

            ret = dev.pd.update_dut_pdo()
            sdk_pdos = dev.pd.dut_pdo()
            src_pdos = [
                int.from_bytes(bytearray(pdo), byteorder="little", signed=False)
                for pdo in sdk_pdos
            ]

            return usb_tester_service_pb2.GetPdosReply(
                err_code=ret,
                error_msg="Failed to update PDOs" if ret else "",
                src_pdos=src_pdos,
            )
