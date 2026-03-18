# Copyright 2025 The ChromiumOS Authors
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

"""Provides a gRPC server to control Unigraf video testing hardware.

This module implements the VideoTesterService gRPC service, allowing clients
to discover, open, close, and configure Unigraf UCD-500 series video testers
using the UniTAP library.
"""

import logging
import tempfile
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


class Ucd500Server(server.UcdServer):
    """Implements the gRPC service for controlling Unigraf video testers.

    This class provides methods to discover, open, close, and configure
    Unigraf UCD-500 series video testing devices. It uses the UniTAP library
    to interact with the hardware.
    """

    @log_functionality.logger
    def __init__(self):
        super().__init__("UCD-500")
        logging.info("VideoTesterServiceServicer init done")

    @log_functionality.logger
    def SetLinkVideoTester(self, request, context):
        """Sets advanced link parameters for a given video tester."""
        self._check_serial_active(request.id)
        caps = self._role.dprx.link.capabilities.link_caps_status()

        if request.HasField("video_spec"):
            rates = []
            if video_pb2.DP_128_BITRATE_10_0 in request.dp_128_bitrates:
                rates.append(10.0)
            if video_pb2.DP_128_BITRATE_13_5 in request.dp_128_bitrates:
                rates.append(13.5)
            if video_pb2.DP_128_BITRATE_20_0 in request.dp_128_bitrates:
                rates.append(20.0)

            if not rates:
                rates = [10.0, 13.5, 20.0]

            if request.video_spec in [
                video_pb2.VIDEO_SPECIFICATION_DP_2_0,
                video_pb2.VIDEO_SPECIFICATION_DP_2_1,
            ]:
                caps.dp_128_132_bitrates = rates
            else:
                # Disable dp 2+. Ignore all rates if they were set.
                caps.dp_128_132_bitrates = []

        if request.HasField("mst"):
            caps.mst = request.mst

        if request.HasField("mst_sink_count"):
            caps.mst_sink_count = request.mst_sink_count

        if request.HasField("max_lane"):
            caps.max_lane = request.max_lane

        if request.HasField("scrambler_seed"):
            self._role.dprx.link.scrambler_seed = request.scrambler_seed

        if request.HasField("ss_sbm"):
            caps.ss_sbm = request.ss_sbm

        if request.HasField("fec"):
            caps.fec = request.fec

        if request.HasField("tps4"):
            caps.tps4 = request.tps4

        if request.HasField("tps3"):
            caps.tps3 = request.tps3

        if request.HasField("dsc"):
            caps.dsc = request.dsc

        self._role.dprx.link.capabilities.set(caps)

        return video_pb2.SetLinkVideoTesterResponse()

    @log_functionality.logger
    def GetLinkVideoTester(self, request, context):
        """Get the current advanced link parameters for a given video tester."""

        self._check_serial_active(request.id)
        caps = self._role.dprx.link.capabilities.link_caps_status()

        link_info = video_pb2.GetLinkVideoTesterResponse()
        link_info.mst = caps.mst
        link_info.mst_sink_count = caps.mst_sink_count
        link_info.max_lane = caps.max_lane
        link_info.scrambler_seed = self._role.dprx.link.scrambler_seed
        link_info.ss_sbm = caps.ss_sbm
        link_info.fec = caps.fec
        link_info.tps4 = caps.tps4
        link_info.tps3 = caps.tps3

        if caps.dp_128_132_bitrates:
            link_info.video_spec = video_pb2.VIDEO_SPECIFICATION_DP_2_1
            if 10.0 in caps.dp_128_132_bitrates:
                link_info.dp_128_bitrates.append(video_pb2.DP_128_BITRATE_10_0)
            if 13.5 in caps.dp_128_132_bitrates:
                link_info.dp_128_bitrates.append(video_pb2.DP_128_BITRATE_13_5)
            if 20.0 in caps.dp_128_132_bitrates:
                link_info.dp_128_bitrates.append(video_pb2.DP_128_BITRATE_20_0)
        else:
            link_info.video_spec = video_pb2.VIDEO_SPECIFICATION_DP_1_4

        link_info.dsc = caps.dsc

        return link_info

    @log_functionality.logger
    def AttachVideoTester(self, request, context):
        """Simulate attaching or detaching a display or sink on a video tester."""
        self._check_serial_active(request.id)

        if isinstance(self._role, UniTAP.dev.UCD500.USBCSourceUSBCSink):
            self._role.pdcrx.controls.attach(request.attach)
            self._role.dprx.link.set_assert_state(request.attach)
        else:
            raise RuntimeError(
                f"Attach operation for role {self._role} is not implemented."
            )

        return video_pb2.AttachVideoTesterResponse()

    @log_functionality.logger
    def HpdPulseVideoTester(self, request, context):
        """Sends an HPD (Hot Plug Detect) pulse to a video tester."""
        self._check_serial_active(request.id)

        self._port_rx.link.hpd_pulse()

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

        caps = self._port_rx.link.capabilities.link_caps_status()

        return caps.mst_sink_count if caps.mst else 1

    @log_functionality.logger
    def StartEventCapture(self, request, context):
        """Start the event capture with the specified filters"""

        event_config_tx = self._port_tx.event_capturer.event_filter(
            UniTAP.EventFilterDpTx
        )
        event_config_rx = self._port_rx.event_capturer.event_filter(
            UniTAP.EventFilterDpRx
        )

        event_config_rx.config_hpd_events(request.dprx_config.hpd_events)
        event_config_rx.config_aux_events(request.dprx_config.aux_events)
        event_config_rx.config_sdp_events(request.dprx_config.sdp_events)
        event_config_rx.config_link_pattern_events(
            request.dprx_config.link_pattern_events
        )
        event_config_rx.config_vb_id_events(request.dprx_config.vb_id_events)
        event_config_rx.config_msa_events(request.dprx_config.msa_events)
        event_config_rx.config_aux_bw_events(request.dprx_config.aux_bw_events)

        event_config_tx.config_hpd_events(request.dptx_config.hpd_events)
        event_config_tx.config_aux_events(request.dptx_config.aux_events)

        # Stop any capture in case they are still running.
        self._port_tx.event_capturer.stop()
        self._port_rx.event_capturer.stop()

        self._port_tx.event_capturer.configure_capturer(event_config_tx)
        self._port_rx.event_capturer.configure_capturer(event_config_rx)

        self._port_tx.event_capturer.start()
        self._port_rx.event_capturer.start()

        return video_pb2.StartEventCaptureResponse()

    def StopEventCapture(self, request, context):
        """Stop the event capture and optionally get the capture files."""

        logging.info("Running StopEventCapture")

        self._port_tx.event_capturer.stop()
        self._port_rx.event_capturer.stop()

        capture_result_tx = (
            self._port_tx.event_capturer.pop_all_elements_as_result_object()
        )
        capture_result_rx = (
            self._port_rx.event_capturer.pop_all_elements_as_result_object()
        )

        logging.info(
            f"StopEventCapture results are {len(capture_result_tx.buffer)} {len(capture_result_rx.buffer)}"
        )

        # Generate reports only if requested.
        if not request.generate_reports:
            return video_pb2.StopEventCaptureResponse()

        # pylint: disable=R1732
        tmp_tx = tempfile.NamedTemporaryFile(suffix=".html")
        tmp_rx = tempfile.NamedTemporaryFile(suffix=".html")
        # pylint: enable=R1732

        capture_result_tx.save_to_file_all_events(
            file_format=UniTAP.EventFileFormat.HTML, path=tmp_tx.name
        )
        capture_result_rx.save_to_file_all_events(
            file_format=UniTAP.EventFileFormat.HTML, path=tmp_rx.name
        )

        with open(tmp_tx.name, "rb") as f_tx, open(tmp_rx.name, "rb") as f_rx:
            logging.info("Files were found")
            return video_pb2.StopEventCaptureResponse(
                dptx_capture_html=f_tx.read(),
                dprx_capture_html=f_rx.read(),
            )

    def _role_set_quirks(self, role_to_set):
        self._role = self._dev.select_role(role_to_set)
        self._port_rx = self._role.dprx
        self._port_tx = self._role.dptx
        self._dev.opf_handler = UniTAP.OpfHandlerInternal(
            port_tx=self._port_tx,
            port_rx=self._port_rx,
        )
        logging.info("Role was selected successfully.")

        if isinstance(self._role, UniTAP.dev.UCD500.USBCSourceUSBCSink):
            logging.info("Set USB-PD to UFP.")
            self._role.pdcrx.capabilities.set_initial_role(
                UniTAP.pdc.PdcDeviceRole.UFP
            )
            # Disable PR swap to avoid triggering PDC bugs, this should force snk
            self._role.pdcrx.capabilities.enable_pr_swap(False)
            self._role.pdcrx.capabilities.cc_pull_up(
                UniTAP.pdc.CCPullUp.Current_3A
            )

            self._role.pdcrx.controls.reconnect()
            time.sleep(5)
