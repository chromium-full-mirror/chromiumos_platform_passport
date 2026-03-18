# Copyright 2025 The ChromiumOS Authors
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

"""Provides a gRPC server to control Unigraf video testing hardware.

This module implements the VideoTesterService gRPC service, allowing clients
to discover, open, close, and configure Unigraf UCD-422 series video testers
using the UniTAP library.
"""

import logging
import time

# pylint: disable=import-error
from chromiumos.test.lab.api.passport import (
    video_tester_service_pb2 as video_pb2,
)
from ucd import server
from ucd import translate
import UniTAP

from utils import log_functionality


# pylint: enable=import-error


class Ucd422Server(server.UcdServer):
    """Implements the gRPC service for controlling Unigraf video testers.

    This class provides methods to discover, open, close, and configure
    Unigraf UCD-422 series video testing devices. It uses the UniTAP library
    to interact with the hardware.
    """

    @log_functionality.logger
    def __init__(self):
        super().__init__("UCD-422")

    @log_functionality.logger
    def SetLinkVideoTester(self, request, context):
        """Sets advanced link parameters for a given video tester."""
        self._check_serial_active(request.id)

        if request.HasField("video_spec"):
            self._port_rx.link.status.hdmi_mode = (
                translate.GRPC_VIDEO_SPEC_TO_SDK[request.video_spec]
            )

        if request.video_spec == video_pb2.VIDEO_SPECIFICATION_HDMI_2_1:
            if request.HasField("frl_mode"):
                self._port_rx.link.frl.frl_mode = (
                    translate.GRPC_FRL_MODE_TO_SDK[request.frl_mode]
                )

            frl_caps = UniTAP.FrlCaps()
            if request.HasField("frl_start"):
                frl_caps.frl_start = request.frl_start

            if request.HasField("frl_ready"):
                frl_caps.flt_ready = request.frl_ready

            if request.HasField("frl_max"):
                frl_caps.frl_max = request.frl_max

            if request.HasField("frl_no_timeout"):
                frl_caps.flt_no_timeout = request.frl_no_timeout

            if request.HasField("frl_check_ltp"):
                frl_caps.check_patterns = request.frl_check_ltp

            self._port_rx.link.frl.frl_caps = frl_caps
            self._port_rx.link.frl.re_train()

        return video_pb2.SetLinkVideoTesterResponse()

    @log_functionality.logger
    def GetLinkVideoTester(self, request, context):
        """Get the current advanced link parameters for a given video tester."""

        self._check_serial_active(request.id)

        logging.info("GetLinkVideoTester")
        link_info = video_pb2.GetLinkVideoTesterResponse()
        link_info.video_spec = translate.SDK_VIDEO_SPEC_TO_RGPC[
            self._port_rx.link.status.hdmi_mode
        ]

        if link_info.video_spec == video_pb2.VIDEO_SPECIFICATION_HDMI_2_1:
            logging.info("Video spec is HDMI 2.1")

            link_info.frl_mode = translate.SDK_FRL_MODE_TO_GRPC[
                self._port_rx.link.frl.frl_mode
            ]
            frl_caps = self._port_rx.link.frl.frl_caps
            link_info.frl_start = frl_caps.frl_start
            link_info.frl_ready = frl_caps.flt_ready
            link_info.frl_max = frl_caps.frl_max
            link_info.frl_no_timeout = frl_caps.flt_no_timeout
            link_info.frl_check_ltp = frl_caps.check_patterns
        else:
            logging.info("Video spec is HDMI 1.4/2.1")
            tdms_stat = self._port_rx.link.tmds
            link_info.tdms_clock_rate = tdms_stat.clock_rate * 1024
            link_info.tdms_report_locks = tdms_stat.input_stream_lock

        # TODO(danielgeorgem@google.com): Add the information about the video
        # lanes.
        return link_info

    @log_functionality.logger
    def AttachVideoTester(self, request, context):
        """Simulate attaching or detaching a display or sink on a video tester."""
        self._check_serial_active(request.id)

        self._port_rx.link.status.set_assert_state(request.attach)

        return video_pb2.AttachVideoTesterResponse()

    @log_functionality.logger
    def HpdPulseVideoTester(self, request, context):
        """Sends an HPD (Hot Plug Detect) pulse to a video tester."""
        self._check_serial_active(request.id)

        self._port_rx.link.status.set_assert_state(False)
        time.sleep(3)
        self._port_rx.link.status.set_assert_state(True)

        return video_pb2.HpdPulseVideoTesterResponse()

    @log_functionality.logger
    def StartEventCapture(self, request, context):
        """Start the event capture with the specified filters"""

        logging.info("NoOp StartEventCapture")

        return video_pb2.StartEventCaptureResponse()

    @log_functionality.logger
    def StopEventCapture(self, request, context):
        """Stop the event capture and optionally get the capture files."""

        logging.info("NoOp StopEventCapture")
        return video_pb2.StopEventCaptureResponse()

    def _role_set_quirks(self, role_to_set):
        self._role = self._dev.select_role(role_to_set)
        logging.info("Role was selected successfully.")
        self._port_rx = self._role.hdrx

    @log_functionality.logger
    def _get_number_of_video_streams(self):
        if self._port_rx.link.status.hpd_status:
            return 1
        return 0
