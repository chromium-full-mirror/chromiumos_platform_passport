# Copyright 2025 The ChromiumOS Authors
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

"""Provides a gRPC server to control Unigraf video testing hardware.

This module implements the VideoTesterService gRPC service, allowing clients
to discover, open, close, and configure Unigraf UCD-500 series video testers
using the UniTAP library.
"""

import atexit
import logging
import re
import tempfile

# pylint: disable=import-error
from chromiumos.test.lab.api.passport import (
    video_tester_service_pb2 as video_pb2,
)
from chromiumos.test.lab.api.passport import (
    video_tester_service_pb2_grpc as video_pb2_grpc,
)
import grpc
import UniTAP

from utils import log_functionality


# pylint: enable=import-error


class UnigrafServer(video_pb2_grpc.VideoTesterServiceServicer):
    """Implements the gRPC service for controlling Unigraf video testers.

    This class provides methods to discover, open, close, and configure
    Unigraf UCD-500 series video testing devices. It uses the UniTAP library
    to interact with the hardware.
    """

    @log_functionality.logger
    def __init__(self):
        self._dev = None
        self._serial = None
        self._role = None

        self._tsilib = UniTAP.TsiLib()
        atexit.register(self.__del__)

        logging.info("VideoTesterServiceServicer init done")

    @log_functionality.logger
    def GetVideoTesters(self, _, context):
        """Retrieves a list of available video testers."""

        testers = self._tsilib.get_list_of_available_devices()
        ret = []
        # Output of `get_list_of_available_devices` is of the form
        # ['0: UCD-500 [xxxxxxx]', '1: UCD-500 [xxxxx]']
        # where the number between the square brackets is the device serial.
        for tester in testers:
            serials = re.findall(r"\[([^]]*)\]", tester)
            if len(serials) != 1:
                logging.error("Serial parsing is malformed %s", tester)
                context.set_code(grpc.StatusCode.INTERNAL)
                context.set_details("Serial parsing is malformed")
                raise RuntimeError("Serial parsing is malformed!")

            ret.append(
                video_pb2.VideoTester(
                    id=serials[0],
                    name="UCD-500",
                )
            )

        return video_pb2.GetVideoTestersResponse(testers=ret)

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

    @log_functionality.logger
    def SetRoleVideoTester(self, request, _):
        """Selects a specific role for a given video tester."""

        if request.id != self._serial:
            raise RuntimeError(
                f"Serials dont match, got {request.id} expected {self._serial}"
            )

        roles = {
            video_pb2.ROLE_DPSOURCE_USBCSINK: UniTAP.dev.UCD500.DPSourceUSBCSink,
            video_pb2.ROLE_DPSOURCE_DPSINK: UniTAP.dev.UCD500.DPSourceDPSink,
            video_pb2.ROLE_USBCSOURCE_USBCSINK: UniTAP.dev.UCD500.USBCSourceUSBCSink,
            video_pb2.ROLE_USBCSOURCE_DPSINK: UniTAP.dev.UCD500.USBCSourceDPSink,
        }

        if request.role not in roles:
            raise RuntimeError(f"Role is unknwon {request.role}")

        self._role = self._dev.select_role(roles[request.role])
        self._dev.opf_handler = UniTAP.OpfHandlerInternal(
            port_tx=self._role.dptx,
            port_rx=self._role.dprx,
        )
        logging.info("Role was selected successfully.")

        if isinstance(self._role, UniTAP.dev.UCD500.USBCSourceUSBCSink):
            logging.info("Set USB-PD to UFP.")
            self._role.pdcrx.capabilities.set_initial_role(
                UniTAP.pdc.PdcDeviceRole.UFP
            )
            self._role.pdcrx.controls.reconnect()

        return video_pb2.SetRoleResponse(success=True)

    @log_functionality.logger
    def LoadEdidVideoTester(self, request, context):
        """Loads the provided EDID data onto a given video tester."""

        self._check_serial_active(request.id)

        # pylint: disable=R1732
        tmp = tempfile.NamedTemporaryFile(suffix=".bin")
        # pylint: enable=R1732

        # Open the file for writing.
        with open(tmp.name, "wb") as f:
            f.write(request.edid)

        logging.info("Temp file name was %s", tmp.name)
        ret = self._role.dprx.edid.load_edid(
            path=tmp.name, load_on_device=True, stream=request.id_stream
        )

        return video_pb2.LoadEdidVideoTesterResponse(success=(len(ret) != 0))

    @log_functionality.logger
    def SetLinkVideoTester(self, request, context):
        """Sets advanced link parameters for a given video tester."""
        self._check_serial_active(request.id)
        caps = self._role.dprx.link.capabilities.link_caps_status()

        if request.HasField("mst"):
            caps.mst = request.mst
            if (
                request.HasField("mst_sink_count")
                and request.mst_sink_count != 0
            ):
                if request.mst is False:
                    raise RuntimeError(
                        "Mst is disabled but sink count was provided"
                    )
                caps.mst_sink_count = request.mst_sink_count

        if request.HasField("max_lane"):
            caps.max_lane = request.max_lane

        self._role.dprx.link.capabilities.set(caps)

        return video_pb2.SetLinkVideoTesterResponse()

    # Do not log the request as the screenshots can get very big.
    def ScreenshotVideoTester(self, request, context):
        """Captures a screenshot from a specific stream of a video tester."""

        logging.info("Running ScreenshotVideoTester with args: %s", request)
        self._check_serial_active(request.id)

        self._role.dprx.video_capturer.start(
            frames_count=1,
            stream_number=request.id_stream,
        )
        self._role.dprx.video_capturer.stop()
        result = self._role.dprx.video_capturer.capture_result

        # pylint: disable=R1732
        tmp = tempfile.NamedTemporaryFile(suffix=".bmp")
        # pylint: enable=R1732

        result.save_image_to_file(
            file_format=UniTAP.PictureFileFormat.BMP,
            path=tmp.name,
            index=0,
        )

        with open(tmp.name, "rb") as f:
            return video_pb2.ScreenshotVideoTesterResponse(screenshot=f.read())

    @log_functionality.logger
    def GetStreamInfoVideoTester(self, request, context):
        """Get the current advanced link parameters for a given video tester."""

        self._check_serial_active(request.id)

        stream_num = self._get_number_of_video_streams()

        res = []
        for i in range(0, stream_num):
            stream = self._role.dprx.link.status.stream(i)
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
            )
            res.append(stream_info)

        return video_pb2.GetStreamInfoVideoTesterResponse(streams=res)

    @log_functionality.logger
    def AttachVideoTester(self, request, context):
        """Simulate attaching or detaching a display or sink on a video tester."""
        self._check_serial_active(request.id)

        if isinstance(self._role, UniTAP.dev.UCD500.USBCSourceUSBCSink):
            self._role.pdcrx.controls.attach(request.attach)
        else:
            raise RuntimeError(
                f"Attach operation for role {self._role} is not implemented."
            )

        return video_pb2.AttachVideoTesterResponse()

    @log_functionality.logger
    def HpdPulseVideoTester(self, request, context):
        """Sends an HPD (Hot Plug Detect) pulse to a video tester."""
        self._check_serial_active(request.id)

        self._role.dprx.link.hpd_pulse()

        return video_pb2.HpdPulseVideoTesterResponse()

    @log_functionality.logger
    def _get_number_of_video_streams(self):
        # When using USB-C DPAM, caps.mst_sink_count will not be zero
        # if we are in a detached state.
        if isinstance(self._role, UniTAP.dev.UCD500.USBCSourceUSBCSink):
            dut_dmap = self._role.pdcrx.dp_alt_mode.status.dut_dp_alt_mode
            dpam_status = dut_dmap.dut_connection
            if dpam_status == "No connection":
                return 0

        caps = self._role.dprx.link.capabilities.link_caps_status()

        return caps.mst_sink_count if caps.mst else 1

    @log_functionality.logger
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
