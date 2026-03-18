# Copyright 2025 The ChromiumOS Authors
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

"""Provides a gRPC server to control Unigraf video testing hardware.

This module implements the VideoTesterService gRPC service, allowing clients
to discover, open, close, and configure Unigraf UCD-500 series video testers
using the UniTAP library.
"""

import atexit
import functools
import logging
import re
import tempfile
import time

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


def rsetattr(obj, attr, val):
    pre, _, post = attr.rpartition(".")
    return setattr(rgetattr(obj, pre) if pre else obj, post, val)


def rgetattr(obj, attr, *args):
    def _getattr(obj, attr):
        return getattr(obj, attr, *args)

    return functools.reduce(_getattr, [obj] + attr.split("."))


class UcdServer(video_pb2_grpc.VideoTesterServiceServicer):
    """Implements some functionality common to all of the unigraf video testers.

    Methods that need specialization:
    - SetRoleVideoTester
    - SetLinkVideoTester
    - GetLinkVideoTester
    - HpdPulseVideoTester
    - AttachVideoTester
    - _get_number_of_video_streams
    - _role_set_quirks
    """

    @log_functionality.logger
    def __init__(self, device_name):
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
        """Get the current advanced link parameters."""
        raise NotImplementedError("Method not implemented!")

    def HpdPulseVideoTester(self, request, context):
        """Send an HPD (Hot Plug Detect) pulse to a video tester."""
        raise NotImplementedError("Method not implemented!")

    def AttachVideoTester(self, request, context):
        """Simulates attaching/detaching."""
        raise NotImplementedError("Method not implemented!")

    def StartEventCapture(self, request, context):
        """Start the event capture with the specified filters"""
        raise NotImplementedError("Method not implemented!")

    def StopEventCapture(self, request, context):
        """Stop the event capture and optionally get the capture files."""
        raise NotImplementedError("Method not implemented!")

    def _get_number_of_video_streams(self):
        raise RuntimeError("Method is not implemented!")

    def _role_set_quirks(self, role_to_set):
        raise RuntimeError("Method is not implemented!")

    # =========== Common methods ===========
    @log_functionality.logger
    def GetVideoTesters(self, _, context):
        """Retrieves a list of available video testers."""

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

    @log_functionality.logger
    def SetRoleVideoTester(self, request, _):
        """Selects a specific role for a given video tester."""

        if request.id != self._serial:
            raise RuntimeError(
                f"Serials dont match, got {request.id} expected {self._serial}"
            )

        if request.role not in translate.UCD_ROLES:
            raise RuntimeError(f"Role is unknown {request.role}")

        self._last_requested_role = translate.UCD_ROLES[request.role]
        self._role_set_quirks(self._last_requested_role)

        return video_pb2.SetRoleResponse(success=True)

    @log_functionality.logger
    def OpenVideoTester(self, request, context):
        """Opens a specific video tester for interaction."""

        try:
            self._dev = self._tsilib.open(request.id)
        except Exception as e:
            context.set_code(grpc.StatusCode.INTERNAL)
            raise RuntimeError(f"Failed to open device: {e}")

        self._serial = request.id

        return video_pb2.OpenVideoTesterResponse(success=True)

    @log_functionality.logger
    def CloseVideoTester(self, request, _):
        """Closes an opened video tester."""

        if request.id != self._serial:
            raise RuntimeError(
                f"Serials dont match, got {request.id} expected {self._serial}"
            )

        if self._dev is None:
            raise RuntimeError(f"Serial {request.id} was never open")

        self._tsilib.close(self._dev)

        return video_pb2.CloseVideoTesterResponse(success=True)

    def RunComplianceTest(self, request, _):
        """Runs compliance test(s) for a given group and returns all results."""
        self._check_serial_active(request.id)

        # Validate that all test groups exist so that we fail early.
        for test in request.tests:
            if test.group_id not in translate.TEST_GROUPS:
                raise RuntimeError(f"Test group is unknown {request.group_id}")

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

        # pylint: disable=R1732
        tmp = tempfile.NamedTemporaryFile()
        # pylint: enable=R1732

        # This automatically appends .html to the filename passed to it.
        self._role.dut_tests.make_report(tmp.name, tested_by="Passport")

        with open(f"{tmp.name}.html", "rb") as f:
            return video_pb2.RunComplianceTestResponse(
                results=results_array, results_html=f.read()
            )

    @log_functionality.logger
    def LoadEdidVideoTester(self, request, _):
        """Loads the provided EDID data onto a given video tester."""

        self._check_serial_active(request.id)

        # pylint: disable=R1732
        tmp = tempfile.NamedTemporaryFile(suffix=".bin")
        # pylint: enable=R1732

        # Open the file for writing.
        with open(tmp.name, "wb") as f:
            f.write(request.edid)

        logging.info("Temp file name was %s", tmp.name)
        ret = self._port_rx.edid.load_edid(
            path=tmp.name, load_on_device=True, stream=request.id_stream
        )

        return video_pb2.LoadEdidVideoTesterResponse(success=len(ret) != 0)

    # Do not log the request as the screenshots can get very big.
    def ScreenshotVideoTester(self, request, _):
        """Captures a screenshot from a specific stream of a video tester."""

        logging.info("Running ScreenshotVideoTester with args: %s", request)
        self._check_serial_active(request.id)

        # Check current status and handle firmware bug where device gets stuck
        current_status = self._port_rx.video_capturer.status
        if current_status != UniTAP.VideoCaptureStatus.Idle:
            logging.warning(
                "Video capturer is not idle (status: %s), attempting to reset",
                current_status,
            )

            # Force stop to clear any stuck state (firmware bug workaround)
            try:
                self._port_rx.video_capturer.stop()
                logging.info("Forced stop completed")
                time.sleep(0.2)

                # Check status after forced stop
                new_status = self._port_rx.video_capturer.status
                logging.info("Status after forced stop: %s", new_status)

            except Exception as e:
                logging.warning("Forced stop failed: %s, proceeding anyway", e)
                raise RuntimeError(f"Forced stop failed: {e}")

        logging.info("Start video capture")
        self._port_rx.video_capturer.start(
            frames_count=1,
            stream_number=request.id_stream,
        )
        logging.info("Stop video capture")
        self._port_rx.video_capturer.stop()
        result = self._port_rx.video_capturer.capture_result

        # pylint: disable=R1732
        tmp = tempfile.NamedTemporaryFile(suffix=".bmp")
        # pylint: enable=R1732

        logging.info("Saving image to disk")
        result.save_image_to_file(
            file_format=UniTAP.PictureFileFormat.BMP,
            path=tmp.name,
            index=0,
        )

        with open(tmp.name, "rb") as f:
            logging.info("Sending screenshot")
            return video_pb2.ScreenshotVideoTesterResponse(screenshot=f.read())

    @log_functionality.logger
    def GetStreamInfoVideoTester(self, request, _):
        """Get the current advanced link parameters for a given video tester."""

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
    def PowerCycle(self, request, context):
        """Power cycle the video tester."""

        self._dev.reset()
        # We need to sleep while the reset is taking place, the expected time
        # for this operation is 20 seconds, we sleep 30 to have some leeway.
        time.sleep(constants.UCD_HW_RESET_TIMEOUT_S)
        self._dev.close()

        # Reopen the device and set the same role
        self._dev = self._tsilib.open(request.id)
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
        if self._dev is not None:
            self._tsilib.close(self._dev)
        self._tsilib.cleanup()
