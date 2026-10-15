# Copyright 2026 The ChromiumOS Authors
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

"""Unit tests for UcdServer, Ucd500Server, and Ucd422Server."""

from __future__ import annotations

import enum
import os
import sys
import threading
import types
import unittest
from unittest import mock


os.environ.setdefault("PROTOCOL_BUFFERS_PYTHON_IMPLEMENTATION", "python")
_CONFIG_PYTHON = os.path.abspath(
    os.path.join(os.path.dirname(__file__), "../../../../../config/python")
)
if os.path.isdir(_CONFIG_PYTHON) and _CONFIG_PYTHON not in sys.path:
    sys.path.insert(0, _CONFIG_PYTHON)


# Provide lightweight fallback modules when running without grpc or PIL.
# pylint: disable=unknown-option-value,g-import-not-at-top,invalid-name,g-bad-exception-name
# pylint: disable=wrong-import-position,import-error
try:
    import grpc  # pylint: disable=unused-import
except ModuleNotFoundError:
    grpc_stub = types.ModuleType("grpc")

    class _StatusCode(enum.Enum):
        OK = 0
        INVALID_ARGUMENT = 3
        DEADLINE_EXCEEDED = 4
        FAILED_PRECONDITION = 9
        INTERNAL = 13
        UNAVAILABLE = 14

    grpc_stub.StatusCode = _StatusCode  # type: ignore[attr-defined]
    sys.modules["grpc"] = grpc_stub

    pb2_grpc_name = (
        "chromiumos.test.lab.api.passport.video_tester_service_pb2_grpc"
    )
    if pb2_grpc_name not in sys.modules:
        pb2_grpc_stub = types.ModuleType(pb2_grpc_name)

        class _VideoTesterServiceServicer:
            """Stub servicer base class."""

        setattr(
            pb2_grpc_stub,
            "VideoTesterServiceServicer",
            _VideoTesterServiceServicer,
        )
        sys.modules[pb2_grpc_name] = pb2_grpc_stub

try:
    import PIL  # pylint: disable=unused-import
except ModuleNotFoundError:
    pil_stub = types.ModuleType("PIL")
    pil_image_stub = types.ModuleType("PIL.Image")
    pil_stub.Image = pil_image_stub  # type: ignore[attr-defined]
    sys.modules["PIL"] = pil_stub
    sys.modules["PIL.Image"] = pil_image_stub

try:
    import UniTAP  # pylint: disable=unused-import
except ModuleNotFoundError:
    unitap_stub = mock.MagicMock()

    class _VideoCaptureStatus(enum.Enum):
        Idle = 0
        LiveModeActive = 1
        Malfunction = 2

    class _EventCaptureStatus(enum.Enum):
        Idle = 0
        Running = 1
        Malfunction = 2

    class _NotExistingRoleSelected(Exception):
        pass

    class _DeviceRoleIsAlreadySelected(Exception):
        pass

    class _USBCSourceUSBCSink:
        pass

    class _DPSourceUSBCSink:
        pass

    class _USBCSourceDPSink:
        pass

    class _DPSourceDPSink:
        pass

    class _HDMISourceHDMISink:
        pass

    unitap_stub.VideoCaptureStatus = _VideoCaptureStatus
    unitap_stub.EventCaptureStatus = _EventCaptureStatus
    unitap_stub.dev.UCD422.HDMISourceHDMISink = _HDMISourceHDMISink
    unitap_stub.dev.UCD500.USBCSourceUSBCSink = _USBCSourceUSBCSink
    unitap_stub.dev.UCD500.DPSourceUSBCSink = _DPSourceUSBCSink
    unitap_stub.dev.UCD500.USBCSourceDPSink = _USBCSourceDPSink
    unitap_stub.dev.UCD500.DPSourceDPSink = _DPSourceDPSink
    unitap_stub.dev.device.NotExistingRoleSelected = _NotExistingRoleSelected
    unitap_stub.dev.device.DeviceRoleIsAlreadySelected = (
        _DeviceRoleIsAlreadySelected
    )
    sys.modules["UniTAP"] = unitap_stub
    sys.modules["UniTAP.dev"] = unitap_stub.dev
    sys.modules["UniTAP.dev.modules"] = unitap_stub.dev.modules
    sys.modules["UniTAP.dev.modules.dut_tests"] = (
        unitap_stub.dev.modules.dut_tests
    )
    sys.modules["UniTAP.dev.modules.dut_tests.dut_default_params"] = (
        unitap_stub.dev.modules.dut_tests.dut_default_params
    )

from chromiumos.test.lab.api.passport import (
    video_tester_service_pb2 as video_pb2,
)
import grpc
from ucd import ucd422
from ucd import ucd500
import UniTAP


# pylint: enable=g-import-not-at-top,g-bad-exception-name
# pylint: enable=wrong-import-position,import-error

FAKE_SERIAL = "2236C961"
HEALTHY_FW_INFO = (
    "UCD-500|2236C961|"
    "UX: 1.0.21, UF: 1.0.22, MFMN500: F.0.7.32.0.0.0/N.3.7.18.0.0.0/M.0.0.8, "
    "PDRX: 0.2.3, PDTX: 0.2.3|"
    "1.0|2048"
)
WEDGED_PD_FW_INFO = (
    "UCD-500|2236C961|"
    "UX: 1.0.21, UF: 1.0.22, MFMN500: F.0.7.32.0.0.0/N.3.7.18.0.0.0/M.0.0.8, "
    "PDRX: 0.0.0, PDTX: 0.0.0|"
    "1.0|2048"
)


# pylint: disable=protected-access
class TestUcd500Server(unittest.TestCase):
    """Unit test suite for UcdServer, Ucd500Server, and Ucd422Server."""

    def setUp(self) -> None:
        super().setUp()
        self.enterContext(mock.patch("ucd.server.atexit.register"))
        mock_tsilib_cls = self.enterContext(
            mock.patch("ucd.server.UniTAP.TsiLib")
        )
        self.mock_tsilib = mock_tsilib_cls.return_value
        self.mock_dev = mock.MagicMock()
        self.mock_io = mock.MagicMock()
        self.mock_io.get_prepared_fw_info.return_value = HEALTHY_FW_INFO
        self.mock_dev._TSIDevice__io = self.mock_io

        self.mock_role = mock.MagicMock(
            spec=UniTAP.dev.UCD500.USBCSourceUSBCSink
        )
        self.mock_port_rx = mock.MagicMock()
        self.mock_port_tx = mock.MagicMock()
        self.mock_port_rx.video_capturer.status = UniTAP.VideoCaptureStatus.Idle
        self.mock_port_rx.event_capturer.status = UniTAP.EventCaptureStatus.Idle
        self.mock_port_tx.event_capturer.status = UniTAP.EventCaptureStatus.Idle
        self.mock_role.dprx = self.mock_port_rx
        self.mock_role.dptx = self.mock_port_tx
        self.mock_role.pdcrx = mock.MagicMock()
        self.mock_dev.select_role.return_value = self.mock_role
        self.mock_tsilib.open.return_value = self.mock_dev

        self.server = ucd500.Ucd500Server()
        self.context = mock.MagicMock()

    def _open_and_set_role(self) -> None:
        """Helper to open the fake UCD-500 and select USBCSourceUSBCSink."""
        self.server.OpenVideoTester(
            video_pb2.OpenVideoTesterRequest(id=FAKE_SERIAL), self.context
        )
        with (
            mock.patch("ucd.ucd500.UniTAP.OpfHandlerInternal"),
            mock.patch("ucd.ucd500.time.sleep"),
        ):
            self.server.SetRoleVideoTester(
                video_pb2.SetRoleRequest(
                    id=FAKE_SERIAL,
                    role=video_pb2.ROLE_USBCSOURCE_USBCSINK,
                ),
                self.context,
            )

    @mock.patch("ucd.server.time.sleep")
    def test_screenshot_success_when_capturer_idle(
        self, mock_sleep: mock.MagicMock
    ) -> None:
        """Verifies ScreenshotVideoTester succeeds when capturer is Idle."""
        del mock_sleep
        self._open_and_set_role()
        dp_status = self.mock_role.pdcrx.dp_alt_mode.status.dut_dp_alt_mode
        dp_status.dut_connection = "Connected"
        link_caps = self.mock_port_rx.link.capabilities.link_caps_status
        link_caps.return_value.mst = False
        self.mock_port_rx.video_capturer.capture_result.buffer = [object()]

        def write_bmp(file_format, path, index):
            del file_format, index
            with open(path, "wb") as f:
                f.write(b"BM_FAKE_IMAGE_DATA")

        capture_result = self.mock_port_rx.video_capturer.capture_result
        capture_result.save_image_to_file.side_effect = write_bmp

        reply = self.server.ScreenshotVideoTester(
            video_pb2.ScreenshotVideoTesterRequest(id=FAKE_SERIAL, id_stream=0),
            self.context,
        )
        self.assertEqual(reply.screenshot, b"BM_FAKE_IMAGE_DATA")
        self.context.set_code.assert_not_called()

    @mock.patch("ucd.server.time.sleep")
    def test_screenshot_normal_stream_failure_does_not_report_not_idle(
        self, mock_sleep: mock.MagicMock
    ) -> None:
        """Verifies normal stream failures do not report capturer not idle."""
        del mock_sleep
        self._open_and_set_role()
        dp_status = self.mock_role.pdcrx.dp_alt_mode.status.dut_dp_alt_mode
        dp_status.dut_connection = "Connected"
        link_caps = self.mock_port_rx.link.capabilities.link_caps_status
        link_caps.return_value.mst = False
        self.mock_port_rx.video_capturer.status = UniTAP.VideoCaptureStatus.Idle
        self.mock_port_rx.video_capturer.pop_element.side_effect = ValueError(
            "Minimum buffer size must be more than 0"
        )

        with self.assertRaises(RuntimeError) as ctx:
            self.server.ScreenshotVideoTester(
                video_pb2.ScreenshotVideoTesterRequest(
                    id=FAKE_SERIAL, id_stream=0
                ),
                self.context,
            )

        self.context.set_code.assert_called_once_with(
            grpc.StatusCode.UNAVAILABLE
        )
        details = self.context.set_details.call_args[0][0]
        self.assertIn("Minimum buffer size must be more than 0", details)
        self.assertNotIn("Video capturer is not idle", details)
        self.assertNotIn("Video capturer is not idle", str(ctx.exception))

    @mock.patch("ucd.server.time.sleep")
    def test_screenshot_wedged_capturer_reports_not_idle(
        self, mock_sleep: mock.MagicMock
    ) -> None:
        """Verifies non-idle capturer surfaces 'Video capturer is not idle'."""
        del mock_sleep
        self._open_and_set_role()
        dp_status = self.mock_role.pdcrx.dp_alt_mode.status.dut_dp_alt_mode
        dp_status.dut_connection = "Connected"
        link_caps = self.mock_port_rx.link.capabilities.link_caps_status
        link_caps.return_value.mst = False
        self.mock_port_rx.video_capturer.status = (
            UniTAP.VideoCaptureStatus.LiveModeActive
        )

        with self.assertRaises(RuntimeError) as ctx:
            self.server.ScreenshotVideoTester(
                video_pb2.ScreenshotVideoTesterRequest(
                    id=FAKE_SERIAL, id_stream=0
                ),
                self.context,
            )

        details = self.context.set_details.call_args[0][0]
        self.assertIn("Video capturer is not idle", details)
        self.assertIn("Video capturer is not idle", str(ctx.exception))

    def test_set_role_fails_when_pdrx_pdtx_firmware_is_zero(self) -> None:
        """Verifies SetRoleVideoTester fails when PDRX/PDTX is 0.0.0."""
        self.server.OpenVideoTester(
            video_pb2.OpenVideoTesterRequest(id=FAKE_SERIAL), self.context
        )
        self.mock_io.get_prepared_fw_info.return_value = WEDGED_PD_FW_INFO

        with (
            mock.patch("ucd.ucd500.UniTAP.OpfHandlerInternal"),
            mock.patch("ucd.ucd500.time.sleep"),
            self.assertRaises(RuntimeError) as ctx,
        ):
            self.server.SetRoleVideoTester(
                video_pb2.SetRoleRequest(
                    id=FAKE_SERIAL,
                    role=video_pb2.ROLE_USBCSOURCE_USBCSINK,
                ),
                self.context,
            )

        self.assertIn(
            "Corrupted UCD firmware version detected", str(ctx.exception)
        )

    @mock.patch("ucd.server.time.sleep")
    def test_set_role_fails_when_video_capturer_not_idle(
        self, mock_sleep: mock.MagicMock
    ) -> None:
        """Verifies SetRoleVideoTester fails when video capturer is non-idle."""
        del mock_sleep
        self.server.OpenVideoTester(
            video_pb2.OpenVideoTesterRequest(id=FAKE_SERIAL), self.context
        )
        self.mock_port_rx.video_capturer.status = (
            UniTAP.VideoCaptureStatus.Malfunction
        )

        with (
            mock.patch("ucd.ucd500.UniTAP.OpfHandlerInternal"),
            mock.patch("ucd.ucd500.time.sleep"),
            self.assertRaises(RuntimeError) as ctx,
        ):
            self.server.SetRoleVideoTester(
                video_pb2.SetRoleRequest(
                    id=FAKE_SERIAL,
                    role=video_pb2.ROLE_USBCSOURCE_USBCSINK,
                ),
                self.context,
            )

        self.assertIn("Video capturer is not idle", str(ctx.exception))

    def test_set_role_allows_inactive_pdtx_zero_on_dp_source_role(self) -> None:
        """Verifies PDTX: 0.0.0 is allowed on DP-source roles without pdctx."""
        self.server.OpenVideoTester(
            video_pb2.OpenVideoTesterRequest(id=FAKE_SERIAL), self.context
        )
        dp_source_role = mock.MagicMock(spec=UniTAP.dev.UCD500.DPSourceUSBCSink)
        dp_source_role.dprx = self.mock_port_rx
        dp_source_role.dptx = self.mock_port_tx
        dp_source_role.pdcrx = mock.MagicMock()
        self.mock_dev.select_role.return_value = dp_source_role
        self.mock_io.get_prepared_fw_info.return_value = (
            "UCD-500|2236C961|UX: 2.6.1, UF: 1.3.4, PDRX: 1.4.20, PDTX: 0.0.0|"
            "1.0|2048"
        )

        with mock.patch("ucd.ucd500.UniTAP.OpfHandlerInternal"):
            reply = self.server.SetRoleVideoTester(
                video_pb2.SetRoleRequest(
                    id=FAKE_SERIAL,
                    role=video_pb2.ROLE_DPSOURCE_USBCSINK,
                ),
                self.context,
            )
        self.assertTrue(reply.success)

    def test_set_role_reopens_once_on_initial_ux_zero_stall(self) -> None:
        """Verifies _role_set_quirks reopens and retries on UX: 0.0.0 stall."""
        self.server.OpenVideoTester(
            video_pb2.OpenVideoTesterRequest(id=FAKE_SERIAL), self.context
        )
        stalled_fw = (
            "UCD-500|2236C961|UX: 0.0.0, UF: 0.0.0, PDRX: 0.0.0, PDTX: 0.0.0|"
            "1.0|2048"
        )
        self.mock_io.get_prepared_fw_info.side_effect = [
            stalled_fw,
            HEALTHY_FW_INFO,
            HEALTHY_FW_INFO,
        ]

        with (
            mock.patch("ucd.ucd500.UniTAP.OpfHandlerInternal"),
            mock.patch("ucd.ucd500.time.sleep"),
        ):
            reply = self.server.SetRoleVideoTester(
                video_pb2.SetRoleRequest(
                    id=FAKE_SERIAL,
                    role=video_pb2.ROLE_USBCSOURCE_USBCSINK,
                ),
                self.context,
            )

        self.assertTrue(reply.success)
        self.assertEqual(self.mock_dev.select_role.call_count, 2)
        self.mock_tsilib.close.assert_called_once_with(self.mock_dev)

    def test_set_role_reopens_on_not_existing_role_selected(self) -> None:
        """Verifies _role_set_quirks reopens when select_role raises."""
        self.server.OpenVideoTester(
            video_pb2.OpenVideoTesterRequest(id=FAKE_SERIAL), self.context
        )
        self.mock_dev.select_role.side_effect = [
            UniTAP.dev.device.NotExistingRoleSelected(
                "Role is not supported by the device."
            ),
            self.mock_role,
        ]

        with (
            mock.patch("ucd.ucd500.UniTAP.OpfHandlerInternal"),
            mock.patch("ucd.ucd500.time.sleep"),
        ):
            reply = self.server.SetRoleVideoTester(
                video_pb2.SetRoleRequest(
                    id=FAKE_SERIAL,
                    role=video_pb2.ROLE_USBCSOURCE_USBCSINK,
                ),
                self.context,
            )

        self.assertTrue(reply.success)
        self.assertEqual(self.mock_dev.select_role.call_count, 2)
        self.mock_tsilib.close.assert_called_once_with(self.mock_dev)

    def test_set_role_reopens_twice_on_already_selected_then_ux_zero(
        self,
    ) -> None:
        """Verifies _role_set_quirks recovers across 2 reopens."""
        self.server.OpenVideoTester(
            video_pb2.OpenVideoTesterRequest(id=FAKE_SERIAL), self.context
        )
        stalled_fw = (
            "UCD-500|2236C961|UX: 0.0.0, UF: 0.0.0, PDRX: 0.0.0, PDTX: 0.0.0|"
            "1.0|2048"
        )
        self.mock_dev.select_role.side_effect = [
            UniTAP.dev.device.DeviceRoleIsAlreadySelected(
                "Device role is already selected."
            ),
            self.mock_role,
            self.mock_role,
        ]
        self.mock_io.get_prepared_fw_info.side_effect = [
            stalled_fw,
            HEALTHY_FW_INFO,
            HEALTHY_FW_INFO,
        ]

        with (
            mock.patch("ucd.ucd500.UniTAP.OpfHandlerInternal"),
            mock.patch("ucd.ucd500.time.sleep"),
        ):
            reply = self.server.SetRoleVideoTester(
                video_pb2.SetRoleRequest(
                    id=FAKE_SERIAL,
                    role=video_pb2.ROLE_USBCSOURCE_USBCSINK,
                ),
                self.context,
            )

        self.assertTrue(reply.success)
        self.assertEqual(self.mock_dev.select_role.call_count, 3)
        self.assertEqual(self.mock_tsilib.close.call_count, 2)

    def test_set_role_recovers_even_when_close_raises(self) -> None:
        """Verifies _select_role still reopens if close() raises on bad dev."""
        self.server.OpenVideoTester(
            video_pb2.OpenVideoTesterRequest(id=FAKE_SERIAL), self.context
        )
        self.mock_dev.select_role.side_effect = [
            UniTAP.dev.device.NotExistingRoleSelected(
                "Role is not supported by the device."
            ),
            self.mock_role,
        ]
        self.mock_tsilib.close.side_effect = [
            RuntimeError("USB close error"),
            None,
        ]

        with (
            mock.patch("ucd.ucd500.UniTAP.OpfHandlerInternal"),
            mock.patch("ucd.ucd500.time.sleep"),
        ):
            reply = self.server.SetRoleVideoTester(
                video_pb2.SetRoleRequest(
                    id=FAKE_SERIAL,
                    role=video_pb2.ROLE_USBCSOURCE_USBCSINK,
                ),
                self.context,
            )

        self.assertTrue(reply.success)
        self.assertEqual(self.mock_dev.select_role.call_count, 2)
        self.assertEqual(self.mock_tsilib.open.call_count, 2)

    def test_open_video_tester_closes_stale_open_device(self) -> None:
        """Verifies OpenVideoTester closes a stale open handle first."""
        self._open_and_set_role()
        reply = self.server.OpenVideoTester(
            video_pb2.OpenVideoTesterRequest(id=FAKE_SERIAL), self.context
        )
        self.assertTrue(reply.success)
        self.mock_port_rx.video_capturer.stop.assert_called_once()
        self.mock_port_rx.event_capturer.stop.assert_called_once()
        self.mock_port_tx.video_capturer.stop.assert_called_once()
        self.mock_port_tx.event_capturer.stop.assert_called_once()
        self.mock_tsilib.close.assert_called_once_with(self.mock_dev)
        self.assertEqual(self.mock_tsilib.open.call_count, 2)

    def test_close_video_tester_stops_capturers(self) -> None:
        """Verifies CloseVideoTester stops active capturers before closing."""
        self._open_and_set_role()
        reply = self.server.CloseVideoTester(
            video_pb2.CloseVideoTesterRequest(id=FAKE_SERIAL), self.context
        )
        self.assertTrue(reply.success)
        self.mock_port_rx.video_capturer.stop.assert_called_once()
        self.mock_port_rx.event_capturer.stop.assert_called_once()
        self.mock_port_tx.video_capturer.stop.assert_called_once()
        self.mock_port_tx.event_capturer.stop.assert_called_once()
        self.mock_tsilib.close.assert_called_once_with(self.mock_dev)
        self.assertIsNone(self.server._port_rx)
        self.assertIsNone(self.server._port_tx)
        self.assertIsNone(self.server._role)
        self.assertIsNone(self.server._dev)

    @mock.patch("ucd.server.time.sleep")
    def test_power_cycle_invokes_direct_io_reset(
        self, mock_sleep: mock.MagicMock
    ) -> None:
        """Verifies PowerCycle calls _TSIDevice__io.reset() directly."""
        del mock_sleep
        self.server.OpenVideoTester(
            video_pb2.OpenVideoTesterRequest(id=FAKE_SERIAL), self.context
        )
        with mock.patch.object(
            self.server, "_force_usb_reenumeration", return_value=True
        ):
            self.server.PowerCycle(
                video_pb2.PowerCycleRequest(id=FAKE_SERIAL), self.context
            )
        self.mock_io.reset.assert_called_once()

    def test_stop_event_capture_refreshes_live_fw_version(self) -> None:
        """Verifies StopEventCapture refreshes cached fw_info."""
        self._open_and_set_role()
        tx_fw_info = {"ucd_fw_version": "UX: 1.0.21, PDRX: 0.2.3, PDTX: 0.2.3"}
        rx_fw_info = {"ucd_fw_version": "UX: 1.0.21, PDRX: 0.2.3, PDTX: 0.2.3"}
        self.mock_port_tx.event_capturer._EventCapturer__fw_info = tx_fw_info
        self.mock_port_rx.event_capturer._EventCapturer__fw_info = rx_fw_info
        self.mock_io.get_prepared_fw_info.return_value = WEDGED_PD_FW_INFO

        self.server.StopEventCapture(
            video_pb2.StopEventCaptureRequest(
                id=FAKE_SERIAL, generate_reports=True
            ),
            self.context,
        )

        self.assertIn("PDRX: 0.0.0, PDTX: 0.0.0", tx_fw_info["ucd_fw_version"])
        self.assertIn("PDRX: 0.0.0, PDTX: 0.0.0", rx_fw_info["ucd_fw_version"])

    @mock.patch("ucd.server.time.sleep")
    def test_ensure_video_capturer_idle_recovers_via_pipeline_reset(
        self, mock_sleep: mock.MagicMock
    ) -> None:
        """Verifies _ensure_video_capturer_idle resets wedged pipeline."""
        del mock_sleep
        self._open_and_set_role()
        self.mock_port_rx.video_capturer.status = (
            UniTAP.VideoCaptureStatus.LiveModeActive
        )
        self.mock_port_rx.event_capturer.status = (
            UniTAP.EventCaptureStatus.Running
        )
        self.mock_port_rx.event_capturer._EventCapturer__result.buffer = [
            "evt1",
            "evt2",
        ]

        def stop_event_capturer() -> None:
            self.mock_port_rx.event_capturer.status = (
                UniTAP.EventCaptureStatus.Idle
            )
            self.mock_port_rx.event_capturer._EventCapturer__result.buffer = []

        def start_event_capturer() -> None:
            self.mock_port_rx.event_capturer.status = (
                UniTAP.EventCaptureStatus.Running
            )

        def write_port_reg(reg: int, val: int) -> None:
            if (
                reg == 0x301
                and val == 2
                and self.mock_port_rx.event_capturer.status
                == UniTAP.EventCaptureStatus.Idle
            ):
                self.mock_port_rx.video_capturer.status = (
                    UniTAP.VideoCaptureStatus.Idle
                )

        self.mock_port_rx.event_capturer.stop.side_effect = stop_event_capturer
        self.mock_port_rx.event_capturer.start.side_effect = (
            start_event_capturer
        )
        self.mock_port_rx._Port__io.set.side_effect = write_port_reg

        self.server._ensure_video_capturer_idle()

        self.assertEqual(
            self.mock_port_rx.video_capturer.status,
            UniTAP.VideoCaptureStatus.Idle,
        )
        self.mock_port_rx._Port__io.set.assert_has_calls(
            [
                mock.call(0x302, 0),
                mock.call(0x301, 2),
                mock.call(0x5002C004, 1),
            ]
        )
        capturer = self.mock_dev._TSIDevice__capturer
        capturer.clear_bulk_buffer.assert_called_once()
        self.mock_dev._TSIDevice__memory_manager.reset.assert_called_once()
        self.mock_port_rx.event_capturer.start.assert_called_once()
        self.assertEqual(
            self.mock_port_rx.event_capturer._EventCapturer__result.buffer,
            ["evt1", "evt2"],
        )

    @mock.patch("ucd.server.time.sleep")
    def test_ensure_video_capturer_idle_recovers_malfunction_via_pulse(
        self, mock_sleep: mock.MagicMock
    ) -> None:
        """Verifies Malfunction status clears via 0-frame start/stop pulse."""
        del mock_sleep
        self._open_and_set_role()
        self.mock_port_rx.video_capturer.status = (
            UniTAP.VideoCaptureStatus.Malfunction
        )
        pulsed = {"zero_frame_started": False}

        def start_capturer(
            frames_count: int = 0, stream_number: int = 0
        ) -> None:
            if frames_count == 0 and stream_number == 0:
                pulsed["zero_frame_started"] = True

        def stop_capturer() -> None:
            if pulsed["zero_frame_started"]:
                self.mock_port_rx.video_capturer.status = (
                    UniTAP.VideoCaptureStatus.Idle
                )

        self.mock_port_rx.video_capturer.start.side_effect = start_capturer
        self.mock_port_rx.video_capturer.stop.side_effect = stop_capturer

        self.server._ensure_video_capturer_idle()

        self.assertEqual(
            self.mock_port_rx.video_capturer.status,
            UniTAP.VideoCaptureStatus.Idle,
        )
        self.mock_port_rx.video_capturer.start.assert_called_once_with(
            frames_count=0, stream_number=0
        )

    @mock.patch("ucd.server.time.sleep")
    def test_screenshot_recovers_on_retry_after_min_buffer_size_error(
        self, mock_sleep: mock.MagicMock
    ) -> None:
        """Verifies ScreenshotVideoTester resets pipeline and retries."""
        del mock_sleep
        self._open_and_set_role()
        dp_status = self.mock_role.pdcrx.dp_alt_mode.status.dut_dp_alt_mode
        dp_status.dut_connection = "Connected"
        link_caps = self.mock_port_rx.link.capabilities.link_caps_status
        link_caps.return_value.mst = False
        self.mock_port_rx.video_capturer.pop_element.side_effect = [
            ValueError("Minimum buffer size must be more than 0"),
            None,
        ]
        self.mock_port_rx.video_capturer.capture_result.buffer = [object()]

        def write_bmp(file_format, path, index) -> None:
            del file_format, index
            with open(path, "wb") as f:
                f.write(b"BM_RECOVERED_IMAGE")

        capture_result = self.mock_port_rx.video_capturer.capture_result
        capture_result.save_image_to_file.side_effect = write_bmp

        reply = self.server.ScreenshotVideoTester(
            video_pb2.ScreenshotVideoTesterRequest(id=FAKE_SERIAL, id_stream=0),
            self.context,
        )

        self.assertEqual(reply.screenshot, b"BM_RECOVERED_IMAGE")
        capturer = self.mock_dev._TSIDevice__capturer
        capturer.clear_bulk_buffer.assert_called_once()
        self.mock_dev._TSIDevice__memory_manager.reset.assert_called_once()
        self.context.set_code.assert_not_called()

    def test_set_role_recovers_pdrx_zero_in_place_via_pdc_reset(self) -> None:
        """Verifies PDRX: 0.0.0 is recovered in-place via pdcrx reset."""
        self.server.OpenVideoTester(
            video_pb2.OpenVideoTesterRequest(id=FAKE_SERIAL), self.context
        )
        self.mock_io.get_prepared_fw_info.side_effect = [
            WEDGED_PD_FW_INFO,
            HEALTHY_FW_INFO,
            HEALTHY_FW_INFO,
        ]

        with (
            mock.patch("ucd.ucd500.UniTAP.OpfHandlerInternal"),
            mock.patch("ucd.ucd500.time.sleep"),
        ):
            reply = self.server.SetRoleVideoTester(
                video_pb2.SetRoleRequest(
                    id=FAKE_SERIAL,
                    role=video_pb2.ROLE_USBCSOURCE_USBCSINK,
                ),
                self.context,
            )

        self.assertTrue(reply.success)
        self.mock_role.pdcrx.controls.reset.assert_called_once()
        self.mock_dev.select_role.assert_called_once()
        self.mock_tsilib.close.assert_not_called()

    def test_set_role_recovers_pdrx_zero_via_reopen_when_pdc_reset_insufficient(
        self,
    ) -> None:
        """Verifies _select_role reopens handle if in-place PDC reset fails."""
        self.server.OpenVideoTester(
            video_pb2.OpenVideoTesterRequest(id=FAKE_SERIAL), self.context
        )
        self.mock_io.get_prepared_fw_info.side_effect = [
            WEDGED_PD_FW_INFO,
            WEDGED_PD_FW_INFO,
            HEALTHY_FW_INFO,
            HEALTHY_FW_INFO,
        ]

        with (
            mock.patch("ucd.ucd500.UniTAP.OpfHandlerInternal"),
            mock.patch("ucd.ucd500.time.sleep"),
        ):
            reply = self.server.SetRoleVideoTester(
                video_pb2.SetRoleRequest(
                    id=FAKE_SERIAL,
                    role=video_pb2.ROLE_USBCSOURCE_USBCSINK,
                ),
                self.context,
            )

        self.assertTrue(reply.success)
        self.mock_role.pdcrx.controls.reset.assert_called_once()
        self.assertEqual(self.mock_dev.select_role.call_count, 2)
        self.mock_tsilib.close.assert_called_once_with(self.mock_dev)

    def test_set_role_allows_benign_ux_only_zero_after_retries_exhausted(
        self,
    ) -> None:
        """Verifies benign UX: 0.0.0 with healthy UF/PDRX succeeds at end."""
        self.server.OpenVideoTester(
            video_pb2.OpenVideoTesterRequest(id=FAKE_SERIAL), self.context
        )
        benign_ux_zero_fw = (
            "UCD-500|2236C961|UX: 0.0.0, UF: 1.0.22, PDRX: 0.2.3, PDTX: 0.2.3|"
            "1.0|2048"
        )
        self.mock_io.get_prepared_fw_info.return_value = benign_ux_zero_fw

        with (
            mock.patch("ucd.ucd500.UniTAP.OpfHandlerInternal"),
            mock.patch("ucd.ucd500.time.sleep"),
        ):
            reply = self.server.SetRoleVideoTester(
                video_pb2.SetRoleRequest(
                    id=FAKE_SERIAL,
                    role=video_pb2.ROLE_USBCSOURCE_USBCSINK,
                ),
                self.context,
            )

        self.assertTrue(reply.success)
        self.mock_io.set.assert_called_with(0x210, 0x40000000)
        self.assertEqual(self.mock_dev.select_role.call_count, 3)

    def test_set_role_recovers_pdrx_zero_with_concurrent_benign_ux_zero(
        self,
    ) -> None:
        """Verifies pdcrx is reset even when UX: 0.0.0 is also present."""
        self.server.OpenVideoTester(
            video_pb2.OpenVideoTesterRequest(id=FAKE_SERIAL), self.context
        )
        ux_and_pdrx_zero_fw = (
            "UCD-500|2236C961|UX: 0.0.0, UF: 1.0.22, PDRX: 0.0.0, PDTX: 0.2.3|"
            "1.0|2048"
        )
        benign_ux_zero_fw = (
            "UCD-500|2236C961|UX: 0.0.0, UF: 1.0.22, PDRX: 0.2.3, PDTX: 0.2.3|"
            "1.0|2048"
        )
        self.mock_io.get_prepared_fw_info.side_effect = [
            ux_and_pdrx_zero_fw,
            benign_ux_zero_fw,
            benign_ux_zero_fw,
            benign_ux_zero_fw,
            benign_ux_zero_fw,
        ]

        with (
            mock.patch("ucd.ucd500.UniTAP.OpfHandlerInternal"),
            mock.patch("ucd.ucd500.time.sleep"),
        ):
            reply = self.server.SetRoleVideoTester(
                video_pb2.SetRoleRequest(
                    id=FAKE_SERIAL,
                    role=video_pb2.ROLE_USBCSOURCE_USBCSINK,
                ),
                self.context,
            )

        self.assertTrue(reply.success)
        self.mock_role.pdcrx.controls.reset.assert_called_once()
        self.mock_io.set.assert_called_with(0x210, 0x40000000)
        self.assertEqual(self.mock_dev.select_role.call_count, 3)

    @mock.patch("ucd.server.time.sleep")
    def test_pipeline_reset_prefers_tsi_port_io_and_close_breaks_ref_cycle(
        self, mock_sleep: mock.MagicMock
    ) -> None:
        """Verifies _TSIPort__io lookup and _close_device cycle break."""
        del mock_sleep
        self._open_and_set_role()
        tsi_port_io = mock.MagicMock()
        self.mock_port_rx._TSIPort__io = tsi_port_io
        self.server._reset_video_capturer_pipeline()

        tsi_port_io.set.assert_has_calls(
            [
                mock.call(0x302, 0),
                mock.call(0x301, 2),
                mock.call(0x5002C004, 1),
            ]
        )

        self.server._close_device()
        self.assertIsNone(self.mock_dev.opf_handler)
        self.mock_io.set_role.assert_called_with(None)

    def test_stop_event_capture_and_load_edid_clean_up_temp_files(
        self,
    ) -> None:
        """Verifies StopEventCapture and LoadEdidVideoTester unlink temps."""
        self._open_and_set_role()
        event_paths: list[str] = []

        def save_events(file_format, path) -> None:
            del file_format
            event_paths.append(path)
            with open(path, "wb") as f:
                f.write(b"<html>events</html>")

        tx_capturer = self.mock_port_tx.event_capturer
        rx_capturer = self.mock_port_rx.event_capturer
        tx_res = tx_capturer.pop_all_elements_as_result_object.return_value
        rx_res = rx_capturer.pop_all_elements_as_result_object.return_value
        tx_res.save_to_file_all_events.side_effect = save_events
        rx_res.save_to_file_all_events.side_effect = save_events

        resp = self.server.StopEventCapture(
            video_pb2.StopEventCaptureRequest(
                id=FAKE_SERIAL, generate_reports=True
            ),
            self.context,
        )
        self.assertEqual(resp.dptx_capture_html, b"<html>events</html>")
        self.assertEqual(resp.dprx_capture_html, b"<html>events</html>")
        self.assertEqual(len(event_paths), 2)
        for path in event_paths:
            self.assertFalse(os.path.exists(path))

        edid_paths: list[str] = []

        def load_edid(path, load_on_device, stream):
            del load_on_device, stream
            edid_paths.append(path)
            self.assertTrue(os.path.exists(path))
            return [1]

        self.mock_port_rx.edid.load_edid.side_effect = load_edid
        edid_resp = self.server.LoadEdidVideoTester(
            video_pb2.LoadEdidVideoTesterRequest(
                id=FAKE_SERIAL, edid=b"\x00\xff" * 64, id_stream=0
            ),
            self.context,
        )
        self.assertTrue(edid_resp.success)
        self.assertEqual(len(edid_paths), 1)
        self.assertFalse(os.path.exists(edid_paths[0]))

    def test_synchronized_lock_serializes_concurrent_rpcs(self) -> None:
        """Verifies self._lock prevents overlapping RPC execution."""
        self._open_and_set_role()
        in_first = threading.Event()
        release_first = threading.Event()
        execution_order: list[str] = []

        def slow_get_testers():
            execution_order.append("first_enter")
            in_first.set()
            release_first.wait(timeout=2.0)
            execution_order.append("first_exit")
            return [f"0: UCD-500 [{FAKE_SERIAL}]"]

        self.mock_tsilib.get_list_of_available_devices.side_effect = (
            slow_get_testers
        )
        self.mock_dev.available_roles = [UniTAP.dev.UCD500.USBCSourceUSBCSink]

        def call_get_roles():
            in_first.wait(timeout=2.0)
            second_started.set()
            self.server.GetRolesVideoTester(
                video_pb2.GetRolesRequest(id=FAKE_SERIAL), self.context
            )
            execution_order.append("second_done")

        second_started = threading.Event()
        worker = threading.Thread(target=call_get_roles)
        worker.start()
        in_first_thread = threading.Thread(
            target=self.server.GetVideoTesters, args=(None, self.context)
        )
        in_first_thread.start()
        in_first.wait(timeout=2.0)
        second_started.wait(timeout=2.0)
        release_first.set()
        in_first_thread.join(timeout=2.0)
        worker.join(timeout=2.0)

        self.assertEqual(
            execution_order, ["first_enter", "first_exit", "second_done"]
        )

    def test_synchronized_lock_timeout_with_context_time_remaining(
        self,
    ) -> None:
        """Verifies @synchronized bounds lock wait with time_remaining()."""
        self._open_and_set_role()
        lock_held = threading.Event()
        release_lock = threading.Event()

        def hold_lock() -> None:
            with self.server._lock:
                lock_held.set()
                release_lock.wait(timeout=2.0)

        holder = threading.Thread(target=hold_lock)
        holder.start()
        lock_held.wait(timeout=2.0)
        try:
            timed_context = mock.MagicMock()
            timed_context.time_remaining.return_value = 0.01

            with self.assertRaises(TimeoutError):
                self.server.PowerCycle(
                    video_pb2.PowerCycleRequest(id=FAKE_SERIAL),
                    timed_context,
                )

            timed_context.set_code.assert_called_once_with(
                grpc.StatusCode.DEADLINE_EXCEEDED
            )
            timed_context.abort.assert_called_once()
        finally:
            release_lock.set()
            holder.join(timeout=2.0)

    def test_run_compliance_test_unknown_group_raises_clean_error(
        self,
    ) -> None:
        """Verifies RunComplianceTest reports unknown test.group_id cleanly."""
        self._open_and_set_role()
        fake_req = mock.MagicMock()
        fake_req.id = FAKE_SERIAL
        fake_test = mock.MagicMock()
        fake_test.group_id = 999999
        fake_req.tests = [fake_test]

        with self.assertRaises(RuntimeError) as ctx:
            self.server.RunComplianceTest(fake_req, self.context)

        self.assertIn("Test group is unknown 999999", str(ctx.exception))

    def test_get_rx_port_io_resolution_order(self) -> None:
        """Verifies _get_rx_port_io checks None, _TSIPort__io, and _Port__io."""
        self.server._port_rx = None
        self.assertIsNone(self.server._get_rx_port_io())

        class DummyPort:
            """Dummy port object for testing IO resolution."""

        port = DummyPort()
        port_io = object()
        tsi_port_io = object()
        setattr(port, "_Port__io", port_io)
        self.server._port_rx = port
        self.assertIs(self.server._get_rx_port_io(), port_io)

        setattr(port, "_TSIPort__io", tsi_port_io)
        self.assertIs(self.server._get_rx_port_io(), tsi_port_io)

    def test_ucd500_set_and_get_link_video_tester_all_branches(self) -> None:
        """Verifies Ucd500Server SetLinkVideoTester and GetLinkVideoTester."""
        self._open_and_set_role()

        class FakeCaps:
            """Fake link capabilities object."""

            def __init__(self) -> None:
                self.dp_128_132_bitrates: list[float] = []
                self.bit_rate: float | None = 8.1
                self.mst = False
                self.mst_sink_count = 1
                self.max_lane = 4
                self.ss_sbm = False
                self.fec = False
                self.tps4 = False
                self.tps3 = False
                self.dsc = False

        caps = FakeCaps()
        link_caps = self.mock_port_rx.link.capabilities
        link_caps.link_caps_status.return_value = caps
        self.mock_port_rx.link.scrambler_seed = 0

        # 1. DP 2.1 with empty dp_128_bitrates defaults to [10.0, 13.5, 20.0]
        req_dp21_default = video_pb2.SetLinkVideoTesterRequest(
            id=FAKE_SERIAL,
            video_spec=video_pb2.VIDEO_SPECIFICATION_DP_2_1,
            mst=True,
            mst_sink_count=2,
            max_lane=4,
            scrambler_seed=1,
            ss_sbm=True,
            fec=True,
            tps4=True,
            tps3=True,
            dsc=True,
        )
        self.server.SetLinkVideoTester(req_dp21_default, self.context)
        self.assertEqual(caps.dp_128_132_bitrates, [10.0, 13.5, 20.0])
        got_dp21 = self.server.GetLinkVideoTester(
            video_pb2.GetLinkVideoTesterRequest(id=FAKE_SERIAL), self.context
        )
        self.assertEqual(
            got_dp21.video_spec, video_pb2.VIDEO_SPECIFICATION_DP_2_1
        )
        self.assertEqual(
            list(got_dp21.dp_128_bitrates),
            [
                video_pb2.DP_128_BITRATE_10_0,
                video_pb2.DP_128_BITRATE_13_5,
                video_pb2.DP_128_BITRATE_20_0,
            ],
        )

        # 2. DP 1.4 with explicit dp_810_bitrates clears dp_128_132_bitrates
        for proto_rate, expected_rate in (
            (video_pb2.DP_810_BITRATE_8_1, 8.1),
            (video_pb2.DP_810_BITRATE_6_75, 6.75),
            (video_pb2.DP_810_BITRATE_5_4, 5.4),
            (video_pb2.DP_810_BITRATE_2_7, 2.7),
            (video_pb2.DP_810_BITRATE_1_62, 1.62),
        ):
            req_810 = video_pb2.SetLinkVideoTesterRequest(
                id=FAKE_SERIAL,
                video_spec=video_pb2.VIDEO_SPECIFICATION_DP_1_4,
                dp_810_bitrates=[proto_rate],
            )
            self.server.SetLinkVideoTester(req_810, self.context)
            self.assertEqual(caps.dp_128_132_bitrates, [])
            self.assertEqual(caps.bit_rate, expected_rate)
            got_810 = self.server.GetLinkVideoTester(
                video_pb2.GetLinkVideoTesterRequest(id=FAKE_SERIAL),
                self.context,
            )
            self.assertEqual(list(got_810.dp_810_bitrates), [proto_rate])

        # 3. Fallback bit_rate when dp_810_bitrates is empty & bit_rate is None
        req_dp14_default = video_pb2.SetLinkVideoTesterRequest(
            id=FAKE_SERIAL,
            video_spec=video_pb2.VIDEO_SPECIFICATION_DP_1_4,
        )
        self.server.SetLinkVideoTester(req_dp14_default, self.context)
        self.assertEqual(caps.bit_rate, 8.1)

        caps.bit_rate = None
        got_none_rate = self.server.GetLinkVideoTester(
            video_pb2.GetLinkVideoTesterRequest(id=FAKE_SERIAL), self.context
        )
        self.assertEqual(
            got_none_rate.video_spec, video_pb2.VIDEO_SPECIFICATION_DP_1_4
        )

    @mock.patch("ucd.ucd500.time.sleep")
    def test_ucd500_attach_hpd_stream_count_and_stop_event_short_circuit(
        self, mock_sleep: mock.MagicMock
    ) -> None:
        """Verifies Attach, HpdPulse, stream count, and StopEventCapture."""
        del mock_sleep
        self._open_and_set_role()

        # 1. AttachVideoTester on USBCSourceUSBCSink
        self.server.AttachVideoTester(
            video_pb2.AttachVideoTesterRequest(id=FAKE_SERIAL, attach=True),
            self.context,
        )
        self.mock_role.pdcrx.controls.attach.assert_called_once_with(True)
        self.mock_port_rx.link.set_assert_state.assert_called_once_with(True)

        # 2. AttachVideoTester on DP-Sink role (non-USBCSourceUSBCSink)
        self.mock_port_rx.link.set_assert_state.reset_mock()
        self.server._role = mock.MagicMock(
            spec=UniTAP.dev.UCD500.DPSourceUSBCSink
        )
        self.server.AttachVideoTester(
            video_pb2.AttachVideoTesterRequest(id=FAKE_SERIAL, attach=False),
            self.context,
        )
        self.mock_port_rx.link.set_assert_state.assert_called_once_with(False)

        # 3. AttachVideoTester on unsupported role without link.set_assert_state
        self.server._port_rx = object()
        with self.assertRaises(RuntimeError) as ctx:
            self.server.AttachVideoTester(
                video_pb2.AttachVideoTesterRequest(id=FAKE_SERIAL, attach=True),
                self.context,
            )
        self.assertIn("not implemented", str(ctx.exception))
        self.server._port_rx = self.mock_port_rx
        self.server._role = self.mock_role

        # 4. HpdPulseVideoTester >= 100ms vs < 100ms
        self.mock_port_rx.link.set_assert_state.reset_mock()
        self.server.HpdPulseVideoTester(
            video_pb2.HpdPulseVideoTesterRequest(
                id=FAKE_SERIAL, pulse_duration_ms=200
            ),
            self.context,
        )
        self.assertEqual(
            self.mock_port_rx.link.set_assert_state.call_args_list,
            [mock.call(False), mock.call(True)],
        )
        self.server.HpdPulseVideoTester(
            video_pb2.HpdPulseVideoTesterRequest(
                id=FAKE_SERIAL, pulse_duration_ms=50
            ),
            self.context,
        )
        self.mock_port_rx.link.hpd_pulse.assert_called_once()

        # 5. _get_number_of_video_streams when "No connection" vs MST
        dp_status = self.mock_role.pdcrx.dp_alt_mode.status.dut_dp_alt_mode
        dp_status.dut_connection = "No connection"
        self.assertEqual(self.server._get_number_of_video_streams(), 0)
        dp_status.dut_connection = "Connected"
        caps = self.mock_port_rx.link.capabilities.link_caps_status.return_value
        caps.mst = True
        caps.mst_sink_count = 3
        self.assertEqual(self.server._get_number_of_video_streams(), 3)

        # 6. StopEventCapture(generate_reports=False) short-circuits
        self.mock_io.get_prepared_fw_info.reset_mock()
        resp = self.server.StopEventCapture(
            video_pb2.StopEventCaptureRequest(
                id=FAKE_SERIAL, generate_reports=False
            ),
            self.context,
        )
        self.assertEqual(resp.dptx_capture_html, b"")
        self.assertEqual(resp.dprx_capture_html, b"")
        self.mock_io.get_prepared_fw_info.assert_not_called()

    def test_ucd422_event_capture_and_run_compliance_html_cleanup(
        self,
    ) -> None:
        """Verifies Ucd422Server event capture guards & compliance cleanup."""
        hdmi_server = ucd422.Ucd422Server()
        with self.assertRaises(RuntimeError):
            hdmi_server.StartEventCapture(
                video_pb2.StartEventCaptureRequest(id=FAKE_SERIAL),
                self.context,
            )
        hdmi_server.OpenVideoTester(
            video_pb2.OpenVideoTesterRequest(id=FAKE_SERIAL), self.context
        )
        start_resp = hdmi_server.StartEventCapture(
            video_pb2.StartEventCaptureRequest(id=FAKE_SERIAL), self.context
        )
        stop_resp = hdmi_server.StopEventCapture(
            video_pb2.StopEventCaptureRequest(id=FAKE_SERIAL), self.context
        )
        self.assertIsInstance(start_resp, video_pb2.StartEventCaptureResponse)
        self.assertIsInstance(stop_resp, video_pb2.StopEventCaptureResponse)

        # Verify RunComplianceTest cleans up both tmp_base and tmp_base.html
        self._open_and_set_role()
        self.mock_role.dut_tests = mock.MagicMock()
        created_bases: list[str] = []

        def fake_make_report(tmp_base, tested_by):
            del tested_by
            created_bases.append(tmp_base)
            with open(f"{tmp_base}.html", "wb") as f:
                f.write(b"<html>cts</html>")

        self.mock_role.dut_tests.make_report.side_effect = fake_make_report
        all_results = self.mock_role.dut_tests.get_all_tests_results
        all_results.return_value.all_test_results.return_value = []
        fake_req = mock.MagicMock()
        fake_req.id = FAKE_SERIAL
        fake_req.tests = []
        comp_resp = self.server.RunComplianceTest(fake_req, self.context)
        self.assertEqual(comp_resp.results_html, b"<html>cts</html>")
        self.assertEqual(len(created_bases), 1)
        self.assertFalse(os.path.exists(created_bases[0]))
        self.assertFalse(os.path.exists(f"{created_bases[0]}.html"))

    def test_rpc_negative_and_guard_branches(self) -> None:
        """Verifies PP-16 negative RPC and serial guard branches."""
        # 1. _check_serial_active when self._serial is None
        with self.assertRaises(RuntimeError) as ctx1:
            self.server._check_serial_active(FAKE_SERIAL)
        self.assertIn(f"Tester {FAKE_SERIAL} is not open", str(ctx1.exception))

        # 2. GetVideoTesters malformed serial string
        self.mock_tsilib.get_list_of_available_devices.return_value = [
            "0: UCD-500 malformed_no_brackets"
        ]
        with self.assertRaises(RuntimeError) as ctx2:
            self.server.GetVideoTesters(None, self.context)
        self.assertIn("Serial parsing is malformed!", str(ctx2.exception))
        self.context.set_code.assert_called_with(grpc.StatusCode.INTERNAL)

        # 3. OpenVideoTester when _open_device raises
        self.mock_tsilib.open.side_effect = RuntimeError("USB open failed")
        with self.assertRaises(RuntimeError) as ctx3:
            self.server.OpenVideoTester(
                video_pb2.OpenVideoTesterRequest(id=FAKE_SERIAL), self.context
            )
        self.assertIn("Failed to open device:", str(ctx3.exception))
        self.context.set_code.assert_called_with(grpc.StatusCode.INTERNAL)
        self.mock_tsilib.open.side_effect = None
        self.mock_tsilib.open.return_value = self.mock_dev

        # 4. Open device, then test _check_serial_active mismatch & unknown role
        self.server.OpenVideoTester(
            video_pb2.OpenVideoTesterRequest(id=FAKE_SERIAL), self.context
        )
        with self.assertRaises(RuntimeError) as ctx4:
            self.server._check_serial_active("WRONG_SERIAL")
        self.assertIn("Serials dont match", str(ctx4.exception))

        with self.assertRaises(RuntimeError) as ctx5:
            self.server.SetRoleVideoTester(
                video_pb2.SetRoleRequest(id=FAKE_SERIAL, role=99999),
                self.context,
            )
        self.assertIn("Role is unknown 99999", str(ctx5.exception))

        # 5. CloseVideoTester with mismatched serial while open raises
        with self.assertRaises(RuntimeError) as ctx_mismatch:
            self.server.CloseVideoTester(
                video_pb2.CloseVideoTesterRequest(id="WRONG_SERIAL"),
                self.context,
            )
        self.assertIn(
            f"Serial 'WRONG_SERIAL' is not the active device '{FAKE_SERIAL}'",
            str(ctx_mismatch.exception),
        )

        # 6. CloseVideoTester when self._dev is None succeeds idempotently
        self.server._dev = None
        close_reply = self.server.CloseVideoTester(
            video_pb2.CloseVideoTesterRequest(id=FAKE_SERIAL), self.context
        )
        self.assertTrue(close_reply.success)
        self.assertIsNone(self.server._serial)
        self.assertIsNone(self.server._last_requested_role)


if __name__ == "__main__":
    unittest.main()
