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

_DEFAULT_LOCK_TIMEOUT_SEC = 60.0


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
    default_timeout = getattr(
        self, "_LOCK_TIMEOUT_SEC", _DEFAULT_LOCK_TIMEOUT_SEC
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
                return context, max(0.0, float(remaining))
        except Exception:  # pylint: disable=broad-except
            pass
    return context, float(default_timeout)


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
    _TSI_CAP_CMD_STOP = 2
    _TSI_CAP_CONFIG = 0x302
    _TSI_USBC_FLUSH_BULK_PIPES_W = 0x5002C004
    _LOCK_TIMEOUT_SEC = _DEFAULT_LOCK_TIMEOUT_SEC

    @log_functionality.logger
    def __init__(self, device_name):
        self._lock = threading.RLock()
        self._dev = None
        self._serial = None
        self._role = None
        self._port_rx = None
        self._port_tx = None
        self._last_requested_role = None
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
        if not fw_info:
            return ["EMPTY"]
        corrupted = []
        for comp in self._get_active_fw_components(role):
            if re.search(rf"\b{comp}:\s*0\.0\.0(?:\.0)?\b", fw_info):
                corrupted.append(comp)
        return corrupted

    def _is_benign_ux_only_corruption(self, fw_info: str, role=None) -> bool:
        """Checks if only UX is 0.0.0 while UF and active PD are healthy."""
        if self._get_corrupted_fw_components(fw_info, role) != ["UX"]:
            return False
        for comp in self._get_active_fw_components(role):
            if comp == "UX":
                continue
            if not re.search(rf"\b{comp}:\s*\d+\.\d+\.\d+", fw_info):
                return False
        return True

    # =========== Common gRPC Methods ===========
    @synchronized
    @log_functionality.logger
    def GetVideoTesters(self, _, context):
        """Retrieves a list of available video testers."""
        self._rescan_devices()
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
                context.set_code(grpc.StatusCode.INTERNAL)
                context.set_details("Serial parsing is malformed")
                raise RuntimeError("Serial parsing is malformed!")

            ret.append(
                video_pb2.VideoTester(
                    id=serials[0],
                    name=self._device_name.upper(),
                )
            )

        return video_pb2.GetVideoTestersResponse(testers=ret)

    @synchronized
    @log_functionality.logger
    def SetRoleVideoTester(self, request, _):
        """Selects a specific role for a given video tester."""
        self._check_serial_active(request.id)

        if request.role not in translate.UCD_ROLES:
            raise RuntimeError(f"Role is unknown {request.role}")

        self._last_requested_role = translate.UCD_ROLES[request.role]
        self._role_set_quirks(self._last_requested_role)
        self._ensure_video_capturer_idle()
        fw_info = self._get_fw_info()
        corrupted = self._get_corrupted_fw_components(fw_info, self._role)
        if corrupted and not self._is_benign_ux_only_corruption(
            fw_info, self._role
        ):
            raise RuntimeError(
                f"Corrupted UCD firmware version detected: {fw_info}"
            )

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
            self._open_device(request.id)
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

    def _save_capture_bmp(self, result) -> bytes:
        """Saves the first frame of a video capture result to BMP bytes.

        Uses temp_file_path with deterministic finally unlink cleanup so
        failed DSC decodes inside save_image_to_file never leak /tmp files.

        Args:
            result: UniTAP video capture result object containing frames.

        Returns:
            Raw BMP image bytes written by UniTAP.

        Raises:
            RuntimeError: If the saved BMP file is empty (0 bytes).
        """
        with temp_file_path(suffix=".bmp") as tmp_path:
            logging.info("Saving image to disk")
            result.save_image_to_file(
                file_format=UniTAP.PictureFileFormat.BMP,
                path=tmp_path,
                index=0,
            )
            with open(tmp_path, "rb") as f:
                screenshot_bytes = f.read()

        if not screenshot_bytes:
            raise RuntimeError("Screenshot file was written with 0 bytes")
        return screenshot_bytes

    # Do not log the request as the screenshots can get very big.
    @synchronized
    def ScreenshotVideoTester(self, request, context):
        """Captures a screenshot from a specific stream of a video tester."""
        logging.info(
            "Running ScreenshotVideoTester for stream %d on device %s",
            request.id_stream,
            request.id,
        )
        self._check_serial_active(request.id)

        # Validate stream index against active hardware streams if supported.
        try:
            active_streams = self._get_number_of_video_streams()
            if request.id_stream >= active_streams:
                msg = (
                    f"Requested stream {request.id_stream} exceeds available "
                    f"streams ({active_streams})"
                )
                logging.error(msg)
                context.set_code(grpc.StatusCode.INVALID_ARGUMENT)
                context.set_details(msg)
                raise ValueError(msg)
        except RuntimeError:
            pass

        max_attempts = 3
        frame_latch_delay_sec = 0.5
        last_error = None

        for attempt in range(1, max_attempts + 1):
            try:
                # Reset any stuck capturer state from previous runs
                self._ensure_video_capturer_idle()

                logging.info(
                    "Start live video capture (attempt %d/%d)",
                    attempt,
                    max_attempts,
                )

                # Asynchronous live capture with hardware latch window
                try:
                    self._port_rx.video_capturer.start(
                        frames_count=0,
                        stream_number=request.id_stream,
                    )
                    time.sleep(frame_latch_delay_sec)
                    self._port_rx.video_capturer.pop_element()
                finally:
                    # Guarantee hardware capturer is stopped in all paths
                    try:
                        self._port_rx.video_capturer.stop()
                    except Exception:  # pylint: disable=broad-except
                        pass
                    self._ensure_video_capturer_idle()

                result = self._port_rx.video_capturer.capture_result
                if not result.buffer:
                    raise RuntimeError(
                        "Capturer completed but returned an empty frame buffer"
                    )

                screenshot_bytes = self._save_capture_bmp(result)

                logging.info(
                    "Screenshot capture successful (%d bytes)",
                    len(screenshot_bytes),
                )
                return video_pb2.ScreenshotVideoTesterResponse(
                    screenshot=screenshot_bytes
                )

            except Exception as e:  # pylint: disable=broad-except
                logging.warning(
                    "Screenshot capture attempt %d/%d failed: %s",
                    attempt,
                    max_attempts,
                    e,
                )
                last_error = e
                if attempt < max_attempts:
                    self._reset_video_capturer_pipeline()
                    time.sleep(0.5)

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
    @log_functionality.logger
    def GetStreamInfoVideoTester(self, request, _):
        """Gets the current stream parameters for a given video tester."""
        self._check_serial_active(request.id)

        stream_num = self._get_number_of_video_streams()

        res = []
        for i in range(0, stream_num):
            stream = self._port_rx.link.status.stream(i)
            color_format = translate.SDK_COLOR_FORMAT_TO_GRPC[
                stream.video_mode.color_info.color_format
            ]
            colometry = translate.SDK_COLOMETRY_TO_GRPC[
                stream.video_mode.color_info.colorimetry
            ]
            dynamic_range = translate.SDK_DYNAMIC_RANGE_TO_GRPC[
                stream.video_mode.color_info.dynamic_range
            ]
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
                bpp=stream.video_mode.color_info.bpp,
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

    @log_functionality.logger
    def _force_usb_reenumeration(self, serial_number):
        """Issues a USBDEVFS_RESET ioctl directly to the device node block.

        This does not require write privileges to /sys (which is often mounted
        read-only in containers) - it only requires write access to the specific
        character device (e.g., /dev/bus/usb/XXX/YYY) which Docker strictly
        permits via cgroups. It drops all lingering handles, unbinds the driver,
        bounces the hardware, and re-enumerates it in place without altering the
        devnum.
        """
        for sys_path in glob.glob("/sys/bus/usb/devices/*/serial"):
            try:
                with open(sys_path, "r", encoding="utf-8") as f:
                    if f.read().strip() == serial_number:
                        dev_dir = os.path.dirname(sys_path)
                        bus_path = os.path.join(dev_dir, "busnum")
                        dev_num_path = os.path.join(dev_dir, "devnum")
                        with (
                            open(bus_path, "r", encoding="utf-8") as f_bus,
                            open(dev_num_path, "r", encoding="utf-8") as f_dev,
                        ):
                            busnum = int(f_bus.read().strip())
                            devnum = int(f_dev.read().strip())

                        dev_path = f"/dev/bus/usb/{busnum:03d}/{devnum:03d}"
                        logging.info(
                            "Hardware resetting USB node %s for serial %s"
                            " using ioctl",
                            dev_path,
                            serial_number,
                        )

                        usbdevfs_reset = 21780
                        fd = os.open(dev_path, os.O_WRONLY)
                        try:
                            fcntl.ioctl(fd, usbdevfs_reset, 0)
                        finally:
                            os.close(fd)

                        # Wait for physical USB hub reset and device boot.
                        time.sleep(20)
                        return True
            except OSError as e:
                logging.debug(
                    "Transient error opening USB ioctl path for %s: %s",
                    sys_path,
                    e,
                )

        logging.warning(
            "Failed to locate/reset USB device node for serial %s",
            serial_number,
        )
        return False

    @synchronized
    def PowerCycle(self, request, context):
        """Power cycles the video tester."""
        del context
        logging.info("PowerCycling UCD %s", request.id)

        try:
            logging.info("Attempting SDK-level reset for UCD %s", request.id)
            self._reset_device_io()
            time.sleep(constants.UCD_HW_RESET_TIMEOUT_S)
        except Exception:  # pylint: disable=broad-except
            logging.exception(
                "Clean SDK reset failed; continuing to forced bounce"
            )

        self._close_device()

        # Bruteforce hardware re-enumeration to clear any dead handles
        self._force_usb_reenumeration(request.id)

        # Reconnect with exponential backoff to allow udev and libusb to settle
        max_retries = 5
        base_delay_s = 2

        for attempt in range(max_retries):
            delay = base_delay_s * (2**attempt)
            time.sleep(delay)
            try:
                self._open_device(request.id)
                logging.info(
                    "Successfully reconnected to UCD %s on attempt %d",
                    request.id,
                    attempt + 1,
                )
                break
            except Exception as e:  # pylint: disable=broad-except
                if attempt == max_retries - 1:
                    logging.exception(
                        "Failed all retry attempts to resurrect UCD %s",
                        request.id,
                    )
                    raise RuntimeError(
                        f"UCD {request.id} failed to return after USB bounce"
                    ) from e
                logging.warning(
                    "Reconnection attempt %d failed, retrying in %ds...",
                    attempt + 1,
                    base_delay_s * (2 ** (attempt + 1)),
                )

        if self._last_requested_role:
            self._role_set_quirks(self._last_requested_role)

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
