# Copyright 2025 The ChromiumOS Authors
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

"""This module provides a gRPC server for interacting with Unigraf UTC-274.

It encapsulates the Unigraf UTC library, providing gRPC endpoints to manage
tester connections, retrieve and set tester capabilities, and perform various
hardware operations such as cable replugging, hard resets, and EDID loading.
"""

import contextlib
import datetime
import logging
import operator
import tempfile
import threading
import time

# pylint: disable=import-error
from chromiumos.test.lab.api.passport import usb_tester_service_pb2
from chromiumos.test.lab.api.passport import usb_tester_service_pb2_grpc
from utc274 import translate
import UTCLibrary

from utils import constants
from utils import log_functionality


# pylint: enable=import-error


class UnigrafServer(usb_tester_service_pb2_grpc.UsbTesterServiceServicer):
    """gRPC service for interacting with Unigraf UTC 274.

    Provides a gRPC service for interacting with Unigraf USB-C testers,
    managing device connections, capabilities, and operations.
    """

    DEVICE_TIMEOUT = datetime.timedelta(hours=1)
    _INACTIVE_DEVICE_CLEANUP_INTERVAL = datetime.timedelta(minutes=5)

    # @log_functionality.logger
    def __init__(self):
        self._lib = UTCLibrary.UTCLib()
        # Read the device list on init. This eliminates the need of doing
        # a `GetTesters` first if you already know the serial.
        self._raw_device = self._lib.devices_name_list()
        self._serial_locks = {}
        self._open_devices = {}
        self._last_access_time = {}
        self._devices_dict_lock = threading.Lock()
        self.SDK_F_MAP = translate.SDK_F_MAP
        self.SELECT_SAFETY_DELAY_S_FMAP = translate.SELECT_SAFETY_DELAY_S_FMAP

        self._cleanup_thread = threading.Thread(
            target=self._cleanup_inactive_devices, daemon=True
        )
        self._cleanup_thread.start()

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
            # Raw device list has the type: (locked(bool), serial, cmd_role)
            testers.append(
                usb_tester_service_pb2.UsbTester(
                    id=device[constants.UTC_274_SERIAL_STRUCT_IDX],
                    name="UTC-274",
                )
            )

        return usb_tester_service_pb2.GetTestersReply(testers=testers)

    @log_functionality.logger
    def OpenTester(self, request, _context):
        """Mark the device as in use and initialize it.

        Used to open the serial of the USB tester being used.
        """
        serial = request.id

        with self._devices_dict_lock:
            if serial in self._serial_locks or serial in self._open_devices:
                logging.info("Device serials locks are: %s", self._serial_locks)
                logging.info("Open devices are: %s", self._open_devices)
                raise ProcessLookupError(f"Serial {serial} is already open.")

            # Try to open the device first so in case this fails we dont populate
            # the locks
            dev = self._lib.open_device(serial_number=serial)

            self._serial_locks[serial] = threading.Lock()
            self._open_devices[serial] = dev
            self._last_access_time[serial] = datetime.datetime.now()

        # Set the active CC when in ET cable mode to CC1
        dev.pd.select_active_cc(
            translate.GRCP_CAPABILITY_VALUE_MAP_SDK_VALUE[
                (usb_tester_service_pb2.ACTIVE_CC, usb_tester_service_pb2.CC1)
            ]
        )

        logging.info(
            "Device FW: pdc %s, ms %s",
            dev.pd_version,
            dev.ms_version,
        )

        return usb_tester_service_pb2.OpenTesterReply(err_code=0, error_msg="")

    def CloseTester(self, request, _context):
        """Free the device resources.

        Used to close the serial of the USB tester being used.
        """
        serial = request.id
        with self._devices_dict_lock:
            cleanup_performed = self._close_device(serial)

        return usb_tester_service_pb2.CloseTesterReply(
            err_code=(not cleanup_performed),
            error_msg="",
        )

    # TODO: add timeout and delay params
    def _capability_get(self, serial, attr):
        val = None
        with self._device_access(serial) as dev:
            try:
                get_f = operator.attrgetter(self.SDK_F_MAP[attr][0])(dev)
            except Exception as e:
                logging.error(
                    "An error occurred during device reflection: %s", str(e)
                )
                raise e

            val = get_f()
        return val

    # TODO: add timeout and delay params
    def _capability_set(self, serial, attr, val):
        ret = None
        with self._device_access(serial) as dev:
            try:
                set_f = operator.attrgetter(self.SDK_F_MAP[attr][1])(dev)
                get_f = operator.attrgetter(self.SDK_F_MAP[attr][0])(dev)
            except Exception as e:
                logging.error(
                    "An error occurred during device reflection: %s", str(e)
                )
                raise e

            ret = 0
            curr_value = get_f()
            if curr_value != val:
                logging.info(f"Setting {attr} to {val}")
                ret = set_f(arg=val)
                delay = self.SELECT_SAFETY_DELAY_S_FMAP.get(attr)
                if delay:
                    time.sleep(delay)
            else:
                logging.info(
                    f"Skipping {attr} because current val is the same as set val {val}"
                )

        return ret

    def GetTesterCapability(self, request, _context):
        """This method retrieves various USB-C connection details.

        This method is used to get the value for: dp pin assignment,
        active cc, power role, data role, usb channel, cable mode, init pd state
        """

        val = self._capability_get(request.id, request.capability)
        reply = usb_tester_service_pb2.GetUsbTesterCapabilityReply(err_code=0)
        if val < 0:
            reply.error_code = val
            reply.error_msg = "Failed to get capability"

        # Set the field by looking at the name of the field
        # that was set in the get request.
        setattr(
            reply,
            translate.sdk_capability_to_reply_set_member(request.capability),
            translate.sdk_get_val_to_grcp_get_val(request.capability, val),
        )

        return reply

    def SetTesterCapability(self, request, _context):
        """Manipulate unigraf's capabilities.

        This method is used to set the value for: dp pin assignment,
        active cc, power role, data role, usb channel, cable mode, init pd state
        """

        if request.capability == usb_tester_service_pb2.CABLE_MODE:
            return usb_tester_service_pb2.SetUsbTesterCapabilityReply(
                err_code=0,
            )

        to_set = translate.grcp_set_val_to_sdk_set_val(request)
        ret = self._capability_set(request.id, request.capability, to_set)

        return usb_tester_service_pb2.SetUsbTesterCapabilityReply(
            err_code=ret, error_msg=("set failed" if ret != 0 else "")
        )

    def GetDpInfo(self, request, _context):
        serial = request.id
        dp_val = {}
        with self._device_access(serial) as dev:
            dp_val = dev.dp.update_dp_info()

        if dp_val < 0:
            return usb_tester_service_pb2.GetDpInfoReply(
                err_code=dp_val, error_msg="Failed to update DP info in the SDK"
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

    def GetActivePort(self, request, _context):
        """Get details about the testing port.

        This method is used to get the active test port on the testing device.
        """
        serial = request.id
        active_port = -1
        with self._device_access(serial) as dev:
            active_port = dev.hw.update_active_port()

        if active_port < 0:
            return usb_tester_service_pb2.GetActivePortReply(
                err_code=active_port, error_msg="the SDK get port failed"
            )

        port_state = usb_tester_service_pb2.PORT_STATE_NOT_SET
        if active_port:
            port_state = usb_tester_service_pb2.PORT_STATE_ON
            active_port = active_port - 1
        else:
            port_state = usb_tester_service_pb2.PORT_STATE_OFF

        # Build the reply. The UTC-274 has 2 test ports.
        reply = usb_tester_service_pb2.GetActivePortReply(
            err_code=0,
            port_id=active_port,
            max_num_ports=2,
            state=port_state,
        )

        return reply

    def SetActivePort(self, request, _context):
        """Manipulate the testing port.

        This method is used to set the active test port on the testing device.
        """
        serial = request.id
        set_status = 0
        with self._device_access(serial) as dev:
            active_port = dev.hw.update_active_port()

            # TODO(b/441683499): rework this API so we don't have to do hacky
            # things like this.
            to_set = request.port_id + 1

            if active_port != to_set:
                # TODO (b/450467364): remove this workaround when the FW fixes it.
                dev.dp.hpd_vdm_irq_control()
                set_status = dev.hw.select_active_port(
                    arg=to_set,
                )
                time.sleep(constants.UTC_274_STABILITY_S)

            time.sleep(1)
            if request.state == usb_tester_service_pb2.PORT_STATE_OFF:
                dev.hw.select_active_port(0)
                time.sleep(constants.UTC_274_STABILITY_S)

        reply = usb_tester_service_pb2.SetActivePortReply(
            err_code=set_status,
            error_msg=("the sdk failed to set port" if set_status else ""),
        )

        return reply

    def ReplugCable(self, request, _context):
        """Simulate cable replug.

        Simulate the physical disconnect and reconnect of the cable between
        thetester and the DUT.
        """
        serial = request.id
        ret = 0
        with self._device_access(serial) as dev:
            # TODO (b/450467364): remove this workaround when the FW fixes it.
            dev.dp.hpd_vdm_irq_control()
            ret = dev.pd.replug()
            time.sleep(constants.UTC_274_STABILITY_S)

        return usb_tester_service_pb2.DoCableReplugReply(
            err_code=ret,
            error_msg=("" if ret == 0 else "failed to do replug in the SDK"),
        )

    def HardResetTester(self, request, _context):
        """This method is used to do a hard reset."""
        serial = request.id
        ret = 0
        with self._device_access(serial) as dev:
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
        ret = 0
        with self._device_access(serial) as dev:
            if request.soft:
                ret = dev.pd.soft_reset()
            else:
                # TODO (b/450467364): remove this workaround when the FW fixes it.
                dev.dp.hpd_vdm_irq_control()
                ret = dev.pd.hard_reset()
                time.sleep(constants.UTC_274_STABILITY_S)

        return usb_tester_service_pb2.HardResetTesterReply(
            err_code=ret,
            error_msg=("" if ret == 0 else "failed to do PD reset in the SDK"),
        )

    def LoadEdid(self, request, _context):
        """This method is used to load an EDID."""

        # pylint: disable=R1732
        tmp = tempfile.NamedTemporaryFile(suffix=".bin")

        # Open the file for writing.
        with open(tmp.name, "wb") as f:
            f.write(request.edid)

        logging.info("Temp file name was %s", tmp.name)

        serial = request.id
        ret = 0
        with self._device_access(serial) as dev:
            ret = dev.hw.load_edid(tmp.name)

        return usb_tester_service_pb2.LoadEdidReply(
            err_code=ret, error_msg=("" if ret == 0 else "failed to load edid")
        )

    def GetPdos(self, request, _context):
        """This method is used to do a hard reset."""
        serial = request.id
        src_pdos = []
        with self._device_access(serial) as dev:
            sdk_pdos = dev.pd.update_dut_pdo()
            src_pdos = [
                int.from_bytes(bytearray(pdo), byteorder="little", signed=False)
                for pdo in sdk_pdos
            ]

        return usb_tester_service_pb2.GetPdosReply(
            err_code=0,
            error_msg="",
            src_pdos=src_pdos,
        )

    def SendVdmHpd(self, request, context):
        """This method is used send a VDM HPDs."""

        serial = request.id
        ret = 0
        with self._device_access(serial) as dev:
            if request.vdm_hpd == usb_tester_service_pb2.VDM_HPD_IRQ:
                ret = dev.dp.hpd_vdm_irq_control()

        return usb_tester_service_pb2.SendVdmHpdReply(
            err_code=ret,
            error_msg="Failed to send vdm" if ret else "",
        )

    def SimulateKeyPress(self, request, context):
        """Simulate a key press. ATM this will simulate the "G" key press."""
        serial = request.id
        ret = 0
        with self._device_access(serial) as dev:
            ret = dev.hw.hid_keyboard(
                UTCLibrary.HIDKeyboardKeys.KEY_G,
            )

        return usb_tester_service_pb2.SimulateKeyPressReply(
            err_code=ret,
            error_msg="Failed to simulate key G press" if ret else "",
        )

    def SendPdAlert(self, request, context):
        """Send a PD alert message to partner."""
        serial = request.id
        ret = 0
        with self._device_access(serial) as dev:
            ret = dev.pd.extended_alert_message_event(
                translate.GRCP_ALERT_TO_SDK_ALERT[request.pd_alert]
            )

        return usb_tester_service_pb2.SendPdAlertReply(err_code=ret)

    def GetPdStats(self, request, context):
        """Get statistics about the PD requests."""
        serial = request.id
        reply = usb_tester_service_pb2.GetPdStatsReply(err_code=0)
        with self._device_access(serial) as dev:
            pd_dev = dev.pd
            power_roles_spwas_stats = {
                i: pd_dev.update_power_role_swap_count(i.value)
                for i in list(translate.PdSwapType)
            }

            reply.power_role_swap_count_allow = power_roles_spwas_stats[
                translate.PdSwapType.ACCEPT
            ]
            reply.power_role_swap_count_reject = power_roles_spwas_stats[
                translate.PdSwapType.REJECT
            ]
            reply.power_role_swap_count_wait = power_roles_spwas_stats[
                translate.PdSwapType.WAIT
            ]
            reply.power_role_swap_count_total = sum(
                [v for v in power_roles_spwas_stats.values() if v > 0]
            )

            data_roles_spwas_stats = {
                i: pd_dev.update_data_role_swap_count(i.value)
                for i in list(translate.PdSwapType)
            }
            reply.data_role_swap_count_allow = data_roles_spwas_stats[
                translate.PdSwapType.ACCEPT
            ]
            reply.data_role_swap_count_reject = data_roles_spwas_stats[
                translate.PdSwapType.REJECT
            ]
            reply.data_role_swap_count_wait = data_roles_spwas_stats[
                translate.PdSwapType.WAIT
            ]
            reply.data_role_swap_count_total = sum(
                [v for v in data_roles_spwas_stats.values() if v > 0]
            )

            if (
                sum(power_roles_spwas_stats.values())
                != reply.power_role_swap_count_total
                or sum(data_roles_spwas_stats.values())
                != reply.data_role_swap_count_total
            ):
                reply.err_code = -1

        return reply

    def ResetPdStats(self, request, context):
        """Reset the PD statistics."""
        serial = request.id
        sdk_err_code = 0
        with self._device_access(serial) as dev:
            pd_dev = dev.pd
            # In case the API call fails a negative error code will be returned.
            data_role_resets = [
                pd_dev.reset_data_role_swap_count(i.value)
                for i in list(translate.PdSwapType)
            ]
            power_role_resets = [
                pd_dev.reset_power_role_swap_count(i.value)
                for i in list(translate.PdSwapType)
            ]
            sdk_err_code = min(min(data_role_resets), min(power_role_resets))

        return usb_tester_service_pb2.GetPdStatsReply(
            err_code=sdk_err_code,
        )

    def _close_device(self, serial):
        """Closes a device and cleans up its resources.

        This method should be called with self._devices_dict_lock held.
        """
        cleanup_performed = False
        if serial in self._serial_locks:
            logging.info("Removing serial lock for  %s", serial)
            del self._serial_locks[serial]
            cleanup_performed = True

        if serial in self._open_devices:
            logging.info("Removing device controller for %s", serial)
            try:
                self._lib.close_device(serial_num=serial)
                del self._open_devices[serial]
                if serial in self._last_access_time:
                    del self._last_access_time[serial]
                cleanup_performed = True
            except Exception as e:
                # We still got things to clean up, put the flag to false in case anything fails.
                logging.error("Failed to close device %s: %s", serial, e)
                cleanup_performed = False

        return cleanup_performed

    def _cleanup_inactive_devices(self):
        """Periodically checks for and closes inactive devices."""
        while True:
            time.sleep(self._INACTIVE_DEVICE_CLEANUP_INTERVAL.total_seconds())
            now = datetime.datetime.now()

            inactive_serials = []
            with self._devices_dict_lock:
                for serial, last_access in list(self._last_access_time.items()):
                    if now - last_access > self.DEVICE_TIMEOUT:
                        inactive_serials.append(serial)

            for serial in inactive_serials:
                logging.info(
                    "Device %s has been inactive for over %s. Closing.",
                    serial,
                    self.DEVICE_TIMEOUT,
                )
                with self._devices_dict_lock:
                    self._close_device(serial)

    @contextlib.contextmanager
    def _device_access(self, serial):
        """A context manager for thread-safe device access."""
        with self._devices_dict_lock:
            if serial not in self._open_devices:
                logging.info("Open devices are: %s", self._open_devices)
                raise ValueError(f"No device with serial {serial}")
            if serial not in self._serial_locks:
                logging.info("Open device locks are: %s", self._serial_locks)
                raise ValueError(f"No device lock with serial {serial}")

        with self._serial_locks[serial]:
            # The device could have been closed by another thread after the check
            # and before we acquired the serial lock.
            dev = self._open_devices.get(serial)
            if not dev:
                raise ValueError(f"Device {serial} was closed unexpectedly.")
            yield dev

        with self._devices_dict_lock:
            if serial in self._last_access_time:
                self._last_access_time[serial] = datetime.datetime.now()
