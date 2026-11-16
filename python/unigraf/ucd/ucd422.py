# Copyright 2025 The ChromiumOS Authors
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

"""Provides a gRPC server to control Unigraf UCD-422 video testing hardware.

This module implements the VideoTesterService gRPC service, allowing clients
to discover, open, close, and configure Unigraf UCD-422 series video testers
using the UniTAP library.
"""

import ctypes
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


def _infer_hdmi_mode_from_edid(edid: bytes):
    """Infers HdmiModeRx (1.4, 2.0, or 2.1) from CTA-861 HF-VSDB."""
    for offset in range(128, len(edid) - 127, 128):
        block = edid[offset : offset + 128]
        if block[0] != 0x02:
            continue
        dtd_offset = min(block[2], 127)
        pos = 4
        while pos < dtd_offset:
            header = block[pos]
            tag = (header >> 5) & 0x07
            length = header & 0x1F
            end = pos + 1 + length
            if end > dtd_offset:
                break
            if length >= 4:
                payload = block[pos + 1 : end]
                # HF-VSDB (OUI 0xC45DD8, little-endian) or HF-SCDB (extended
                # tag 0x79) share the SCDS layout, Max_FRL_Rate in payload[6].
                if (tag == 0x03 and payload[:3] == b"\xd8\x5d\xc4") or (
                    tag == 0x07 and payload[0] == 0x79
                ):
                    max_frl_rate = (
                        (payload[6] >> 4) & 0x0F if len(payload) >= 7 else 0
                    )
                    if max_frl_rate > 0:
                        return UniTAP.HdmiModeRx.HDMI_2_1
                    return UniTAP.HdmiModeRx.HDMI_2_0
            pos = end
    return UniTAP.HdmiModeRx.HDMI_1_4


class Ucd422Server(server.UcdServer):
    """Implements the gRPC service for Unigraf UCD-422 video testers.

    This class provides methods to discover, open, close, and configure
    Unigraf UCD-422 series video testing devices. It uses the UniTAP library
    to interact with the hardware.
    """

    _TSI_HDRX_VIDEO_MODE_R = 0x817
    _HDMI_VIDEO_MODE_DWORD_COUNT = 13
    _HDMI_TIMING_RELATCH_WAIT_SEC = 0.25
    _HDMI_MODE_CHANGE_SETTLE_SEC = 2.5
    # Workaround for b/586509400, see _log_and_recover_unlatched_rx().
    _RX_RELATCH_AFTER_SEC = 5.0
    _RX_RELATCH_HPD_LOW_SEC = 1.0

    @log_functionality.logger
    def __init__(self):
        super().__init__("UCD-422")
        self._pending_hdmi_mode = None
        self._hpd_asserted_at = None

    @server.synchronized
    @log_functionality.logger
    def SetLinkVideoTester(self, request, context):
        """Sets advanced link parameters for a given video tester."""
        self._check_serial_active(request.id)

        if request.HasField("video_spec"):
            self._port_rx.link.status.hdmi_mode = (
                translate.GRPC_VIDEO_SPEC_TO_SDK[request.video_spec]
            )
            self._pending_hdmi_mode = None

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

    @server.synchronized
    @log_functionality.logger
    def GetLinkVideoTester(self, request, context):
        """Gets the current advanced link parameters for a video tester."""
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

    def _apply_pending_hdmi_mode(
        self, settle_after_change: bool = True
    ) -> None:
        """Applies queued HDMI RX mode right before asserting HPD.

        Writing TSI_HDRX_BEHAVIOR on UCD-422 triggers a ~2s firmware HPD reset
        cycle, so deferring it until Attach(True) or HpdPulse avoids spurious
        re-connects after LoadEdid + Attach(False).
        """
        target_mode = self._pending_hdmi_mode
        if target_mode is None or self._port_rx is None:
            return
        self._pending_hdmi_mode = None
        try:
            if self._port_rx.link.status.hdmi_mode == target_mode:
                return
            logging.info(
                "Setting UCD-422 HDMI RX mode to %s before HPD assert",
                target_mode,
            )
            if settle_after_change:
                self._port_rx.link.status.set_assert_state(False)
            self._port_rx.link.status.hdmi_mode = target_mode
            if settle_after_change:
                time.sleep(self._HDMI_MODE_CHANGE_SETTLE_SEC)
        except Exception as e:  # pylint: disable=broad-except
            logging.warning(
                "Failed to set UCD-422 HDMI RX mode to %s: %s",
                target_mode,
                e,
            )

    @server.synchronized
    @log_functionality.logger
    def AttachVideoTester(self, request, context):
        """Simulates attaching or detaching a display or sink."""
        self._check_serial_active(request.id)

        if request.attach:
            self._apply_pending_hdmi_mode(settle_after_change=True)
        self._port_rx.link.status.set_assert_state(request.attach)
        self._hpd_asserted_at = time.monotonic() if request.attach else None

        return video_pb2.AttachVideoTesterResponse()

    @server.synchronized
    @log_functionality.logger
    def HpdPulseVideoTester(self, request, context):
        """Sends an HPD (Hot Plug Detect) pulse to a video tester."""
        self._check_serial_active(request.id)

        self._port_rx.link.status.set_assert_state(False)
        self._apply_pending_hdmi_mode(settle_after_change=False)
        time.sleep(3)
        self._port_rx.link.status.set_assert_state(True)
        self._hpd_asserted_at = time.monotonic()

        return video_pb2.HpdPulseVideoTesterResponse()

    @server.synchronized
    @log_functionality.logger
    def StartEventCapture(self, request, context):
        """Starts the event capture with the specified filters."""
        self._check_serial_active(request.id)
        logging.info("NoOp StartEventCapture")
        return video_pb2.StartEventCaptureResponse()

    @server.synchronized
    @log_functionality.logger
    def StopEventCapture(self, request, context):
        """Stops the event capture and optionally gets the capture files."""
        self._check_serial_active(request.id)
        logging.info("NoOp StopEventCapture")
        return video_pb2.StopEventCaptureResponse()

    @server.synchronized
    @log_functionality.logger
    def LoadEdidVideoTester(self, request, context):
        """Loads EDID data and queues matching UCD-422 HDMI RX mode."""
        resp = super().LoadEdidVideoTester(request, context)
        if resp.success and self._port_rx is not None:
            self._pending_hdmi_mode = _infer_hdmi_mode_from_edid(request.edid)
        return resp

    def _role_set_quirks(self, role_to_set):
        self._select_role(role_to_set)
        logging.info("Role was selected successfully.")
        self._port_rx = self._role.hdrx
        self._pending_hdmi_mode = None
        self._hpd_asserted_at = None

    def _has_latched_hdmi_timing(self, port_io) -> bool:
        """Checks TSI_HDRX_VIDEO_MODE_R for non-zero active timing."""
        if port_io is None:
            return True
        res = port_io.get(
            self._TSI_HDRX_VIDEO_MODE_R,
            ctypes.c_uint32,
            self._HDMI_VIDEO_MODE_DWORD_COUNT,
        )
        if (
            not isinstance(res, tuple)
            or len(res) < 2
            or not isinstance(res[0], int)
            or isinstance(res[0], bool)
        ):
            return True
        if res[0] < 0:
            return False
        dwords = res[1]
        if not isinstance(dwords, (list, tuple)) or len(dwords) < 4:
            return True
        # HdmiVideoMode layout: [h_total, v_total, h_active, v_active, ...]
        return dwords[2] > 0 and dwords[3] > 0

    def _log_and_recover_unlatched_rx(self) -> None:
        """Logs RX link state on 0x0 timing and re-pulses HPD if stuck.

        WORKAROUND (remove once b/586509400 is fixed in UCD-422 FW):
        in ~5% of HPD asserts the RX locks all TMDS lanes with zero errors
        (the source is driving valid video) but TSI_HDRX_VIDEO_MODE_R never
        latches until the next HPD cycle. If that persists for
        _RX_RELATCH_AFTER_SEC after an assert, pulse HPD once so the source
        re-trains. Lanes unlocked means no valid source signal, so we do not
        pulse then and real source/DUT failures still surface.
        """
        try:
            status = self._port_rx.link.status
            hpd = status.hpd_status
            lanes = status.channel_lock
            logging.warning(
                "UCD-422 RX timing 0x0: hpd=%s mode=%s lane_lock=%s err=%s",
                hpd,
                status.hdmi_mode,
                lanes,
                status.error_counters,
            )
            stuck = (
                hpd
                and all(lanes[:3])
                and self._hpd_asserted_at is not None
                and time.monotonic() - self._hpd_asserted_at
                >= self._RX_RELATCH_AFTER_SEC
            )
        except Exception as e:  # pylint: disable=broad-except
            logging.warning("Failed to read UCD-422 RX link state: %s", e)
            return
        if not stuck:
            return
        logging.warning(
            "UCD-422 RX TMDS locked but timing not latched; re-pulsing "
            "HPD once (workaround for b/586509400)"
        )
        self._hpd_asserted_at = None  # One pulse per HPD assert.
        # Callers expect only ValueError("not available") from here.
        try:
            try:
                status.set_assert_state(False)
                time.sleep(self._RX_RELATCH_HPD_LOW_SEC)
            finally:
                status.set_assert_state(True)  # Never leave HPD low.
        except Exception as e:  # pylint: disable=broad-except
            logging.warning("UCD-422 HPD re-pulse failed: %s", e)

    def _read_stream_status(self, stream_id: int):
        # StatusRx.__check_video() checks `result > 0` on TSI_HDRX_VIDEO_MODE_R,
        # which libTSI sets to 13 even when h_active/v_active are 0. Calling
        # StatusRx.stream() on 0x0 then reads TSI_VIDCAP_SIGNAL_CRC_R, starting
        # live capture on an unlatched stream and stalling 10s in bulk timeouts.
        port_io = self._get_rx_port_io()
        if not self._has_latched_hdmi_timing(port_io):
            time.sleep(self._HDMI_TIMING_RELATCH_WAIT_SEC)
            if not self._has_latched_hdmi_timing(port_io):
                self._log_and_recover_unlatched_rx()
                raise ValueError("Video is not available.")
        # When timing is latched, StatusRx.stream() still leaves live capture
        # active in C++; stop it via the raw TSI capture-stop command.
        try:
            return super()._read_stream_status(stream_id)
        finally:
            try:
                if port_io is not None:
                    port_io.set(self._TSI_W_CAP_COMMAND, self._TSI_CAP_CMD_STOP)
            except Exception as e:  # pylint: disable=broad-except
                logging.warning(
                    "Failed to stop live capture after stream status: %s", e
                )

    @log_functionality.logger
    def _get_number_of_video_streams(self):
        if self._port_rx.link.status.hpd_status:
            return 1
        return 0
