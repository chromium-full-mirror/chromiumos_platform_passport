# Copyright 2025 The ChromiumOS Authors
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

"""Provides a gRPC server to control Unigraf UCD-500 video testing hardware.

This module implements the VideoTesterService gRPC service, allowing clients
to discover, open, close, and configure Unigraf UCD-500 series video testers
using the UniTAP library.
"""

import logging
import time

# pylint: disable=import-error
from chromiumos.test.lab.api.passport import (
    video_tester_service_pb2 as video_pb2,
)
from ucd import server
import UniTAP

from utils import log_functionality


# pylint: enable=import-error


class Ucd500Server(server.UcdServer):
    """Implements the gRPC service for Unigraf UCD-500 video testers.

    This class provides DisplayPort 1.4/2.1 and USB-C DP Alt Mode link,
    event capture, and role configuration methods for UCD-500 devices.
    """

    @log_functionality.logger
    def __init__(self):
        super().__init__("UCD-500")
        logging.info("VideoTesterServiceServicer init done")

    @server.synchronized
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

            if request.dp_810_bitrates:
                if video_pb2.DP_810_BITRATE_8_1 in request.dp_810_bitrates:
                    caps.bit_rate = 8.1
                elif video_pb2.DP_810_BITRATE_6_75 in request.dp_810_bitrates:
                    caps.bit_rate = 6.75
                elif video_pb2.DP_810_BITRATE_5_4 in request.dp_810_bitrates:
                    caps.bit_rate = 5.4
                elif video_pb2.DP_810_BITRATE_2_7 in request.dp_810_bitrates:
                    caps.bit_rate = 2.7
                elif video_pb2.DP_810_BITRATE_1_62 in request.dp_810_bitrates:
                    caps.bit_rate = 1.62
            elif request.video_spec not in [
                video_pb2.VIDEO_SPECIFICATION_DP_2_0,
                video_pb2.VIDEO_SPECIFICATION_DP_2_1,
            ]:
                dp_1_2 = getattr(video_pb2, "VIDEO_SPECIFICATION_DP_1_2", -1)
                dp_1_1 = getattr(video_pb2, "VIDEO_SPECIFICATION_DP_1_1", -1)
                if request.video_spec == dp_1_2:
                    caps.bit_rate = 5.4
                elif request.video_spec == dp_1_1:
                    caps.bit_rate = 2.7
                else:
                    caps.bit_rate = 8.1

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

        if request.HasField("max_lane"):
            self._configure_pdc_dp_alt_mode_lanes(request.max_lane)

        return video_pb2.SetLinkVideoTesterResponse()

    def _configure_pdc_dp_alt_mode_lanes(self, max_lane: int) -> None:
        """Configures the USB-C PDC DP Alt Mode pin assignment for 2 or 4 lanes.

        When max_lane is 2, configures Type-C Pin Assignment D (2 DP lanes +
        2 USB3 SuperSpeed lanes) with Multi-Function Preferred enabled. When
        max_lane is 4, configures Pin Assignment C (4 DP lanes) with
        Multi-Function Preferred disabled.
        """
        if (
            max_lane not in (2, 4)
            or not isinstance(self._role, UniTAP.dev.UCD500.USBCSourceUSBCSink)
            or self._role.pdcrx is None
        ):
            return

        is_two_lane = max_lane == 2
        try:
            dpam = self._role.pdcrx.dp_alt_mode
            pin_caps = dpam.ufp_caps
            pin_caps.c_4_lanes = not is_two_lane
            pin_caps.d_2_lanes = True
            pin_caps.e_4_lanes = False
            # UniTAP's DPAMCaps.value() shifts dfp_assign into both the
            # DFP and UFP bitfields, so both properties must be set.
            dpam.ufp_caps = pin_caps
            dpam.dfp_caps = pin_caps
            dpam.multifunction_preferred(is_two_lane)
            if is_two_lane:
                dpam.enter_2_lane()
            else:
                dpam.enter_4_lane()
        except Exception as e:  # pylint: disable=broad-exception-caught
            logging.warning(
                "Failed to configure PDC DP Alt Mode for %d lanes: %s",
                max_lane,
                e,
            )

    @server.synchronized
    @log_functionality.logger
    def GetLinkVideoTester(self, request, context):
        """Gets the current advanced link parameters for a video tester."""
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
            dp_1_4 = video_pb2.VIDEO_SPECIFICATION_DP_1_4
            dp_1_2 = getattr(video_pb2, "VIDEO_SPECIFICATION_DP_1_2", dp_1_4)
            dp_1_1 = getattr(video_pb2, "VIDEO_SPECIFICATION_DP_1_1", dp_1_4)
            if getattr(caps, "bit_rate", None) is not None:
                if caps.bit_rate >= 8.1:
                    link_info.video_spec = dp_1_4
                    link_info.dp_810_bitrates.append(
                        video_pb2.DP_810_BITRATE_8_1
                    )
                elif caps.bit_rate >= 6.75:
                    link_info.video_spec = dp_1_4
                    link_info.dp_810_bitrates.append(
                        video_pb2.DP_810_BITRATE_6_75
                    )
                elif caps.bit_rate >= 5.4:
                    link_info.video_spec = dp_1_2
                    link_info.dp_810_bitrates.append(
                        video_pb2.DP_810_BITRATE_5_4
                    )
                elif caps.bit_rate >= 2.7:
                    link_info.video_spec = dp_1_1
                    link_info.dp_810_bitrates.append(
                        video_pb2.DP_810_BITRATE_2_7
                    )
                elif caps.bit_rate >= 1.62:
                    link_info.video_spec = dp_1_1
                    link_info.dp_810_bitrates.append(
                        video_pb2.DP_810_BITRATE_1_62
                    )
            else:
                link_info.video_spec = dp_1_4

        link_info.dsc = caps.dsc

        return link_info

    @server.synchronized
    @log_functionality.logger
    def AttachVideoTester(self, request, context):
        """Simulates attaching or detaching a display or sink."""
        self._check_serial_active(request.id)

        if isinstance(self._role, UniTAP.dev.UCD500.USBCSourceUSBCSink):
            self._role.pdcrx.controls.attach(request.attach)
            self._role.dprx.link.set_assert_state(request.attach)
        elif hasattr(self._port_rx, "link") and hasattr(
            self._port_rx.link, "set_assert_state"
        ):
            self._port_rx.link.set_assert_state(request.attach)
        else:
            raise RuntimeError(
                f"Attach operation for role {self._role} is not implemented."
            )

        return video_pb2.AttachVideoTesterResponse()

    @server.synchronized
    @log_functionality.logger
    def HpdPulseVideoTester(self, request, context):
        """Sends an HPD (Hot Plug Detect) pulse to a video tester."""
        self._check_serial_active(request.id)

        has_duration = (
            request.HasField("pulse_duration_ms")
            and request.pulse_duration_ms > 0
        )
        duration_ms = request.pulse_duration_ms if has_duration else 500
        if (
            duration_ms >= 100
            and hasattr(self._port_rx, "link")
            and hasattr(self._port_rx.link, "set_assert_state")
        ):
            self._port_rx.link.set_assert_state(False)
            time.sleep(duration_ms / 1000.0)
            self._port_rx.link.set_assert_state(True)
        else:
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

    @server.synchronized
    @log_functionality.logger
    def StartEventCapture(self, request, context):
        """Starts the event capture with the specified filters."""
        self._check_serial_active(request.id)

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
        self._event_capture_active = True

        return video_pb2.StartEventCaptureResponse()

    @server.synchronized
    def StopEventCapture(self, request, context):
        """Stops the event capture and optionally gets the capture files."""
        self._check_serial_active(request.id)
        logging.info("Running StopEventCapture")

        self._event_capture_active = False
        self._port_tx.event_capturer.stop()
        self._port_rx.event_capturer.stop()

        capture_result_tx = (
            self._port_tx.event_capturer.pop_all_elements_as_result_object()
        )
        capture_result_rx = (
            self._port_rx.event_capturer.pop_all_elements_as_result_object()
        )

        logging.info(
            "StopEventCapture results are %d %d",
            len(capture_result_tx.buffer),
            len(capture_result_rx.buffer),
        )

        # Generate reports only if requested.
        if not request.generate_reports:
            return video_pb2.StopEventCaptureResponse()

        fw_parts = self._get_fw_info().split("|")
        if len(fw_parts) >= 3:
            for port in (self._port_tx, self._port_rx):
                self._update_event_capturer_fw_version(port, fw_parts[2])

        with (
            server.temp_file_path(suffix=".html") as tx_path,
            server.temp_file_path(suffix=".html") as rx_path,
        ):
            capture_result_tx.save_to_file_all_events(
                file_format=UniTAP.EventFileFormat.HTML, path=tx_path
            )
            capture_result_rx.save_to_file_all_events(
                file_format=UniTAP.EventFileFormat.HTML, path=rx_path
            )

            with open(tx_path, "rb") as f_tx, open(rx_path, "rb") as f_rx:
                logging.info("Files were found")
                dptx_html = f_tx.read()
                dprx_html = f_rx.read()

        return video_pb2.StopEventCaptureResponse(
            dptx_capture_html=dptx_html,
            dprx_capture_html=dprx_html,
        )

    def _role_set_quirks(self, role_to_set):
        self._select_role(role_to_set)
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
            # Disable PR swap to avoid triggering PDC bugs; force sink role.
            self._role.pdcrx.capabilities.enable_pr_swap(False)
            self._role.pdcrx.capabilities.cc_pull_up(
                UniTAP.pdc.CCPullUp.Current_3A
            )

            self._role.pdcrx.controls.reconnect()
            time.sleep(5)
