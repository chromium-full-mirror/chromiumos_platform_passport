# Copyright 2025 The ChromiumOS Authors
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

"""Provides a gRPC server to control Unigraf video testing hardware.

This module implements the VideoTesterService gRPC service, allowing clients
to discover, open, close, and configure Unigraf UCD series video testers
using the UniTAP library.
"""

import atexit
import contextlib
import ctypes
import fcntl
import functools
import gc
import glob
import logging
import math
import os
import re
import tempfile
import threading
import time
from typing import Any

# pylint: disable=import-error
from chromiumos.test.lab.api.passport import (
    video_tester_service_pb2 as video_pb2,
)
from chromiumos.test.lab.api.passport import (
    video_tester_service_pb2_grpc as video_pb2_grpc,
)
import grpc
from ucd import translate
import UniTAP

from utils import constants
from utils import log_functionality


# pylint: enable=import-error

_DEFAULT_LOCK_TIMEOUT_SEC = 90.0
# Frame encoding runs outside the UCD lock; keep UniTAP's native image libs
# single-threaded as they were when everything ran under the UCD lock.
_ENCODE_LOCK = threading.Lock()


def rsetattr(obj, attr, val):
    pre, _, post = attr.rpartition(".")
    return setattr(rgetattr(obj, pre) if pre else obj, post, val)


def rgetattr(obj, attr, *args):
    def _getattr(obj, attr):
        return getattr(obj, attr, *args)

    return functools.reduce(_getattr, [obj] + attr.split("."))


def _get_lock_timeout(self, args, kwargs) -> tuple[Any, float]:
    """Extracts the gRPC context and lock acquisition timeout in seconds."""
    context = kwargs.get("context")
    if context is None and len(args) >= 2:
        context = args[1]
    default_timeout = min(
        float(getattr(self, "_LOCK_TIMEOUT_SEC", _DEFAULT_LOCK_TIMEOUT_SEC)),
        threading.TIMEOUT_MAX,
    )
    time_remaining_fn = getattr(context, "time_remaining", None)
    if callable(time_remaining_fn):
        try:
            remaining = time_remaining_fn()
            if (
                isinstance(remaining, (int, float))
                and not isinstance(remaining, bool)
                and math.isfinite(remaining)
            ):
                return context, min(default_timeout, max(0.0, float(remaining)))
        except Exception:  # pylint: disable=broad-except
            pass
    return context, default_timeout


def synchronized(func):
    """Serializes RPC and lifecycle calls on a UcdServer instance."""

    @functools.wraps(func)
    def wrapper(self, *args, **kwargs):
        lock = getattr(self, "_lock", None)
        if lock is None:
            return func(self, *args, **kwargs)
        context, timeout = _get_lock_timeout(self, args, kwargs)
        if timeout <= 0:
            acquired = lock.acquire(blocking=False)
        else:
            acquired = lock.acquire(timeout=timeout)
        if not acquired:
            msg = (
                f"Timed out after {timeout:.2f}s waiting for UCD lock in"
                f" {func.__name__}"
            )
            logging.error(msg)
            if context is not None:
                context.set_code(grpc.StatusCode.DEADLINE_EXCEEDED)
                context.set_details(msg)
                context.abort(grpc.StatusCode.DEADLINE_EXCEEDED, msg)
            raise TimeoutError(msg)
        try:
            return func(self, *args, **kwargs)
        finally:
            lock.release()

    return wrapper


@contextlib.contextmanager
def temp_file_path(suffix: str = "", extra_suffixes: tuple[str, ...] = ()):
    """Creates a closed temporary file path and unlinks it on exit."""
    with tempfile.NamedTemporaryFile(suffix=suffix, delete=False) as tmp:
        tmp_path = tmp.name
    try:
        yield tmp_path
    finally:
        for ext in ("",) + tuple(extra_suffixes):
            path = f"{tmp_path}{ext}"
            try:
                if os.path.exists(path):
                    os.unlink(path)
            except OSError as e:
                logging.debug("Failed to remove temp file %s: %s", path, e)


def _save_dsc_frame_as_bmp(frame, path: str) -> None:
    """Decodes a DSC frame into a BMP file with UniTAP's native libraries.

    Byte-identical to UniTAP's save_image_to_file, minus its Python glue that
    copies the frame byte by byte twice (about 8x slower, minutes on lab
    hosts for 8K) and never frees the decoded image (b/578947985).
    """
    # pylint: disable=import-outside-toplevel,import-error
    from UniTAP.libs.lib_dscl import dscl
    from UniTAP.libs.lib_dscl import dscl_types
    from UniTAP.libs.lib_uicl import uicl

    # UniTAP prepends the header unless b"DSCF" occurs anywhere in the data,
    # so a payload that happens to contain those bytes fails to decode.
    data = frame.data
    if not data.startswith(b"DSCF"):
        data = b"DSCF" + data
    encoded = dscl_types.DSCL_Image()
    encoded.DataSize = len(data)
    encoded.DataPtr = (ctypes.c_uint8 * len(data)).from_buffer_copy(data)
    decoded = dscl.DSCL_Decode(
        encoded,
        decode_simple422_to_444=frame.compression_info.is_simple_as_444,
    )
    try:
        result = uicl.UICL_SaveToFile(
            decoded, path, uicl.UICL_ImageFileFormat.FILE_FORMAT_BMP
        )
        if result < uicl.UICL_SUCCESS:
            raise RuntimeError(f"Saving decoded DSC frame failed: {result}")
    finally:
        uicl.UICL_FreeImage(decoded)


class UcdServer(video_pb2_grpc.VideoTesterServiceServicer):
    """Implements functionality common to all Unigraf video testers.

    Methods that need specialization:
    - SetLinkVideoTester
    - GetLinkVideoTester
    - HpdPulseVideoTester
    - AttachVideoTester
    - StartEventCapture
    - StopEventCapture
    - _get_number_of_video_streams
    - _role_set_quirks
    """

    _TSI_DEVCAP_CONTROL = 0x210
    _TSI_DEVCAP_FLUSH_FX3 = 0x40000000
    _TSI_W_CAP_COMMAND = 0x301
    _TSI_CAP_CMD_START = 1
    _TSI_CAP_CMD_STOP = 2
    _TSI_CAP_CONFIG = 0x302
    _TSI_USBC_FLUSH_BULK_PIPES_W = 0x5002C004
    _ROLE_SELECT_RETRIES = 2
    _SCREENSHOT_MAX_ATTEMPTS = 3
    _SCREENSHOT_LATCH_DELAY_SEC = 0.5
    _SCREENSHOT_RETRY_DELAY_SEC = 1.0
    _LOCK_TIMEOUT_SEC = _DEFAULT_LOCK_TIMEOUT_SEC
    _HW_RESET_INITIAL_WAIT_SEC = constants.UCD_HW_RESET_TIMEOUT_S
    _USB_REENUMERATION_SETTLE_SEC = 2.0
    _POWER_CYCLE_POLL_INTERVAL_SEC = 2.0
    _POWER_CYCLE_MAX_POLL_ATTEMPTS = 10
    _UNIGRAF_USB_VENDOR_IDS = ("16a6", "1992")
    _PDC_RESET_POLL_INTERVAL_SEC = 0.5
    _PDC_RESET_MAX_POLL_ATTEMPTS = 6

    @log_functionality.logger
    def __init__(self, device_name):
        self._lock = threading.RLock()
        self._dev = None
        self._serial = None
        self._role = None
        self._port_rx = None
        self._port_tx = None
        self._last_requested_role = None
        self._event_capture_active = False
        self._device_name = device_name

        self._tsilib = UniTAP.TsiLib()
        atexit.register(self.__del__)

        logging.info("%sServer init done", self._device_name)

    # =========== Not implemented methods ===========
    def SetLinkVideoTester(self, request, context):
        """Sets advanced link parameters for a given video tester."""
        raise NotImplementedError("Method not implemented!")

    def GetLinkVideoTester(self, request, context):
        """Gets the current advanced link parameters."""
        raise NotImplementedError("Method not implemented!")

    def HpdPulseVideoTester(self, request, context):
        """Sends an HPD (Hot Plug Detect) pulse to a video tester."""
        raise NotImplementedError("Method not implemented!")

    def AttachVideoTester(self, request, context):
        """Simulates attaching/detaching."""
        raise NotImplementedError("Method not implemented!")

    def StartEventCapture(self, request, context):
        """Starts the event capture with the specified filters."""
        raise NotImplementedError("Method not implemented!")

    def StopEventCapture(self, request, context):
        """Stops the event capture and optionally gets the capture files."""
        raise NotImplementedError("Method not implemented!")

    def _get_number_of_video_streams(self):
        raise RuntimeError("Method is not implemented!")

    def _role_set_quirks(self, role_to_set):
        raise RuntimeError("Method is not implemented!")

    # =========== Low-level UniTAP / libTSI SDK Interop ===========
    # pylint: disable=protected-access
    def _rescan_devices(self) -> None:
        """Refreshes libTSI's internal USB table when no handle is open."""
        if self._dev is not None:
            return
        tsi_mod = getattr(
            getattr(getattr(UniTAP, "libs", None), "lib_tsi", None),
            "tsi",
            None,
        )
        rescan_fn = getattr(tsi_mod, "TSIX_DEV_RescanDevices", None)
        if callable(rescan_fn):
            try:
                rescan_fn()
            except Exception as e:  # pylint: disable=broad-except
                logging.debug("TSIX_DEV_RescanDevices failed: %s", e)

    def _has_populated_role_list(self, dev=None) -> bool:
        """Returns False only if the device's internal role list is []."""
        target_dev = self._dev if dev is None else dev
        if target_dev is None:
            return False
        role_list = getattr(target_dev, "_TSIDevice__role_list", None)
        if isinstance(role_list, list) and not role_list:
            return False
        return True

    def _clear_sdk_role(self, dev=None) -> None:
        """Clears the cached role reference inside UniTAP DeviceIO."""
        target_dev = self._dev if dev is None else dev
        if target_dev is None:
            return
        try:
            target_dev._TSIDevice__io.set_role(None)
        except Exception as e:  # pylint: disable=broad-except
            logging.debug("Failed to clear SDK role reference: %s", e)

    def _get_fw_info(self) -> str:
        """Reads the prepared firmware version from the open UCD handle."""
        return self._dev._TSIDevice__io.get_prepared_fw_info()

    def _write_device_io_reg(self, reg: int, val: int) -> None:
        """Writes a 32-bit device-level TSI configuration item."""
        self._dev._TSIDevice__io.set(reg, val)

    def _flush_fx3(self) -> None:
        """Flushes the Cypress FX3 USB bulk endpoints via TSI control."""
        if self._dev is None:
            return
        try:
            self._write_device_io_reg(
                self._TSI_DEVCAP_CONTROL,
                self._TSI_DEVCAP_FLUSH_FX3,
            )
        except Exception as e:  # pylint: disable=broad-except
            logging.debug(
                "Failed to flush FX3 status on %s: %s", self._serial, e
            )

    def _reset_device_io(self) -> None:
        """Issues an in-band NIOS/FPGA reset via TSI_DEVICE_HW_RESET."""
        self._dev._TSIDevice__io.reset()

    def _get_rx_port_io(self):
        """Returns the underlying PortIO instance for the RX port, if any."""
        if self._port_rx is None:
            return None
        port_dict = getattr(self._port_rx, "__dict__", {})
        if "_TSIPort__io" in port_dict:
            return self._port_rx._TSIPort__io
        return getattr(self._port_rx, "_Port__io", None) or getattr(
            self._port_rx, "_TSIPort__io", None
        )

    def _clear_sdk_capturer_buffers(self) -> None:
        """Clears UniTAP's internal bulk buffer and video memory manager."""
        if self._dev is None:
            return
        try:
            self._dev._TSIDevice__capturer.clear_bulk_buffer()
        except Exception as e:  # pylint: disable=broad-except
            logging.debug("Failed to clear bulk buffer during reset: %s", e)
        try:
            self._dev._TSIDevice__memory_manager.reset()
        except Exception as e:  # pylint: disable=broad-except
            logging.debug(
                "Failed to reset video memory manager during reset: %s", e
            )

    @staticmethod
    def _get_event_capturer_buffer(event_capturer) -> list[Any] | None:
        """Returns a copy of the pending event buffer from an EventCapturer."""
        res = getattr(event_capturer, "_EventCapturer__result", None)
        buf = getattr(res, "buffer", None)
        if isinstance(buf, list):
            return list(buf)
        return None

    @staticmethod
    def _restore_event_capturer_buffer(
        event_capturer, saved_events: list[Any]
    ) -> None:
        """Prepends previously saved events back onto an EventCapturer."""
        res = getattr(event_capturer, "_EventCapturer__result", None)
        buf = getattr(res, "buffer", None)
        if isinstance(buf, list):
            buf[:0] = saved_events

    @staticmethod
    def _update_event_capturer_fw_version(port, fw_version: str) -> None:
        """Updates the cached ucd_fw_version string inside EventCapturer."""
        if port is None:
            return
        fw_dict = getattr(port.event_capturer, "_EventCapturer__fw_info", None)
        if isinstance(fw_dict, dict):
            fw_dict["ucd_fw_version"] = fw_version

    def _remove_from_tsilib_device_list(self, dev) -> None:
        """Ensures a closed TSIDevice is removed from TsiLib's device list."""
        try:
            dev_list = getattr(self._tsilib, "_TsiLib__device_list", None)
            if isinstance(dev_list, list) and dev in dev_list:
                dev_list.remove(dev)
        except Exception as e:  # pylint: disable=broad-except
            logging.debug(
                "Failed to remove device from TsiLib device list: %s", e
            )

    # pylint: enable=protected-access

    # =========== Device Handle & Capture Lifecycle ===========
    def _open_device(self, serial: str):
        """Rescans libTSI USB descriptors and opens the requested UCD serial."""
        if self._dev is not None:
            self._close_device()
        self._rescan_devices()
        self._dev = self._tsilib.open(serial)
        return self._dev

    def _stop_active_capturers(self) -> None:
        """Stops any active event or video capturers on RX and TX ports."""
        self._event_capture_active = False
        for port in (self._port_rx, self._port_tx):
            if port is not None:
                for attr in ("event_capturer", "video_capturer"):
                    try:
                        getattr(port, attr).stop()
                    except Exception as e:  # pylint: disable=broad-except
                        logging.debug(
                            "Failed to stop %s during close: %s", attr, e
                        )

    def _close_device(self) -> None:
        """Stops active capturers and closes the current UCD handle."""
        self._stop_active_capturers()
        self._port_rx = None
        self._port_tx = None
        self._role = None
        if self._dev is not None:
            dev = self._dev
            self._dev = None
            try:
                dev.opf_handler = None
            except Exception as e:  # pylint: disable=broad-except
                logging.debug("Failed to clear opf_handler before close: %s", e)
            self._clear_sdk_role(dev)
            try:
                self._tsilib.close(dev)
            except Exception as e:  # pylint: disable=broad-except
                logging.warning(
                    "Error closing UCD device %s (%s); clearing handle anyway.",
                    self._serial,
                    e,
                )
            self._remove_from_tsilib_device_list(dev)
            del dev
            gc.collect()

    def _resume_event_capture_if_active(self) -> None:
        """Re-arms FPGA event capture if video_capturer.stop() halted it."""
        if not self._event_capture_active:
            return
        port_io = self._get_rx_port_io()
        if port_io is not None:
            try:
                port_io.set(self._TSI_W_CAP_COMMAND, self._TSI_CAP_CMD_START)
            except Exception as e:  # pylint: disable=broad-except
                logging.debug(
                    "Failed to re-arm event capture after video stop: %s", e
                )

    def _reset_video_capturer_pipeline(self) -> None:
        """Force-clears the video capturer pipeline and FPGA capture state."""
        if self._port_rx is None:
            return

        running_status = getattr(
            getattr(UniTAP, "EventCaptureStatus", None), "Running", object()
        )
        active_event_capturers = []
        for port in (self._port_rx, self._port_tx):
            event_capturer = getattr(port, "event_capturer", None)
            if (
                event_capturer is not None
                and getattr(event_capturer, "status", None) == running_status
            ):
                try:
                    saved_events = self._get_event_capturer_buffer(
                        event_capturer
                    )
                    event_capturer.stop()
                    active_event_capturers.append(
                        (event_capturer, saved_events)
                    )
                except Exception as e:  # pylint: disable=broad-except
                    logging.debug(
                        "Failed to stop event_capturer during reset: %s", e
                    )

        try:
            self._port_rx.video_capturer.stop()
        except Exception as e:  # pylint: disable=broad-except
            logging.debug("Failed to stop video_capturer during reset: %s", e)

        port_io = self._get_rx_port_io()
        if port_io is not None:
            for reg, val in (
                (self._TSI_CAP_CONFIG, 0),
                (self._TSI_W_CAP_COMMAND, self._TSI_CAP_CMD_STOP),
                (self._TSI_USBC_FLUSH_BULK_PIPES_W, 1),
            ):
                try:
                    port_io.set(reg, val)
                except Exception as e:  # pylint: disable=broad-except
                    logging.debug(
                        "Failed to write TSI reg %#x=%#x during capturer"
                        " reset: %s",
                        reg,
                        val,
                        e,
                    )

        self._clear_sdk_capturer_buffers()

        if (
            self._port_rx.video_capturer.status
            != UniTAP.VideoCaptureStatus.Idle
        ):
            try:
                try:
                    self._port_rx.video_capturer.start(
                        frames_count=0, stream_number=0
                    )
                finally:
                    self._port_rx.video_capturer.stop()
                time.sleep(0.2)
            except Exception as e:  # pylint: disable=broad-except
                logging.debug(
                    "Failed 0-frame pulse during capturer reset: %s", e
                )

        for event_capturer, saved_events in active_event_capturers:
            try:
                event_capturer.start()
                if saved_events:
                    self._restore_event_capturer_buffer(
                        event_capturer, saved_events
                    )
            except Exception as e:  # pylint: disable=broad-except
                logging.debug(
                    "Failed to restart event_capturer after reset: %s", e
                )

        self._resume_event_capture_if_active()

    def _ensure_video_capturer_idle(self) -> None:
        """Ensures the video capturer is Idle, stopping it if needed."""
        if self._port_rx is None:
            return
        current_status = self._port_rx.video_capturer.status
        if current_status != UniTAP.VideoCaptureStatus.Idle:
            logging.warning(
                "Video capturer is not idle (status: %s), attempting to reset",
                current_status,
            )
            try:
                self._port_rx.video_capturer.stop()
                time.sleep(0.2)
            except Exception as e:  # pylint: disable=broad-except
                logging.debug("Non-fatal error resetting capturer: %s", e)

            current_status = self._port_rx.video_capturer.status
            if current_status != UniTAP.VideoCaptureStatus.Idle:
                self._reset_video_capturer_pipeline()
                current_status = self._port_rx.video_capturer.status

            if current_status != UniTAP.VideoCaptureStatus.Idle:
                raise RuntimeError(
                    f"Video capturer is not idle (status: {current_status})"
                )

    # =========== Firmware Validation & Role Recovery Engine ===========
    def _get_active_fw_components(self, role=None) -> list[str]:
        """Returns the firmware component names active for the given role."""
        target_role = self._role if role is None else role
        fw_components = ["UX", "UF"]
        if hasattr(target_role, "pdcrx"):
            fw_components.append("PDRX")
        if hasattr(target_role, "pdctx"):
            fw_components.append("PDTX")
        return fw_components

    def _get_corrupted_fw_components(
        self, fw_info: str, role=None
    ) -> list[str]:
        """Returns active firmware components reporting 0.0.0 (or EMPTY)."""
        if not isinstance(fw_info, str):
            return []
        if not fw_info:
            return ["EMPTY"]
        corrupted = []
        for comp in self._get_active_fw_components(role):
            if re.search(rf"\b{comp}:\s*0\.0\.0(?:\.0)?\b", fw_info):
                corrupted.append(comp)
        return corrupted

    def _is_benign_ux_only_corruption(self, fw_info: str, role=None) -> bool:
        """Checks if only UX is 0.0.0 while UF and active PD are healthy."""
        if not isinstance(fw_info, str):
            return False
        if self._get_corrupted_fw_components(fw_info, role) != ["UX"]:
            return False
        for comp in self._get_active_fw_components(role):
            if comp == "UX":
                continue
            if not re.search(rf"\b{comp}:\s*\d+\.\d+\.\d+", fw_info):
                return False
        return True

    def _recover_corrupted_fw_in_place(
        self, fw_info: str, corrupted: list[str]
    ) -> tuple[str, list[str]]:
        """Attempts in-place recovery of corrupted PD or FX3 firmware state."""
        if "UF" not in corrupted and "EMPTY" not in corrupted:
            pd_controllers = (
                ("PDRX", "pdcrx", "RX"),
                ("PDTX", "pdctx", "TX"),
            )
            for comp, attr, label in pd_controllers:
                if comp in corrupted and hasattr(self._role, attr):
                    logging.warning(
                        "UCD %s reported %s: 0.0.0 (%s); resetting %s PD"
                        " controller in place.",
                        self._serial,
                        comp,
                        fw_info,
                        label,
                    )
                    try:
                        getattr(self._role, attr).controls.reset()
                        for attempt in range(self._PDC_RESET_MAX_POLL_ATTEMPTS):
                            time.sleep(self._PDC_RESET_POLL_INTERVAL_SEC)
                            post_fw_info = self._get_fw_info()
                            still_corrupted = (
                                self._get_corrupted_fw_components(
                                    post_fw_info, self._role
                                )
                            )
                            if (
                                comp not in still_corrupted
                                and attr not in still_corrupted
                            ):
                                logging.info(
                                    "UCD %s %s recovered healthy firmware after"
                                    " %.1fs: %s",
                                    self._serial,
                                    attr,
                                    (attempt + 1)
                                    * self._PDC_RESET_POLL_INTERVAL_SEC,
                                    post_fw_info,
                                )
                                break
                        else:
                            logging.warning(
                                "UCD %s %s remained corrupted after %.1fs"
                                " reset polling.",
                                self._serial,
                                attr,
                                self._PDC_RESET_MAX_POLL_ATTEMPTS
                                * self._PDC_RESET_POLL_INTERVAL_SEC,
                            )
                        fw_info = post_fw_info
                        corrupted = still_corrupted
                    except Exception as e:  # pylint: disable=broad-except
                        logging.debug(
                            "Failed to reset %s on %s: %s",
                            attr,
                            self._serial,
                            e,
                        )

        if "UX" in corrupted:
            self._flush_fx3()

        return fw_info, corrupted

    @staticmethod
    def _resolve_usb_dev_dir(sys_path: str) -> str:
        """Normalizes a sysfs USB file or directory path to its device dir."""
        if os.path.basename(sys_path) in ("serial", "idVendor", "product"):
            return os.path.dirname(sys_path)
        return sys_path

    def _reset_usb_dev_dir(
        self, dev_dir: str, label: str, settle_delay_sec: float
    ) -> bool:
        """Resets a sysfs USB device directory via ioctl or authorized sysfs."""
        bus_path = os.path.join(dev_dir, "busnum")
        dev_num_path = os.path.join(dev_dir, "devnum")
        try:
            with (
                open(bus_path, "r", encoding="utf-8") as f_bus,
                open(dev_num_path, "r", encoding="utf-8") as f_dev,
            ):
                busnum = int(f_bus.read().strip())
                devnum = int(f_dev.read().strip())

            dev_path = f"/dev/bus/usb/{busnum:03d}/{devnum:03d}"
            logging.info(
                "Hardware resetting USB node %s for %s using ioctl",
                dev_path,
                label,
            )

            usbdevfs_reset = 21780
            fd = os.open(dev_path, os.O_WRONLY)
            try:
                fcntl.ioctl(fd, usbdevfs_reset, 0)
            finally:
                os.close(fd)

            if settle_delay_sec > 0:
                time.sleep(settle_delay_sec)
            return True
        except (OSError, ValueError) as e:
            logging.debug(
                "Transient error opening USB ioctl path for %s: %s",
                dev_dir,
                e,
            )
            auth_path = os.path.join(dev_dir, "authorized")
            try:
                with open(auth_path, "w", encoding="utf-8") as f_auth:
                    f_auth.write("0")
                time.sleep(0.5)
                with open(auth_path, "w", encoding="utf-8") as f_auth:
                    f_auth.write("1")
                if settle_delay_sec > 0:
                    time.sleep(settle_delay_sec)
                return True
            except OSError as auth_err:
                logging.debug(
                    "Fallback sysfs authorized toggle failed for %s: %s",
                    dev_dir,
                    auth_err,
                )
        return False

    @log_functionality.logger
    def _force_usb_reenumeration(
        self,
        serial_number: str | None = None,
        settle_delay_sec: float | None = None,
    ) -> bool:
        """Issues a USBDEVFS_RESET ioctl directly to the device node block.

        This does not require write privileges to /sys (which is often mounted
        read-only in containers) - it only requires write access to the specific
        character device (e.g., /dev/bus/usb/XXX/YYY) which Docker strictly
        permits via cgroups. It drops all lingering handles, unbinds the driver,
        bounces the hardware, and re-enumerates it in place without altering the
        devnum.

        Args:
            serial_number: Optional UCD serial number to match in sysfs.
            settle_delay_sec: Optional post-reset settle delay in seconds.

        Returns:
            True if a matching USB device node was reset, False otherwise.
        """
        if settle_delay_sec is None:
            settle_delay_sec = self._USB_REENUMERATION_SETTLE_SEC

        attempted_dirs: set[str] = set()
        if serial_number:
            target_serial = serial_number.strip().upper()
            for sys_path in glob.glob("/sys/bus/usb/devices/*/serial"):
                try:
                    dev_dir = self._resolve_usb_dev_dir(sys_path)
                    serial_path = os.path.join(dev_dir, "serial")
                    with open(serial_path, "r", encoding="utf-8") as f:
                        if f.read().strip().upper() != target_serial:
                            continue
                    vendor_path = os.path.join(dev_dir, "idVendor")
                    try:
                        with open(vendor_path, "r", encoding="utf-8") as f_ven:
                            if (
                                f_ven.read().strip().lower()
                                not in self._UNIGRAF_USB_VENDOR_IDS
                            ):
                                continue
                    except OSError:
                        pass

                    attempted_dirs.add(dev_dir)
                    if self._reset_usb_dev_dir(
                        dev_dir, f"serial {serial_number}", settle_delay_sec
                    ):
                        return True
                except OSError as e:
                    logging.debug(
                        "Transient error reading sysfs serial %s: %s",
                        sys_path,
                        e,
                    )

        target_model = self._device_name.replace("-", "").lower()
        for sys_path in glob.glob("/sys/bus/usb/devices/*/idVendor"):
            try:
                dev_dir = self._resolve_usb_dev_dir(sys_path)
                if dev_dir in attempted_dirs:
                    continue
                vendor_path = os.path.join(dev_dir, "idVendor")
                with open(vendor_path, "r", encoding="utf-8") as f_ven:
                    if (
                        f_ven.read().strip().lower()
                        not in self._UNIGRAF_USB_VENDOR_IDS
                    ):
                        continue

                if serial_number:
                    serial_path = os.path.join(dev_dir, "serial")
                    try:
                        with open(serial_path, "r", encoding="utf-8") as f_ser:
                            dev_serial = f_ser.read().strip()
                        if (
                            dev_serial
                            and dev_serial.upper()
                            != serial_number.strip().upper()
                        ):
                            continue
                    except OSError:
                        pass

                product_path = os.path.join(dev_dir, "product")
                product = ""
                try:
                    with open(product_path, "r", encoding="utf-8") as f_prod:
                        product = f_prod.read().strip()
                except OSError:
                    pass

                if product:
                    if target_model not in product.replace("-", "").lower():
                        continue
                elif not serial_number:
                    continue

                attempted_dirs.add(dev_dir)
                if self._reset_usb_dev_dir(
                    dev_dir, f"Unigraf {self._device_name}", settle_delay_sec
                ):
                    return True
            except OSError as e:
                logging.debug(
                    "Transient error reading sysfs idVendor %s: %s",
                    sys_path,
                    e,
                )

        if serial_number:
            logging.warning(
                "Failed to locate/reset USB device node for serial %s",
                serial_number,
            )
        else:
            logging.debug(
                "No matching %s USB device node found to reset",
                self._device_name,
            )
        return False

    def _scan_sysfs_matching_serials(self) -> list[str]:
        """Scans sysfs USB devices for matching Unigraf model serials."""
        target_model = self._device_name.replace("-", "").lower()
        serials: list[str] = []
        seen_dirs: set[str] = set()
        for sys_path in glob.glob("/sys/bus/usb/devices/*/idVendor"):
            try:
                dev_dir = self._resolve_usb_dev_dir(sys_path)
                if dev_dir in seen_dirs:
                    continue
                seen_dirs.add(dev_dir)
                vendor_path = os.path.join(dev_dir, "idVendor")
                with open(vendor_path, "r", encoding="utf-8") as f_ven:
                    if (
                        f_ven.read().strip().lower()
                        not in self._UNIGRAF_USB_VENDOR_IDS
                    ):
                        continue
                product_path = os.path.join(dev_dir, "product")
                with open(product_path, "r", encoding="utf-8") as f_prod:
                    product = f_prod.read().strip()
                if (
                    not product
                    or target_model not in product.replace("-", "").lower()
                ):
                    continue
                serial_path = os.path.join(dev_dir, "serial")
                with open(serial_path, "r", encoding="utf-8") as f_ser:
                    dev_serial = f_ser.read().strip().upper()
                if dev_serial and dev_serial not in serials:
                    serials.append(dev_serial)
            except OSError:
                continue
        return serials

    def _hard_reset_and_reopen(self, serial: str) -> None:
        """Executes in-band NIOS reset, bounces USB, and polls until reopen."""
        if self._dev is not None:
            try:
                logging.info(
                    "Attempting SDK-level hardware reset for UCD %s", serial
                )
                self._reset_device_io()
                # Always wait after TSI_DEVICE_HW_RESET before issuing
                # USBDEVFS_RESET so we never interrupt FPGA reconfiguration.
                time.sleep(self._HW_RESET_INITIAL_WAIT_SEC)
            except Exception as e:  # pylint: disable=broad-except
                logging.warning(
                    "Clean SDK reset failed on %s (%s); continuing to USB"
                    " bounce",
                    serial,
                    e,
                )
        self._close_device()
        self._force_usb_reenumeration(serial)
        self._reopen_after_reset(serial)

    def _reopen_after_reset(
        self,
        serial_number: str,
        max_attempts: int | None = None,
        poll_interval_sec: float | None = None,
    ) -> None:
        """Polls libTSI rescan + open until the UCD is ready with roles."""
        if max_attempts is None:
            max_attempts = self._POWER_CYCLE_MAX_POLL_ATTEMPTS
        if poll_interval_sec is None:
            poll_interval_sec = self._POWER_CYCLE_POLL_INTERVAL_SEC

        last_err = None
        for attempt in range(max_attempts):
            if poll_interval_sec > 0:
                time.sleep(poll_interval_sec)
            try:
                self._open_device(serial_number)
                if not self._has_populated_role_list():
                    self._close_device()
                    raise RuntimeError(
                        f"UCD {serial_number} opened with empty role list"
                        " while booting"
                    )
                logging.info(
                    "Successfully reconnected to UCD %s on poll attempt %d/%d",
                    serial_number,
                    attempt + 1,
                    max_attempts,
                )
                return
            except Exception as e:  # pylint: disable=broad-except
                last_err = e
                self._close_device()
                logging.warning(
                    "Reconnection poll %d/%d for UCD %s not ready (%s)...",
                    attempt + 1,
                    max_attempts,
                    serial_number,
                    e,
                )

        logging.error(
            "Failed all %d poll attempts to resurrect UCD %s: %s",
            max_attempts,
            serial_number,
            last_err,
        )
        raise RuntimeError(
            f"UCD {serial_number} failed to return after USB bounce"
        ) from last_err

    def _select_role(self, role_to_set):
        """Selects the UCD role using a 3-tier recovery state machine.

        Attempt 1: Fast path (in-place PD/FX3 recovery).
        Attempt 2: Soft recovery (FX3 flush, close, libTSI rescan, reopen).
        Attempt 3: Hard recovery (NIOS reset, close, USBDEVFS_RESET, rescan,
                   and polled reopen until roles are populated).

        Args:
            role_to_set: The UniTAP role class to select on the open device.

        Raises:
            Exception: If role selection fails across all recovery tiers.
        """
        for attempt in range(self._ROLE_SELECT_RETRIES + 1):
            last_ux_only_benign = False
            try:
                if self._role is not None:
                    # Unigraf's C++ libTSI.so aborts via std::terminate() if
                    # TSIX_DEV_SelectRole is called a second time on the same
                    # TSI_HANDLE, so we must close and reopen a fresh handle.
                    self._close_device()
                if self._dev is None:
                    self._open_device(self._serial)

                if not self._has_populated_role_list():
                    raise UniTAP.dev.device.NotExistingRoleSelected(
                        f"UCD {self._serial} has empty role list (firmware"
                        " still booting)"
                    )

                self._role = self._dev.select_role(role_to_set)
                fw_info = self._get_fw_info()
                corrupted = self._get_corrupted_fw_components(
                    fw_info, self._role
                )
                if corrupted:
                    fw_info, corrupted = self._recover_corrupted_fw_in_place(
                        fw_info, corrupted
                    )

                if corrupted:
                    last_ux_only_benign = self._is_benign_ux_only_corruption(
                        fw_info, self._role
                    )
                    if (
                        attempt == self._ROLE_SELECT_RETRIES
                        and last_ux_only_benign
                    ):
                        logging.warning(
                            "Proceeding despite UX: 0.0.0 after %d attempts"
                            " because FPGA and PD firmware are healthy: %s",
                            self._ROLE_SELECT_RETRIES + 1,
                            fw_info,
                        )
                        return
                    raise RuntimeError(
                        f"Corrupted UCD firmware version detected: {fw_info}"
                    )
                return
            except Exception as e:  # pylint: disable=broad-except
                if attempt == self._ROLE_SELECT_RETRIES:
                    raise
                if attempt == 0 or last_ux_only_benign:
                    logging.warning(
                        "UCD role selection attempt %d/%d failed (%s);"
                        " reopening device %s (Tier 2 soft recovery).",
                        attempt + 1,
                        self._ROLE_SELECT_RETRIES + 1,
                        e,
                        self._serial,
                    )
                    if self._dev is not None and not last_ux_only_benign:
                        self._flush_fx3()
                    self._close_device()
                else:
                    logging.warning(
                        "UCD role selection attempt %d/%d failed (%s);"
                        " escalating to NIOS reset and USB bounce on %s"
                        " (Tier 3 hard recovery).",
                        attempt + 1,
                        self._ROLE_SELECT_RETRIES + 1,
                        e,
                        self._serial,
                    )
                    self._hard_reset_and_reopen(self._serial)

    def _activate_role(self, role_to_set) -> None:
        """Selects the role with device quirks and verifies capturer."""
        self._last_requested_role = role_to_set
        self._role_set_quirks(role_to_set)
        # HDCP is off by default: with link encryption active the UCD masks
        # captured frames with solid blue RGB(0,0,255) (HDCP license rule).
        # Tests that verify protected content opt in via
        # SetLinkVideoTesterRequest.hdcp_capable.
        self._set_hdcp_rx_capable(False)
        self._ensure_video_capturer_idle()

    def _set_hdcp_rx_capable(self, capable: bool) -> None:
        """Sets HDCP 1.x and 2.x sink capability on the receiver port.

        Takes effect on the DUT's next HDCP authentication (i.e. next hotplug).
        Disabling is best effort so it never breaks role selection or link
        setup; enabling raises, as an HDCP test can't run without it.
        """
        if self._port_rx is None:
            return
        try:
            for cfg_cls in (
                UniTAP.HdcpRxConfig.Config1x,
                UniTAP.HdcpRxConfig.Config2x,
            ):
                cfg = cfg_cls()
                cfg.capable = capable
                self._port_rx.hdcp.config.set(cfg)
        except Exception as e:  # pylint: disable=broad-except
            if capable:
                raise
            logging.warning(
                "Failed to disable HDCP sink capability on UCD: %s", e
            )
            return
        logging.info("Set HDCP sink capability on UCD RX port to %s.", capable)

    # =========== Common gRPC Methods ===========
    def _scan_matching_testers(
        self, context=None
    ) -> list[video_pb2.VideoTester]:
        """Scans libTSI available devices and returns matching VideoTesters."""
        testers = self._tsilib.get_list_of_available_devices()
        ret = []
        # Output of `get_list_of_available_devices` is of the form
        # ['0: UCD-abc [xxxxxxx]', '1: UCD-abc [yyyyyyy]']
        # where the number between the square brackets is the device serial.
        for tester in testers:
            if self._device_name.upper() not in tester.upper():
                continue

            serials = re.findall(r"\[([^]]*)\]", tester)
            if len(serials) != 1:
                logging.error("Serial parsing is malformed %s", tester)
                if context is not None:
                    context.set_code(grpc.StatusCode.INTERNAL)
                    context.set_details("Serial parsing is malformed")
                raise RuntimeError("Serial parsing is malformed!")

            ret.append(
                video_pb2.VideoTester(
                    id=serials[0],
                    name=self._device_name.upper(),
                )
            )

        return ret

    @synchronized
    @log_functionality.logger
    def GetVideoTesters(self, _, context):
        """Retrieves a list of available video testers."""
        if self._dev is None:
            self._rescan_devices()
        testers = self._scan_matching_testers(context)
        if not testers and self._dev is None:
            for serial in self._scan_sysfs_matching_serials():
                logging.warning(
                    "libTSI returned 0 %s testers; falling back to"
                    " read-only sysfs USB serial %s so OpenVideoTester"
                    " can run targeted recovery.",
                    self._device_name,
                    serial,
                )
                testers.append(
                    video_pb2.VideoTester(
                        id=serial,
                        name=self._device_name.upper(),
                    )
                )
        if (
            self._dev is not None
            and self._serial
            and all(t.id != self._serial for t in testers)
        ):
            testers.append(
                video_pb2.VideoTester(
                    id=self._serial,
                    name=self._device_name.upper(),
                )
            )
        return video_pb2.GetVideoTestersResponse(testers=testers)

    @synchronized
    @log_functionality.logger
    def SetRoleVideoTester(self, request, _):
        """Selects a specific role for a given video tester."""
        self._check_serial_active(request.id)

        if request.role not in translate.UCD_ROLES:
            raise RuntimeError(f"Role is unknown {request.role}")

        self._activate_role(translate.UCD_ROLES[request.role])
        return video_pb2.SetRoleResponse(success=True)

    @synchronized
    @log_functionality.logger
    def OpenVideoTester(self, request, context):
        """Opens a specific video tester for interaction."""
        if self._dev is not None:
            logging.warning(
                "Tester %s was left open; closing stale handle before"
                " reopening.",
                self._serial,
            )
            self._close_device()
        self._serial = None
        self._last_requested_role = None

        try:
            try:
                self._open_device(request.id)
                if not self._has_populated_role_list():
                    raise RuntimeError(
                        f"UCD {request.id} opened with empty role list"
                    )
            except Exception as first_err:  # pylint: disable=broad-except
                logging.warning(
                    "Initial OpenVideoTester('%s') failed or returned empty"
                    " role list (%s); running hard reset and reopen.",
                    request.id,
                    first_err,
                )
                self._hard_reset_and_reopen(request.id)
        except Exception as e:
            context.set_code(grpc.StatusCode.INTERNAL)
            raise RuntimeError(f"Failed to open device: {e}") from e

        self._serial = request.id

        return video_pb2.OpenVideoTesterResponse(success=True)

    @synchronized
    @log_functionality.logger
    def CloseVideoTester(self, request, _):
        """Closes an opened video tester."""
        if self._dev is None:
            logging.debug("Serial '%s' is already closed", request.id)
            self._serial = None
            self._last_requested_role = None
            return video_pb2.CloseVideoTesterResponse(success=True)

        if request.id and self._serial and request.id != self._serial:
            raise RuntimeError(
                f"Serial '{request.id}' is not the active device"
                f" '{self._serial}'"
            )

        self._close_device()
        self._serial = None
        self._last_requested_role = None

        return video_pb2.CloseVideoTesterResponse(success=True)

    @synchronized
    def RunComplianceTest(self, request, _):
        """Runs compliance test(s) for a given group and returns all results."""
        self._check_serial_active(request.id)

        # Validate that all test groups exist so that we fail early.
        for test in request.tests:
            if test.group_id not in translate.TEST_GROUPS:
                raise RuntimeError(f"Test group is unknown {test.group_id}")

        self._role.dut_tests.clear_results()
        for test in request.tests:
            test_group = translate.TEST_GROUPS[test.group_id]

            test_params = self._role.dut_tests.get_default_parameters(
                test_group["default_param_class"]
            )
            if request.platform in test_group:
                platform_params = test_group[request.platform]
                for key, val in platform_params["default"].items():
                    rsetattr(test_params, key, val)
                if request.model in platform_params:
                    for key, val in platform_params[request.model].items():
                        rsetattr(test_params, key, val)

            self._role.dut_tests.run(
                test_group["group_id"],
                test.test_id,
                test_params,
            )

        i = 0
        results_array = []
        results = self._role.dut_tests.get_all_tests_results()
        for result in results.all_test_results():
            logging.info(
                "Ran test %s with result %s",
                result.test_name,
                result.test_result,
            )

            result_obj = video_pb2.ComplianceTestResultVideoTester(
                test=request.tests[i],
                status=translate.TEST_UNITAP_TO_GRPC[result.test_result],
            )
            results_array.append(result_obj)
            i = i + 1

        # make_report automatically appends .html to the filename passed to it.
        with temp_file_path(extra_suffixes=(".html",)) as tmp_base:
            self._role.dut_tests.make_report(tmp_base, tested_by="Passport")
            with open(f"{tmp_base}.html", "rb") as f:
                results_html = f.read()

        return video_pb2.RunComplianceTestResponse(
            results=results_array, results_html=results_html
        )

    @synchronized
    @log_functionality.logger
    def LoadEdidVideoTester(self, request, _):
        """Loads the provided EDID data onto a given video tester."""
        self._check_serial_active(request.id)

        with temp_file_path(suffix=".bin") as tmp_path:
            with open(tmp_path, "wb") as f:
                f.write(request.edid)

            logging.info("Temp file name was %s", tmp_path)
            ret = self._port_rx.edid.load_edid(
                path=tmp_path, load_on_device=True, stream=request.id_stream
            )

        return video_pb2.LoadEdidVideoTesterResponse(success=len(ret) != 0)

    @staticmethod
    def _frame_to_bmp(frame) -> bytes:
        """Encodes a captured frame as BMP bytes.

        Pure host-side work on an already captured frame: it never touches the
        device, so callers must not hold the UCD lock while it runs.

        Args:
            frame: UniTAP VideoFrame or VideoFrameDSC popped by the capturer.

        Returns:
            Raw BMP image bytes written by UniTAP.

        Raises:
            RuntimeError: If the saved BMP file is empty (0 bytes).
        """
        with _ENCODE_LOCK, temp_file_path(suffix=".bmp") as tmp_path:
            logging.info("Saving image to disk")
            if isinstance(frame, UniTAP.VideoFrameDSC):
                _save_dsc_frame_as_bmp(frame, tmp_path)
            else:
                UniTAP.utils.video_frame_save_to_file(
                    frame, tmp_path, UniTAP.utils.ImageFileFormat.IFF_BMP
                )
            with open(tmp_path, "rb") as f:
                screenshot_bytes = f.read()

        if not screenshot_bytes:
            raise RuntimeError("Screenshot file was written with 0 bytes")
        return screenshot_bytes

    @staticmethod
    def _is_non_positive_number(val: Any, min_valid: int = 1) -> bool:
        """Returns True if val is a numeric (non-bool) value < min_valid."""
        return (
            isinstance(val, (int, float))
            and not isinstance(val, bool)
            and val < min_valid
        )

    @staticmethod
    def _extract_stream_metric(stream: Any, nested_obj: Any, attr: str) -> Any:
        """Reads a numeric stream metric from stream or nested_obj."""
        direct_val = getattr(stream, attr, None)
        if isinstance(direct_val, (int, float)) and not isinstance(
            direct_val, bool
        ):
            return direct_val
        nested_val = getattr(nested_obj, attr, None)
        if isinstance(nested_val, (int, float)) and not isinstance(
            nested_val, bool
        ):
            return nested_val
        return nested_val if nested_val is not None else direct_val

    def _check_dut_driving_valid_stream(
        self, stream_id: int
    ) -> tuple[bool, str]:
        """Checks whether the DUT is driving valid video on stream_id."""
        if self._port_rx is None:
            return True, ""
        try:
            if self._get_number_of_video_streams() <= 0:
                return False, "0 active streams"
        except RuntimeError:
            pass
        try:
            stream = self._port_rx.link.status.stream(stream_id)
        except ValueError as e:
            if "not available" in str(e).lower():
                return False, str(e)
            logging.debug(
                "Unable to read stream %d status before capture: %s",
                stream_id,
                e,
            )
            return True, ""
        except Exception as e:  # pylint: disable=broad-except
            logging.debug(
                "Unable to read stream %d status before capture: %s",
                stream_id,
                e,
            )
            return True, ""

        video_mode = getattr(stream, "video_mode", None)
        timing = getattr(video_mode, "timing", None)
        color_info = getattr(video_mode, "color_info", None)

        hactive = self._extract_stream_metric(stream, timing, "hactive")
        vactive = self._extract_stream_metric(stream, timing, "vactive")
        bpp = self._extract_stream_metric(stream, color_info, "bpp")
        bpc = self._extract_stream_metric(stream, color_info, "bpc")

        has_valid_bpc = (
            isinstance(bpc, (int, float))
            and not isinstance(bpc, bool)
            and bpc >= 1
        )
        invalid_color_depth = (
            self._is_non_positive_number(bpp, 1) and not has_valid_bpc
        )

        if (
            self._is_non_positive_number(hactive, 1)
            or self._is_non_positive_number(vactive, 2)
            or invalid_color_depth
        ):
            return False, f"hactive={hactive}, vactive={vactive}, bpp={bpp}"
        return True, ""

    # Do not log the request as the screenshots can get very big.
    def ScreenshotVideoTester(self, request, context):
        """Captures a screenshot from a specific stream of a video tester.

        Only the hardware capture holds the UCD lock. Encoding the frame (DSC
        decode for 8K) runs unlocked so it can never starve other RPCs, and
        no new attempt starts once the client has given up.
        """
        logging.info(
            "Running ScreenshotVideoTester for stream %d on device %s",
            request.id_stream,
            request.id,
        )
        max_attempts = self._SCREENSHOT_MAX_ATTEMPTS
        last_error = None
        for attempt in range(1, max_attempts + 1):
            if attempt > 1 and not context.is_active():
                break
            # Lock timeouts and precondition errors raise/abort directly.
            frame, last_error = self._capture_frame(request, context, attempt)
            if frame is None and last_error is None:
                return video_pb2.ScreenshotVideoTesterResponse()
            if frame is not None:
                try:
                    screenshot_bytes = self._frame_to_bmp(frame)
                    logging.info(
                        "Screenshot capture successful (%d bytes)",
                        len(screenshot_bytes),
                    )
                    return video_pb2.ScreenshotVideoTesterResponse(
                        screenshot=screenshot_bytes
                    )
                except Exception as e:  # pylint: disable=broad-except
                    last_error = e
            logging.warning(
                "Screenshot capture attempt %d/%d failed: %s",
                attempt,
                max_attempts,
                last_error,
            )

        context.set_code(grpc.StatusCode.UNAVAILABLE)
        context.set_details(
            f"Screenshot capture failed after {max_attempts} attempts:"
            f" {last_error}"
        )
        raise RuntimeError(
            f"Screenshot capture failed after {max_attempts} attempts:"
            f" {last_error}"
        )

    @synchronized
    def _capture_frame(self, request, context, attempt: int):
        """Validates preconditions and captures one frame under the UCD lock.

        Returns:
            (frame, None) on success, (None, error) on a retryable capture
            failure, or (None, None) when aborted for FAILED_PRECONDITION.
        """
        self._check_serial_active(request.id)
        if attempt == 1:
            try:
                active_streams = self._get_number_of_video_streams()
                if (
                    request.id_stream < 0
                    or 0 < active_streams <= request.id_stream
                ):
                    msg = (
                        f"Requested stream {request.id_stream} exceeds"
                        f" available streams ({active_streams})"
                    )
                    logging.error(msg)
                    context.set_code(grpc.StatusCode.INVALID_ARGUMENT)
                    context.set_details(msg)
                    raise ValueError(msg)
            except RuntimeError:
                pass

            valid, details = self._check_dut_driving_valid_stream(
                request.id_stream
            )
            if not valid:
                logging.warning(
                    "Stream %d reports inactive/unlatched video (%s); waiting"
                    " 0.5s to re-check.",
                    request.id_stream,
                    details,
                )
                time.sleep(0.5)
                valid, details = self._check_dut_driving_valid_stream(
                    request.id_stream
                )
                if not valid:
                    msg = (
                        "DUT is not driving valid video on stream"
                        f" {request.id_stream} ({details})"
                    )
                    logging.error(msg)
                    context.set_code(grpc.StatusCode.FAILED_PRECONDITION)
                    context.set_details(msg)
                    context.abort(grpc.StatusCode.FAILED_PRECONDITION, msg)
                    return None, None

        try:
            capturer = self._port_rx.video_capturer
            if attempt > 1:
                if capturer.status == UniTAP.VideoCaptureStatus.Idle:
                    self._reset_video_capturer_pipeline()
                time.sleep(self._SCREENSHOT_RETRY_DELAY_SEC)
            if (
                attempt == 1
                or capturer.status != UniTAP.VideoCaptureStatus.Idle
            ):
                self._ensure_video_capturer_idle()

            logging.info(
                "Start live video capture (attempt %d/%d)",
                attempt,
                self._SCREENSHOT_MAX_ATTEMPTS,
            )

            # Asynchronous live capture with hardware latch window.
            try:
                capturer.start(frames_count=0, stream_number=request.id_stream)
                time.sleep(self._SCREENSHOT_LATCH_DELAY_SEC)
                capturer.pop_element()
            finally:
                # Guarantee hardware capturer is stopped in all paths.
                try:
                    capturer.stop()
                except Exception:  # pylint: disable=broad-except
                    pass
                self._ensure_video_capturer_idle()
                self._resume_event_capture_if_active()

            result = capturer.capture_result
            if not result.buffer:
                raise RuntimeError(
                    "Capturer completed but returned an empty frame buffer"
                )
            # Hold the frame itself: the next capture clears result.buffer.
            return result.buffer[0], None
        except Exception as e:  # pylint: disable=broad-except
            return None, e

    @synchronized
    @log_functionality.logger
    def GetStreamInfoVideoTester(self, request, _):
        """Gets the current stream parameters for a given video tester."""
        self._check_serial_active(request.id)

        stream_num = self._get_number_of_video_streams()

        res = []
        for i in range(0, stream_num):
            try:
                stream = self._port_rx.link.status.stream(i)
            except ValueError as e:
                if "not available" in str(e).lower():
                    logging.debug(
                        "Stream %d not available in link status (%s); returning"
                        " inactive stream entry.",
                        i,
                        e,
                    )
                    res.append(video_pb2.StreamInfoVideoTester())
                    continue
                raise
            color_format = translate.SDK_COLOR_FORMAT_TO_GRPC[
                stream.video_mode.color_info.color_format
            ]
            colometry = translate.SDK_COLOMETRY_TO_GRPC[
                stream.video_mode.color_info.colorimetry
            ]
            dynamic_range = translate.SDK_DYNAMIC_RANGE_TO_GRPC[
                stream.video_mode.color_info.dynamic_range
            ]
            raw_bpp = stream.video_mode.color_info.bpp
            raw_bpc = getattr(stream.video_mode.color_info, "bpc", 0)
            if (
                self._is_non_positive_number(raw_bpp, 1)
                and isinstance(raw_bpc, int)
                and not isinstance(raw_bpc, bool)
                and raw_bpc > 0
            ):
                effective_bpp = raw_bpc * 3
            else:
                effective_bpp = raw_bpp
            stream_info = video_pb2.StreamInfoVideoTester(
                frame_rate=stream.video_mode.timing.frame_rate,
                hactive=stream.video_mode.timing.hactive,
                vactive=stream.video_mode.timing.vactive,
                htotal=stream.video_mode.timing.htotal,
                vtotal=stream.video_mode.timing.vtotal,
                hstart=stream.video_mode.timing.hstart,
                vstart=stream.video_mode.timing.vstart,
                hswidth=stream.video_mode.timing.hswidth,
                vswidth=stream.video_mode.timing.vswidth,
                bpp=effective_bpp,
                color_format=color_format,
                colormetry=colometry,
                dynamic_range=dynamic_range,
                crc=stream.crc,
            )
            res.append(stream_info)

        return video_pb2.GetStreamInfoVideoTesterResponse(streams=res)

    @synchronized
    @log_functionality.logger
    def GetRolesVideoTester(self, request, _):
        """Gets the list of supported roles."""
        self._check_serial_active(request.id)

        inv_role_map = {v: k for k, v in translate.UCD_ROLES.items()}
        ret = []
        for role in self._dev.available_roles:
            ret.append(inv_role_map[role])

        return video_pb2.GetRolesResponse(roles=ret)

    @synchronized
    def PowerCycle(self, request, context):
        """Power cycles the video tester and restores its active role."""
        del context
        request_id = getattr(request, "id", None)
        if request_id and self._serial and request_id != self._serial:
            raise RuntimeError(
                f"Serial '{request_id}' is not the active device"
                f" '{self._serial}'"
            )
        target_serial = request_id or self._serial
        if not target_serial:
            raise RuntimeError("Tester serial id is required for PowerCycle")

        was_open = self._dev is not None
        saved_role = self._last_requested_role
        if saved_role is None and self._role is not None:
            saved_role = self._role.__class__

        logging.info("PowerCycling UCD %s", target_serial)

        self._serial = None
        self._last_requested_role = None
        self._hard_reset_and_reopen(target_serial)
        if was_open:
            self._serial = target_serial
            if saved_role is not None:
                self._activate_role(saved_role)
        else:
            self._close_device()

        return video_pb2.PowerCycleResponse()

    def _check_serial_active(self, serial):
        if self._serial is None:
            raise RuntimeError(f"Tester {serial} is not open")

        if serial != self._serial:
            raise RuntimeError(
                f"Serials dont match, got {serial} expected {self._serial}"
            )

    @log_functionality.logger
    def __del__(self):
        logging.info("Delete function will ran")
        self._close_device()
        self._tsilib.cleanup()
