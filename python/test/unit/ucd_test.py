# Copyright 2026 The ChromiumOS Authors
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

"""Unit tests for UcdServer and Ucd500Server."""

from __future__ import annotations

import enum
import sys
import types
import unittest
from unittest import mock


# Provide lightweight fallback modules when running without grpc or PIL
try:
    import grpc  # pylint: disable=unused-import
except ModuleNotFoundError:
    grpc_stub = types.ModuleType("grpc")

    class _StatusCode(enum.Enum):
        OK = 0
        INVALID_ARGUMENT = 3
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

# pylint: disable=wrong-import-position,import-error
from chromiumos.test.lab.api.passport import (
    video_tester_service_pb2 as video_pb2,
)
import grpc
from ucd import ucd500
import UniTAP


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
    """Unit test suite for UcdServer and Ucd500Server."""

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
        dp_source_role = mock.MagicMock(
            spec=UniTAP.dev.UCD500.DPSourceUSBCSink
        )
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


if __name__ == "__main__":
    unittest.main()
