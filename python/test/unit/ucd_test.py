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
import weakref


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
from ucd import server as ucd_server
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
            mock.patch("ucd.server.time.sleep"),
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
            mock.patch("ucd.server.time.sleep"),
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
        ]

        with (
            mock.patch("ucd.ucd500.UniTAP.OpfHandlerInternal"),
            mock.patch("ucd.server.time.sleep"),
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
            mock.patch("ucd.server.time.sleep"),
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
        ]

        with (
            mock.patch("ucd.ucd500.UniTAP.OpfHandlerInternal"),
            mock.patch("ucd.server.time.sleep"),
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
            mock.patch("ucd.server.time.sleep"),
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
        stream = self.mock_port_rx.link.status.stream.return_value
        stream.video_mode.timing.hactive = 3840
        stream.video_mode.timing.vactive = 2160
        stream.video_mode.color_info.bpp = 24
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
        ]

        with (
            mock.patch("ucd.ucd500.UniTAP.OpfHandlerInternal"),
            mock.patch("ucd.server.time.sleep"),
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
        ]

        with (
            mock.patch("ucd.ucd500.UniTAP.OpfHandlerInternal"),
            mock.patch("ucd.server.time.sleep"),
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
            mock.patch("ucd.server.time.sleep"),
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
        ]

        with (
            mock.patch("ucd.ucd500.UniTAP.OpfHandlerInternal"),
            mock.patch("ucd.server.time.sleep"),
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

    def test_select_role_clears_existing_role_when_switching_roles(
        self,
    ) -> None:
        """Verifies switching roles clears SDK role and reopens TSI handle."""
        self._open_and_set_role()
        self.mock_io.set_role.reset_mock()
        dp_role = mock.MagicMock(spec=UniTAP.dev.UCD500.DPSourceUSBCSink)
        dp_role.dprx = self.mock_port_rx
        dp_role.dptx = self.mock_port_tx
        dp_role.pdcrx = mock.MagicMock()
        self.mock_dev.select_role.return_value = dp_role

        with (
            mock.patch("ucd.ucd500.UniTAP.OpfHandlerInternal"),
            mock.patch("ucd.server.time.sleep"),
        ):
            reply = self.server.SetRoleVideoTester(
                video_pb2.SetRoleRequest(
                    id=FAKE_SERIAL,
                    role=video_pb2.ROLE_DPSOURCE_USBCSINK,
                ),
                self.context,
            )

        self.assertTrue(reply.success)
        self.mock_io.set_role.assert_called_once_with(None)
        self.mock_tsilib.close.assert_called_once_with(self.mock_dev)
        self.assertEqual(self.mock_tsilib.open.call_count, 2)

    def test_select_role_recovers_from_empty_role_list(self) -> None:
        """Verifies _select_role reopens and rescans when role_list is []."""
        self.server.OpenVideoTester(
            video_pb2.OpenVideoTesterRequest(id=FAKE_SERIAL), self.context
        )
        self.mock_dev._TSIDevice__role_list = []

        def reopen_with_roles(serial: str):
            del serial
            self.mock_dev._TSIDevice__role_list = [
                UniTAP.dev.UCD500.USBCSourceUSBCSink
            ]
            return self.mock_dev

        self.mock_tsilib.open.side_effect = reopen_with_roles
        UniTAP.libs.lib_tsi.tsi.TSIX_DEV_RescanDevices.reset_mock()

        with (
            mock.patch("ucd.ucd500.UniTAP.OpfHandlerInternal"),
            mock.patch("ucd.server.time.sleep"),
        ):
            reply = self.server.SetRoleVideoTester(
                video_pb2.SetRoleRequest(
                    id=FAKE_SERIAL,
                    role=video_pb2.ROLE_USBCSOURCE_USBCSINK,
                ),
                self.context,
            )

        self.assertTrue(reply.success)
        self.mock_tsilib.close.assert_called_once_with(self.mock_dev)
        UniTAP.libs.lib_tsi.tsi.TSIX_DEV_RescanDevices.assert_called_once()
        self.assertEqual(self.mock_dev.select_role.call_count, 1)

    def test_select_role_tier3_hard_recovery_polls_until_roles_populated(
        self,
    ) -> None:
        """Verifies Tier 3 hard recovery runs NIOS reset, bounce, and poll."""
        self.server.OpenVideoTester(
            video_pb2.OpenVideoTesterRequest(id=FAKE_SERIAL), self.context
        )
        self.mock_dev.select_role.side_effect = [
            UniTAP.dev.device.NotExistingRoleSelected("Attempt 1 failed"),
            UniTAP.dev.device.NotExistingRoleSelected("Attempt 2 failed"),
            self.mock_role,
        ]

        booting_dev = mock.MagicMock()
        booting_dev._TSIDevice__role_list = []
        self.mock_dev._TSIDevice__role_list = [
            UniTAP.dev.UCD500.USBCSourceUSBCSink
        ]
        self.mock_tsilib.open.side_effect = [
            self.mock_dev,
            RuntimeError("USB still enumerating"),
            booting_dev,
            self.mock_dev,
        ]

        with (
            mock.patch("ucd.ucd500.UniTAP.OpfHandlerInternal"),
            mock.patch("ucd.server.time.sleep"),
            mock.patch.object(
                self.server, "_force_usb_reenumeration", return_value=True
            ) as mock_usb_bounce,
        ):
            reply = self.server.SetRoleVideoTester(
                video_pb2.SetRoleRequest(
                    id=FAKE_SERIAL,
                    role=video_pb2.ROLE_USBCSOURCE_USBCSINK,
                ),
                self.context,
            )

        self.assertTrue(reply.success)
        self.mock_io.reset.assert_called_once()
        mock_usb_bounce.assert_called_once_with(FAKE_SERIAL)
        self.assertEqual(self.mock_dev.select_role.call_count, 3)

    @mock.patch("ucd.server.time.sleep")
    def test_power_cycle_polls_rescan_and_restores_role(
        self, mock_sleep: mock.MagicMock
    ) -> None:
        """Verifies PowerCycle waits 30s, polls rescan, and restores role."""
        self._open_and_set_role()
        self.mock_tsilib._TsiLib__device_list = [self.mock_dev]
        booting_dev = mock.MagicMock()
        booting_dev._TSIDevice__role_list = []
        ready_dev = self.mock_dev
        ready_dev._TSIDevice__role_list = [UniTAP.dev.UCD500.USBCSourceUSBCSink]
        self.mock_tsilib.open.side_effect = [
            RuntimeError("Device not yet enumerated"),
            booting_dev,
            ready_dev,
        ]
        UniTAP.libs.lib_tsi.tsi.TSIX_DEV_RescanDevices.reset_mock()

        with (
            mock.patch("ucd.ucd500.UniTAP.OpfHandlerInternal"),
            mock.patch.object(
                self.server, "_force_usb_reenumeration", return_value=True
            ) as mock_usb_bounce,
        ):
            self.server.PowerCycle(
                video_pb2.PowerCycleRequest(id=FAKE_SERIAL),
                self.context,
            )

        self.mock_io.reset.assert_called_once()
        self.assertEqual(self.server._HW_RESET_INITIAL_WAIT_SEC, 30)
        mock_sleep.assert_any_call(30)
        mock_usb_bounce.assert_called_once_with(FAKE_SERIAL)
        self.assertEqual(
            UniTAP.libs.lib_tsi.tsi.TSIX_DEV_RescanDevices.call_count, 3
        )
        self.assertEqual(self.mock_dev.select_role.call_count, 2)
        self.assertEqual(self.mock_tsilib._TsiLib__device_list, [])

    @mock.patch("ucd.server.time.sleep")
    def test_power_cycle_rejects_mismatched_serial(
        self, mock_sleep: mock.MagicMock
    ) -> None:
        """Verifies PowerCycle rejects a mismatched request.id when open."""
        del mock_sleep
        self._open_and_set_role()
        self.mock_io.reset.reset_mock()

        with (
            mock.patch.object(
                self.server, "_force_usb_reenumeration"
            ) as mock_usb_bounce,
            self.assertRaises(RuntimeError) as ctx,
        ):
            self.server.PowerCycle(
                video_pb2.PowerCycleRequest(id="WRONG_SERIAL"),
                self.context,
            )

        self.assertIn(
            f"Serial 'WRONG_SERIAL' is not the active device '{FAKE_SERIAL}'",
            str(ctx.exception),
        )
        self.mock_io.reset.assert_not_called()
        mock_usb_bounce.assert_not_called()
        self.assertEqual(self.server._serial, FAKE_SERIAL)

    @mock.patch("ucd.server.time.sleep")
    def test_close_then_power_cycle_leaves_device_closed_without_role_set(
        self, mock_sleep: mock.MagicMock
    ) -> None:
        """Verifies CloseVideoTester + PowerCycle leaves tester closed."""
        del mock_sleep
        self._open_and_set_role()
        self.server.CloseVideoTester(
            video_pb2.CloseVideoTesterRequest(id=FAKE_SERIAL), self.context
        )
        self.assertIsNone(self.server._last_requested_role)
        self.assertIsNone(self.server._dev)
        self.assertIsNone(self.server._serial)
        self.mock_dev.select_role.reset_mock()

        with mock.patch.object(
            self.server, "_force_usb_reenumeration", return_value=True
        ):
            self.server.PowerCycle(
                video_pb2.PowerCycleRequest(id=FAKE_SERIAL), self.context
            )

        self.mock_dev.select_role.assert_not_called()
        self.assertIsNone(self.server._dev)
        self.assertIsNone(self.server._role)
        self.assertIsNone(self.server._serial)
        self.assertIsNone(self.server._last_requested_role)

    @mock.patch("ucd.server.time.sleep")
    def test_screenshot_retries_on_dsc_decode_error_minus_5_and_cleans_temp_bmp(
        self, mock_sleep: mock.MagicMock
    ) -> None:
        """Verifies DSC -5 error triggers retry and unlinks temp BMP files."""
        self._open_and_set_role()
        dp_status = self.mock_role.pdcrx.dp_alt_mode.status.dut_dp_alt_mode
        dp_status.dut_connection = "Connected"
        link_caps = self.mock_port_rx.link.capabilities.link_caps_status
        link_caps.return_value.mst = False
        self.mock_port_rx.video_capturer.capture_result.buffer = [object()]

        seen_paths: list[str] = []
        attempt_counter = {"count": 0}

        def save_bmp(file_format, path, index) -> None:
            del file_format, index
            seen_paths.append(path)
            attempt_counter["count"] += 1
            if attempt_counter["count"] == 1:
                with open(path, "wb") as f:
                    f.write(b"PARTIAL")
                raise RuntimeError("Decoding failed with error code: -5")
            with open(path, "wb") as f:
                f.write(b"BM_DSC_DECODED_OK")

        capture_result = self.mock_port_rx.video_capturer.capture_result
        capture_result.save_image_to_file.side_effect = save_bmp

        reply = self.server.ScreenshotVideoTester(
            video_pb2.ScreenshotVideoTesterRequest(id=FAKE_SERIAL, id_stream=0),
            self.context,
        )

        self.assertEqual(reply.screenshot, b"BM_DSC_DECODED_OK")
        self.assertEqual(len(seen_paths), 2)
        for path in seen_paths:
            self.assertFalse(os.path.exists(path))
        mock_sleep.assert_any_call(self.server._SCREENSHOT_RETRY_DELAY_SEC)

    @mock.patch("ucd.server.time.sleep")
    def test_screenshot_retries_on_get_frame_dsc_error(
        self, mock_sleep: mock.MagicMock
    ) -> None:
        """Verifies get_frame() DSC -5 failure is caught and retried."""
        del mock_sleep
        self._open_and_set_role()
        dp_status = self.mock_role.pdcrx.dp_alt_mode.status.dut_dp_alt_mode
        dp_status.dut_connection = "Connected"
        link_caps = self.mock_port_rx.link.capabilities.link_caps_status
        link_caps.return_value.mst = False

        bad_frame = mock.MagicMock()
        bad_frame.get_frame.side_effect = RuntimeError(
            "Decoding failed with error code: -5"
        )
        good_frame = mock.MagicMock()
        good_frame.get_frame.return_value = object()

        def pop_side_effect():
            if self.mock_port_rx.video_capturer.pop_element.call_count == 1:
                self.mock_port_rx.video_capturer.capture_result.buffer = [
                    bad_frame
                ]
                return bad_frame
            self.mock_port_rx.video_capturer.capture_result.buffer = [
                good_frame
            ]
            return good_frame

        self.mock_port_rx.video_capturer.pop_element.side_effect = (
            pop_side_effect
        )

        def write_bmp(file_format, path, index) -> None:
            del file_format, index
            with open(path, "wb") as f:
                f.write(b"BM_FROM_GOOD_FRAME")

        capture_result = self.mock_port_rx.video_capturer.capture_result
        capture_result.save_image_to_file.side_effect = write_bmp

        reply = self.server.ScreenshotVideoTester(
            video_pb2.ScreenshotVideoTesterRequest(id=FAKE_SERIAL, id_stream=0),
            self.context,
        )

        self.assertEqual(reply.screenshot, b"BM_FROM_GOOD_FRAME")
        bad_frame.get_frame.assert_called_once()
        good_frame.get_frame.assert_called_once()

    @mock.patch("ucd.server.time.sleep")
    def test_screenshot_preserves_active_event_capture(
        self, mock_sleep: mock.MagicMock
    ) -> None:
        """Verifies ScreenshotVideoTester re-arms event capture if active."""
        del mock_sleep
        self._open_and_set_role()
        self.server.StartEventCapture(
            video_pb2.StartEventCaptureRequest(id=FAKE_SERIAL), self.context
        )
        self.assertTrue(self.server._event_capture_active)

        dp_status = self.mock_role.pdcrx.dp_alt_mode.status.dut_dp_alt_mode
        dp_status.dut_connection = "Connected"
        link_caps = self.mock_port_rx.link.capabilities.link_caps_status
        link_caps.return_value.mst = False
        self.mock_port_rx.video_capturer.capture_result.buffer = [object()]

        def write_bmp(file_format, path, index) -> None:
            del file_format, index
            with open(path, "wb") as f:
                f.write(b"BM_WITH_EVENTS")

        capture_result = self.mock_port_rx.video_capturer.capture_result
        capture_result.save_image_to_file.side_effect = write_bmp

        self.server.ScreenshotVideoTester(
            video_pb2.ScreenshotVideoTesterRequest(id=FAKE_SERIAL, id_stream=0),
            self.context,
        )
        self.mock_port_rx._Port__io.set.assert_any_call(0x301, 1)

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

    def test_synchronized_lock_timeout_caps_gpr_inf_future_deadline(
        self,
    ) -> None:
        """Verifies unset gRPC deadline (gpr_inf_future) does not overflow."""
        self.assertIsInstance(self.server._lock, type(threading.RLock()))
        self.assertEqual(self.server._LOCK_TIMEOUT_SEC, 90.0)
        self.mock_tsilib.get_list_of_available_devices.return_value = [
            f"0: UCD-500 [{FAKE_SERIAL}]"
        ]

        inf_future_ctx = mock.MagicMock()
        # grpcio returns INT64_MAX ns (~9223372036.854776s > TIMEOUT_MAX) when
        # a client does not set a gRPC deadline.
        inf_future_ctx.time_remaining.return_value = 9223372036.854776

        _, capped_timeout = ucd_server._get_lock_timeout(
            self.server, (None, inf_future_ctx), {}
        )
        self.assertEqual(capped_timeout, 90.0)

        reply = self.server.GetVideoTesters(None, inf_future_ctx)
        self.assertEqual(len(reply.testers), 1)
        self.assertEqual(reply.testers[0].id, FAKE_SERIAL)

        short_ctx = mock.MagicMock()
        short_ctx.time_remaining.return_value = 12.5
        _, short_timeout = ucd_server._get_lock_timeout(
            self.server, (None, short_ctx), {}
        )
        self.assertEqual(short_timeout, 12.5)

    def test_ucd422_server_inherits_tiered_role_selection(self) -> None:
        """Verifies Ucd422Server uses UcdServer._select_role and binds hdrx."""
        hdmi_server = ucd422.Ucd422Server()
        hdmi_role = mock.MagicMock(spec=UniTAP.dev.UCD422.HDMISourceHDMISink)
        hdmi_role.hdrx = mock.MagicMock()
        hdmi_role.hdrx.video_capturer.status = UniTAP.VideoCaptureStatus.Idle
        self.mock_dev.select_role.side_effect = [
            UniTAP.dev.device.NotExistingRoleSelected("Transient open race"),
            hdmi_role,
        ]
        hdmi_server.OpenVideoTester(
            video_pb2.OpenVideoTesterRequest(id=FAKE_SERIAL), self.context
        )

        reply = hdmi_server.SetRoleVideoTester(
            video_pb2.SetRoleRequest(
                id=FAKE_SERIAL,
                role=video_pb2.ROLE_HDMISOURCE_HDMISINK,
            ),
            self.context,
        )
        self.assertTrue(reply.success)
        self.assertIs(hdmi_server._port_rx, hdmi_role.hdrx)

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

    @mock.patch("ucd.server.time.sleep")
    def test_reopen_after_reset_exhausts_polls_and_raises(
        self, mock_sleep: mock.MagicMock
    ) -> None:
        """Verifies _reopen_after_reset raises after exhausting all polls."""
        del mock_sleep
        booting_dev = mock.MagicMock()
        booting_dev._TSIDevice__role_list = []
        self.mock_tsilib.open.side_effect = [
            RuntimeError("USB not ready"),
            booting_dev,
        ] * 5

        with self.assertRaises(RuntimeError) as ctx:
            self.server._reopen_after_reset(FAKE_SERIAL)

        self.assertIn(
            f"UCD {FAKE_SERIAL} failed to return after USB bounce",
            str(ctx.exception),
        )
        self.assertEqual(self.mock_tsilib.open.call_count, 10)
        self.assertIsNone(self.server._dev)

    @mock.patch("ucd.server.time.sleep")
    def test_hard_reset_and_reopen_continues_when_reset_device_io_raises(
        self, mock_sleep: mock.MagicMock
    ) -> None:
        """Verifies _hard_reset_and_reopen continues if NIOS reset raises."""
        del mock_sleep
        self.server.OpenVideoTester(
            video_pb2.OpenVideoTesterRequest(id=FAKE_SERIAL), self.context
        )
        self.mock_io.reset.side_effect = RuntimeError("NIOS reset timeout")
        self.mock_dev._TSIDevice__role_list = [
            UniTAP.dev.UCD500.USBCSourceUSBCSink
        ]

        with mock.patch.object(
            self.server, "_force_usb_reenumeration", return_value=True
        ) as mock_bounce:
            self.server._hard_reset_and_reopen(FAKE_SERIAL)

        self.mock_io.reset.assert_called_once()
        mock_bounce.assert_called_once_with(FAKE_SERIAL)
        self.assertIs(self.server._dev, self.mock_dev)

    @mock.patch("ucd.server.time.sleep")
    def test_force_usb_reenumeration_success_and_error_branches(
        self, mock_sleep: mock.MagicMock
    ) -> None:
        """Verifies _force_usb_reenumeration ioctl, OSError, and miss."""
        del mock_sleep
        with mock.patch("ucd.server.glob.glob", return_value=[]):
            self.assertFalse(self.server._force_usb_reenumeration(FAKE_SERIAL))

        file_map = {
            "/sys/bus/usb/devices/3-1/serial": f"{FAKE_SERIAL}\n",
            "/sys/bus/usb/devices/3-1/busnum": "3\n",
            "/sys/bus/usb/devices/3-1/devnum": "14\n",
        }

        def fake_open(path, *args, **kwargs):
            del args, kwargs
            if path in file_map:
                return mock.mock_open(read_data=file_map[path])()
            raise FileNotFoundError(path)

        with (
            mock.patch(
                "ucd.server.glob.glob",
                return_value=["/sys/bus/usb/devices/3-1/serial"],
            ),
            mock.patch("builtins.open", side_effect=fake_open),
            mock.patch("ucd.server.os.open", return_value=42) as mock_os_open,
            mock.patch("ucd.server.os.close") as mock_os_close,
            mock.patch(
                "ucd.server.fcntl.ioctl",
                side_effect=OSError("Permission denied"),
            ),
        ):
            self.assertFalse(self.server._force_usb_reenumeration(FAKE_SERIAL))
            mock_os_open.assert_called_once_with(
                "/dev/bus/usb/003/014", os.O_WRONLY
            )
            mock_os_close.assert_called_once_with(42)

        with (
            mock.patch(
                "ucd.server.glob.glob",
                return_value=["/sys/bus/usb/devices/3-1/serial"],
            ),
            mock.patch("builtins.open", side_effect=fake_open),
            mock.patch("ucd.server.os.open", return_value=42),
            mock.patch("ucd.server.os.close") as mock_os_close,
            mock.patch("ucd.server.fcntl.ioctl") as mock_ioctl,
        ):
            self.assertTrue(self.server._force_usb_reenumeration(FAKE_SERIAL))
            mock_ioctl.assert_called_once_with(42, 21780, 0)
            mock_os_close.assert_called_once_with(42)

    @mock.patch("ucd.server.time.sleep")
    def test_power_cycle_role_fallback_when_last_requested_role_is_none(
        self, mock_sleep: mock.MagicMock
    ) -> None:
        """Verifies PowerCycle falls back to self._role.__class__."""
        del mock_sleep
        self._open_and_set_role()
        self.server._role = weakref.proxy(self.mock_role)
        self.server._last_requested_role = None
        self.mock_dev._TSIDevice__role_list = [
            UniTAP.dev.UCD500.USBCSourceUSBCSink
        ]
        self.mock_dev.select_role.reset_mock()

        with (
            mock.patch("ucd.ucd500.UniTAP.OpfHandlerInternal"),
            mock.patch.object(
                self.server, "_force_usb_reenumeration", return_value=True
            ),
        ):
            self.server.PowerCycle(
                video_pb2.PowerCycleRequest(id=FAKE_SERIAL), self.context
            )

        self.mock_dev.select_role.assert_called_once_with(
            self.mock_role.__class__
        )

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

    @mock.patch("ucd.server.time.sleep")
    def test_screenshot_unlatched_timing_and_empty_buffer_or_zero_bmp_branches(
        self, mock_sleep: mock.MagicMock
    ) -> None:
        """Verifies stream bounds, unlatched timing wait, and empty checks."""
        self._open_and_set_role()
        dp_status = self.mock_role.pdcrx.dp_alt_mode.status.dut_dp_alt_mode
        dp_status.dut_connection = "Connected"
        link_caps = self.mock_port_rx.link.capabilities.link_caps_status
        link_caps.return_value.mst = False

        with self.assertRaises(ValueError):
            self.server.ScreenshotVideoTester(
                video_pb2.ScreenshotVideoTesterRequest(
                    id=FAKE_SERIAL, id_stream=99
                ),
                self.context,
            )
        self.context.set_code.assert_called_with(
            grpc.StatusCode.INVALID_ARGUMENT
        )

        # Unlatched timing (0x0) on check 1 latches on check 2 after 0.5s wait,
        # then empty buffer raises.
        unlatched_stream = mock.MagicMock()
        unlatched_stream.video_mode.timing.hactive = 0
        unlatched_stream.video_mode.timing.vactive = 0
        unlatched_stream.video_mode.color_info.bpp = 0

        latched_stream = mock.MagicMock()
        latched_stream.video_mode.timing.hactive = 1920
        latched_stream.video_mode.timing.vactive = 1080
        latched_stream.video_mode.color_info.bpp = 24

        self.mock_port_rx.link.status.stream.side_effect = [
            unlatched_stream,
            latched_stream,
            latched_stream,
        ]
        self.mock_port_rx.video_capturer.capture_result.buffer = []

        with self.assertRaises(RuntimeError) as ctx:
            self.server.ScreenshotVideoTester(
                video_pb2.ScreenshotVideoTesterRequest(
                    id=FAKE_SERIAL, id_stream=0
                ),
                self.context,
            )
        self.assertIn("empty frame buffer", str(ctx.exception))
        mock_sleep.assert_any_call(0.5)

        # 0-byte BMP file raises RuntimeError.
        self.mock_port_rx.link.status.stream.side_effect = None
        self.mock_port_rx.link.status.stream.return_value = latched_stream
        self.mock_port_rx.video_capturer.capture_result.buffer = [object()]
        capture_result = self.mock_port_rx.video_capturer.capture_result
        capture_result.save_image_to_file.side_effect = (
            lambda file_format, path, index: None
        )
        with self.assertRaises(RuntimeError) as ctx2:
            self.server.ScreenshotVideoTester(
                video_pb2.ScreenshotVideoTesterRequest(
                    id=FAKE_SERIAL, id_stream=0
                ),
                self.context,
            )
        self.assertIn("0 bytes", str(ctx2.exception))

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

        # 3. OpenVideoTester when _open_device raises across all recovery polls
        self.mock_tsilib.open.side_effect = RuntimeError("USB open failed")
        with (
            mock.patch("ucd.server.time.sleep"),
            mock.patch.object(
                self.server, "_force_usb_reenumeration", return_value=False
            ),
            self.assertRaises(RuntimeError) as ctx3,
        ):
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

    @mock.patch("ucd.server.time.sleep")
    def test_get_video_testers_read_only_and_targeted_usb_bounce_safety(
        self, mock_sleep: mock.MagicMock
    ) -> None:
        """Verifies GetVideoTesters is read-only and USB bounce is safe."""
        del mock_sleep
        # Case 1: When a handle is open and libTSI hides it from scan_devices,
        # GetVideoTesters stays read-only (does not close _dev or bounce USB)
        # and still includes the open self._serial in the response.
        self._open_and_set_role()
        self.mock_tsilib.close.reset_mock()
        self.mock_tsilib.get_list_of_available_devices.return_value = []
        with mock.patch.object(
            self.server, "_force_usb_reenumeration"
        ) as mock_usb_bounce:
            resp_a = self.server.GetVideoTesters(None, self.context)

        self.assertEqual(len(resp_a.testers), 1)
        self.assertEqual(resp_a.testers[0].id, FAKE_SERIAL)
        self.assertEqual(resp_a.testers[0].name, "UCD-500")
        self.assertIsNotNone(self.server._dev)
        self.mock_tsilib.close.assert_not_called()
        mock_usb_bounce.assert_not_called()

        # Case 2: When closed and 0 devices are found, GetVideoTesters stays
        # read-only and does not trigger USB re-enumeration.
        self.server.CloseVideoTester(
            video_pb2.CloseVideoTesterRequest(id=FAKE_SERIAL), self.context
        )
        self.mock_tsilib.get_list_of_available_devices.return_value = []
        with mock.patch.object(
            self.server, "_force_usb_reenumeration"
        ) as mock_usb_bounce2:
            resp_b = self.server.GetVideoTesters(None, self.context)
        self.assertEqual(len(resp_b.testers), 0)
        mock_usb_bounce2.assert_not_called()

        # Case 3 (Cross-plugin safety): Untargeted _force_usb_reenumeration
        # must NOT reset a USB node when product is missing or mismatches.
        hdmi_server = ucd422.Ucd422Server()
        file_map_no_prod = {
            "/sys/bus/usb/devices/3-1/idVendor": "1992\n",
            "/sys/bus/usb/devices/3-1/busnum": "3\n",
            "/sys/bus/usb/devices/3-1/devnum": "14\n",
        }

        def fake_open_no_prod(path, *args, **kwargs):
            del args, kwargs
            if path in file_map_no_prod:
                return mock.mock_open(read_data=file_map_no_prod[path])()
            raise FileNotFoundError(path)

        with (
            mock.patch(
                "ucd.server.glob.glob",
                return_value=["/sys/bus/usb/devices/3-1/idVendor"],
            ),
            mock.patch("builtins.open", side_effect=fake_open_no_prod),
            mock.patch("ucd.server.os.open") as mock_os_open_cross,
        ):
            self.assertFalse(hdmi_server._force_usb_reenumeration(None))
            mock_os_open_cross.assert_not_called()

        # Case 4 (Shared Satlab host safety): When serial_number is set, the
        # idVendor fallback skips another UCD-500 whose serial is readable and
        # does not match ("9999AAAA"), and only resets the wedged UCD-500
        # whose serial descriptor is unreadable.
        shared_host_files = {
            "/sys/bus/usb/devices/3-1/idVendor": "1992\n",
            "/sys/bus/usb/devices/3-1/serial": "9999AAAA\n",
            "/sys/bus/usb/devices/3-1/product": "UCD-500\n",
            "/sys/bus/usb/devices/3-1/busnum": "3\n",
            "/sys/bus/usb/devices/3-1/devnum": "10\n",
            "/sys/bus/usb/devices/3-2/idVendor": "1992\n",
            "/sys/bus/usb/devices/3-2/product": "UCD-500\n",
            "/sys/bus/usb/devices/3-2/busnum": "3\n",
            "/sys/bus/usb/devices/3-2/devnum": "14\n",
        }

        def fake_open_shared(path, *args, **kwargs):
            del args, kwargs
            if path in shared_host_files:
                return mock.mock_open(read_data=shared_host_files[path])()
            raise FileNotFoundError(path)

        def fake_glob_shared(pattern: str):
            if pattern.endswith("/serial"):
                return ["/sys/bus/usb/devices/3-1/serial"]
            return [
                "/sys/bus/usb/devices/3-1/idVendor",
                "/sys/bus/usb/devices/3-2/idVendor",
            ]

        with (
            mock.patch("ucd.server.glob.glob", side_effect=fake_glob_shared),
            mock.patch("builtins.open", side_effect=fake_open_shared),
            mock.patch(
                "ucd.server.os.open", return_value=42
            ) as mock_os_open_shared,
            mock.patch("ucd.server.os.close"),
            mock.patch("ucd.server.fcntl.ioctl") as mock_ioctl_targeted,
        ):
            self.assertTrue(self.server._force_usb_reenumeration(FAKE_SERIAL))
            mock_os_open_shared.assert_called_once_with(
                "/dev/bus/usb/003/014", os.O_WRONLY
            )
            mock_ioctl_targeted.assert_called_once_with(42, 21780, 0)

    @mock.patch("ucd.server.time.sleep")
    def test_open_video_tester_self_heals_via_hard_reset(
        self, mock_sleep: mock.MagicMock
    ) -> None:
        """Verifies OpenVideoTester runs _hard_reset_and_reopen on failure."""
        del mock_sleep
        ready_dev = self.mock_dev
        ready_dev._TSIDevice__role_list = [UniTAP.dev.UCD500.USBCSourceUSBCSink]

        # 1. Initial _open_device raises RuntimeError -> recovers via hard reset
        self.mock_tsilib.open.side_effect = [
            RuntimeError("Initial open failed"),
            ready_dev,
        ]
        with mock.patch.object(
            self.server, "_force_usb_reenumeration", return_value=True
        ) as mock_bounce:
            reply1 = self.server.OpenVideoTester(
                video_pb2.OpenVideoTesterRequest(id=FAKE_SERIAL), self.context
            )
        self.assertTrue(reply1.success)
        self.assertEqual(self.server._serial, FAKE_SERIAL)
        mock_bounce.assert_called_once_with(FAKE_SERIAL)

        # 2. Initial _open_device returns empty role list -> recovers via reset
        self.server.CloseVideoTester(
            video_pb2.CloseVideoTesterRequest(id=FAKE_SERIAL), self.context
        )
        booting_dev = mock.MagicMock()
        booting_dev._TSIDevice__role_list = []
        self.mock_tsilib.open.side_effect = [
            booting_dev,
            ready_dev,
        ]
        with mock.patch.object(
            self.server, "_force_usb_reenumeration", return_value=True
        ) as mock_bounce2:
            reply2 = self.server.OpenVideoTester(
                video_pb2.OpenVideoTesterRequest(id=FAKE_SERIAL), self.context
            )
        self.assertTrue(reply2.success)
        self.assertIs(self.server._dev, ready_dev)
        mock_bounce2.assert_called_once_with(FAKE_SERIAL)

        # 3. Failed reopen after closing previous session clears _serial & role
        self.server._last_requested_role = UniTAP.dev.UCD500.USBCSourceUSBCSink
        self.mock_tsilib.open.side_effect = RuntimeError("Perm failure")
        with (
            mock.patch.object(
                self.server, "_force_usb_reenumeration", return_value=False
            ),
            self.assertRaises(RuntimeError),
        ):
            self.server.OpenVideoTester(
                video_pb2.OpenVideoTesterRequest(id="OTHER_SERIAL"),
                self.context,
            )
        self.assertIsNone(self.server._serial)
        self.assertIsNone(self.server._last_requested_role)

    @mock.patch("ucd.server.time.sleep")
    def test_screenshot_aborts_failed_precondition_when_dut_stream_inactive(
        self, mock_sleep: mock.MagicMock
    ) -> None:
        """Verifies ScreenshotVideoTester aborts with FAILED_PRECONDITION."""
        self._open_and_set_role()
        mock_sleep.reset_mock()
        dp_status = self.mock_role.pdcrx.dp_alt_mode.status.dut_dp_alt_mode
        dp_status.dut_connection = "Connected"
        link_caps = self.mock_port_rx.link.capabilities.link_caps_status
        link_caps.return_value.mst = False

        stream = self.mock_port_rx.link.status.stream.return_value
        stream.video_mode.timing.hactive = 0
        stream.video_mode.timing.vactive = 0
        stream.video_mode.color_info.bpp = 0
        stream.video_mode.color_info.bpc = 0

        self.mock_port_rx.video_capturer.start.reset_mock()
        reply = self.server.ScreenshotVideoTester(
            video_pb2.ScreenshotVideoTesterRequest(id=FAKE_SERIAL, id_stream=0),
            self.context,
        )

        self.assertEqual(reply.screenshot, b"")
        mock_sleep.assert_called_once_with(0.5)
        self.mock_port_rx.video_capturer.start.assert_not_called()
        self.context.abort.assert_called_once()
        abort_code, abort_msg = self.context.abort.call_args[0]
        self.assertEqual(abort_code, grpc.StatusCode.FAILED_PRECONDITION)
        self.assertIn(
            "DUT is not driving valid video on stream 0"
            " (hactive=0, vactive=0, bpp=0)",
            abort_msg,
        )

        # Case 2: ValueError("Video is not available.") also aborts with
        # FAILED_PRECONDITION.
        self.context.abort.reset_mock()
        self.mock_port_rx.link.status.stream.side_effect = ValueError(
            "Video is not available."
        )
        reply_unavail = self.server.ScreenshotVideoTester(
            video_pb2.ScreenshotVideoTesterRequest(id=FAKE_SERIAL, id_stream=0),
            self.context,
        )
        self.assertEqual(reply_unavail.screenshot, b"")
        self.context.abort.assert_called_once()
        abort_code2, abort_msg2 = self.context.abort.call_args[0]
        self.assertEqual(abort_code2, grpc.StatusCode.FAILED_PRECONDITION)
        self.assertIn("Video is not available.", abort_msg2)
        self.mock_port_rx.link.status.stream.side_effect = None

        # Case 3: When DP Alt Mode is disconnected (0 active streams),
        # ScreenshotVideoTester(id_stream=0) aborts with FAILED_PRECONDITION
        # ("0 active streams") rather than INVALID_ARGUMENT.
        self.context.abort.reset_mock()
        self.context.set_code.reset_mock()
        dp_status.dut_connection = "No connection"
        reply_zero_streams = self.server.ScreenshotVideoTester(
            video_pb2.ScreenshotVideoTesterRequest(id=FAKE_SERIAL, id_stream=0),
            self.context,
        )
        self.assertEqual(reply_zero_streams.screenshot, b"")
        self.context.abort.assert_called_once()
        abort_code3, abort_msg3 = self.context.abort.call_args[0]
        self.assertEqual(abort_code3, grpc.StatusCode.FAILED_PRECONDITION)
        self.assertIn("0 active streams", abort_msg3)
        dp_status.dut_connection = "Connected"

    @mock.patch("ucd.server.time.sleep")
    def test_dsc_stream_zero_bpp_with_valid_bpc_passes_screenshot_and_info(
        self, mock_sleep: mock.MagicMock
    ) -> None:
        """Verifies DSC stream with bpp=0, bpc=8 passes check & StreamInfo."""
        del mock_sleep
        self._open_and_set_role()
        dp_status = self.mock_role.pdcrx.dp_alt_mode.status.dut_dp_alt_mode
        dp_status.dut_connection = "Connected"
        link_caps = self.mock_port_rx.link.capabilities.link_caps_status
        link_caps.return_value.mst = False

        stream = self.mock_port_rx.link.status.stream.return_value
        stream.video_mode.timing.frame_rate = 60
        stream.video_mode.timing.hactive = 3840
        stream.video_mode.timing.vactive = 2160
        stream.video_mode.timing.htotal = 4400
        stream.video_mode.timing.vtotal = 2250
        stream.video_mode.timing.hstart = 384
        stream.video_mode.timing.vstart = 82
        stream.video_mode.timing.hswidth = 88
        stream.video_mode.timing.vswidth = 10
        stream.video_mode.color_info.bpp = 0
        stream.video_mode.color_info.bpc = 8
        stream.video_mode.color_info.color_format = (
            UniTAP.ColorInfo.ColorFormat.CF_DSC
        )
        stream.video_mode.color_info.colorimetry = (
            UniTAP.ColorInfo.Colorimetry.CM_NONE
        )
        stream.video_mode.color_info.dynamic_range = (
            UniTAP.ColorInfo.DynamicRange.DR_VESA
        )
        stream.crc = [0x1111, 0x2222, 0x3333]

        self.mock_port_rx.video_capturer.capture_result.buffer = [object()]

        def write_bmp(file_format, path, index) -> None:
            del file_format, index
            with open(path, "wb") as f:
                f.write(b"BM_DSC_OK")

        capture_result = self.mock_port_rx.video_capturer.capture_result
        capture_result.save_image_to_file.side_effect = write_bmp

        reply = self.server.ScreenshotVideoTester(
            video_pb2.ScreenshotVideoTesterRequest(id=FAKE_SERIAL, id_stream=0),
            self.context,
        )
        self.assertEqual(reply.screenshot, b"BM_DSC_OK")
        self.context.abort.assert_not_called()

        info_resp = self.server.GetStreamInfoVideoTester(
            video_pb2.GetStreamInfoVideoTesterRequest(id=FAKE_SERIAL),
            self.context,
        )
        self.assertEqual(len(info_resp.streams), 1)
        self.assertEqual(info_resp.streams[0].bpp, 24)

        # When MST is configured for 2 sinks (stream_num=2) but the DUT only
        # negotiated 1 stream in link.status, stream(1) raises ValueError("...
        # not available...") and GetStreamInfoVideoTester returns an inactive
        # placeholder entry for stream 1.
        link_caps.return_value.mst = True
        link_caps.return_value.mst_sink_count = 2

        def stream_side_effect(idx: int):
            if idx == 0:
                return stream
            raise ValueError(
                "Selected stream 1 is not available. Available stream"
                " number: 1"
            )

        self.mock_port_rx.link.status.stream.side_effect = stream_side_effect
        mst_info_resp = self.server.GetStreamInfoVideoTester(
            video_pb2.GetStreamInfoVideoTesterRequest(id=FAKE_SERIAL),
            self.context,
        )
        self.assertEqual(len(mst_info_resp.streams), 2)
        self.assertEqual(mst_info_resp.streams[0].hactive, 3840)
        self.assertEqual(mst_info_resp.streams[0].vactive, 2160)
        self.assertEqual(mst_info_resp.streams[0].bpp, 24)
        self.assertEqual(mst_info_resp.streams[1].hactive, 0)
        self.assertEqual(mst_info_resp.streams[1].vactive, 0)
        self.assertEqual(mst_info_resp.streams[1].bpp, 0)
        self.mock_port_rx.link.status.stream.side_effect = None

    def test_set_link_video_tester_2_lane_mode(self) -> None:
        """Verifies SetLinkVideoTester with max_lane=2 sets 2-lane mode."""
        self._open_and_set_role()
        caps = self.mock_port_rx.link.capabilities.link_caps_status.return_value
        dpam_mock = self.mock_role.pdcrx.dp_alt_mode
        pin_caps = mock.MagicMock()
        dpam_mock.ufp_caps = pin_caps

        req = video_pb2.SetLinkVideoTesterRequest(id=FAKE_SERIAL, max_lane=2)
        reply = self.server.SetLinkVideoTester(req, self.context)

        self.assertIsInstance(reply, video_pb2.SetLinkVideoTesterResponse)
        self.assertEqual(caps.max_lane, 2)
        self.mock_port_rx.link.capabilities.set.assert_called_once_with(caps)
        self.assertEqual(pin_caps.c_4_lanes, False)
        self.assertEqual(pin_caps.d_2_lanes, True)
        self.assertEqual(pin_caps.e_4_lanes, False)
        self.assertEqual(dpam_mock.ufp_caps, pin_caps)
        self.assertEqual(dpam_mock.dfp_caps, pin_caps)
        dpam_mock.multifunction_preferred.assert_called_once_with(True)
        dpam_mock.enter_2_lane.assert_called_once()

    def test_set_link_video_tester_4_lane_mode(self) -> None:
        """Verifies SetLinkVideoTester with max_lane=4 sets 4-lane mode."""
        self._open_and_set_role()
        caps = self.mock_port_rx.link.capabilities.link_caps_status.return_value
        dpam_mock = self.mock_role.pdcrx.dp_alt_mode
        pin_caps = mock.MagicMock()
        dpam_mock.ufp_caps = pin_caps

        req = video_pb2.SetLinkVideoTesterRequest(id=FAKE_SERIAL, max_lane=4)
        reply = self.server.SetLinkVideoTester(req, self.context)

        self.assertIsInstance(reply, video_pb2.SetLinkVideoTesterResponse)
        self.assertEqual(caps.max_lane, 4)
        self.mock_port_rx.link.capabilities.set.assert_called_once_with(caps)
        self.assertEqual(pin_caps.c_4_lanes, True)
        self.assertEqual(pin_caps.d_2_lanes, True)
        self.assertEqual(pin_caps.e_4_lanes, False)
        self.assertEqual(dpam_mock.ufp_caps, pin_caps)
        self.assertEqual(dpam_mock.dfp_caps, pin_caps)
        dpam_mock.multifunction_preferred.assert_called_once_with(False)
        dpam_mock.enter_4_lane.assert_called_once()

    def test_set_link_video_tester_pdc_error_logs_warning_and_succeeds(
        self,
    ) -> None:
        """Verifies SetLinkVideoTester succeeds if PDC DP Alt Mode raises."""
        self._open_and_set_role()
        caps = self.mock_port_rx.link.capabilities.link_caps_status.return_value
        dpam_mock = self.mock_role.pdcrx.dp_alt_mode
        dpam_mock.enter_2_lane.side_effect = RuntimeError("PDC timeout")

        req = video_pb2.SetLinkVideoTesterRequest(id=FAKE_SERIAL, max_lane=2)
        with self.assertLogs(level="WARNING") as cm:
            reply = self.server.SetLinkVideoTester(req, self.context)

        self.assertIsInstance(reply, video_pb2.SetLinkVideoTesterResponse)
        self.assertEqual(caps.max_lane, 2)
        self.mock_port_rx.link.capabilities.set.assert_called_once_with(caps)
        self.assertTrue(
            any("Failed to configure PDC DP Alt Mode" in m for m in cm.output)
        )


if __name__ == "__main__":
    unittest.main()
