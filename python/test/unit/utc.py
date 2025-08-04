# Copyright 2025 The ChromiumOS Authors
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.
from __future__ import annotations

import contextlib
import threading
from typing import Generator
import unittest
import unittest.mock

from chromiumos.test.lab.api.passport import usb_tester_service_pb2

# Correctly import the server module and protobuf definitions
from utc274 import server


# --- Constants for clarity and easy modification ---
FAKE_SERIAL_UTC = "12345678"
FAKE_SERIAL_UCD = "SER002"
UTC_DEVICE_NAME = "UTC-274"
UCD_DEVICE_NAME = "UCD-500"


class TestUnigrafServer(unittest.TestCase):
    """Test suite for the UnigrafServer gRPC service."""

    server: server.UnigrafServer
    mock_utclib_instance: unittest.mock.MagicMock
    mock_device: unittest.mock.MagicMock

    @unittest.mock.patch("utc274.server.UTCLibrary.UTCLib")
    def setUp(self, mock_utclib: unittest.mock.MagicMock) -> None:
        """Set up a fresh UnigrafServer instance and mocks for each test."""
        self.mock_utclib_instance = mock_utclib.return_value
        self.mock_utclib_instance.devices_name_list.return_value = [
            (UTC_DEVICE_NAME, False, FAKE_SERIAL_UTC)
        ]

        # The mock device that `open_device` will return
        self.mock_device = unittest.mock.MagicMock()
        self.mock_utclib_instance.open_device.return_value = self.mock_device

        # Instantiate the server, which calls devices_name_list
        self.server = server.UnigrafServer()

    @contextlib.contextmanager
    def _open_tester_context(self, serial: str) -> Generator[None, None, None]:
        """A context manager to safely open and close a tester for a test."""
        # Setup: Open the device
        open_request = usb_tester_service_pb2.OpenTesterRequest(id=serial)
        self.server.OpenTester(open_request, None)
        try:
            # Yield to the test
            yield
        finally:
            # Teardown: Close the device
            close_request = usb_tester_service_pb2.CloseTesterRequest(id=serial)
            self.server.CloseTester(close_request, None)

    def test_init(self) -> None:
        """Test that the server initializes correctly."""
        self.mock_utclib_instance.devices_name_list.assert_called_once()
        self.assertEqual(self.server._raw_device[0][2], FAKE_SERIAL_UTC)

    def test_get_testers_pure_utc(self) -> None:
        """Test GetTesters with a single UTC device."""
        request = usb_tester_service_pb2.GetTestersRequest()
        reply = self.server.GetTesters(request, None)

        self.assertEqual(len(reply.testers), 1)
        self.assertEqual(reply.testers[0].id, FAKE_SERIAL_UTC)
        self.assertEqual(reply.testers[0].name, UTC_DEVICE_NAME)

    def test_get_testers_filters_non_utc_devices(self) -> None:
        """Test GetTesters filters out non-UTC devices."""
        self.mock_utclib_instance.devices_name_list.return_value = [
            (UTC_DEVICE_NAME, True, FAKE_SERIAL_UTC),
            (UCD_DEVICE_NAME, False, FAKE_SERIAL_UCD),
        ]
        request = usb_tester_service_pb2.GetTestersRequest()
        reply = self.server.GetTesters(request, None)

        self.assertEqual(len(reply.testers), 1)
        self.assertEqual(reply.testers[0].id, FAKE_SERIAL_UTC)

    def test_open_tester_success(self) -> None:
        """Test that opening a tester succeeds and creates necessary locks."""
        request = usb_tester_service_pb2.OpenTesterRequest(id=FAKE_SERIAL_UTC)
        reply = self.server.OpenTester(request, None)

        self.mock_utclib_instance.open_device.assert_called_once_with(
            serial_number=FAKE_SERIAL_UTC
        )
        self.assertIn(FAKE_SERIAL_UTC, self.server._open_devices)
        self.assertIsInstance(
            self.server._serial_locks[FAKE_SERIAL_UTC], type(threading.Lock())
        )
        self.assertEqual(reply.err_code, 0)

    def test_open_tester_already_open_raises_error(self) -> None:
        """Test that opening an already open tester raises ProcessLookupError."""
        self.server._open_devices[FAKE_SERIAL_UTC] = self.mock_device
        request = usb_tester_service_pb2.OpenTesterRequest(id=FAKE_SERIAL_UTC)

        with self.assertRaises(ProcessLookupError):
            self.server.OpenTester(request, None)

    def test_close_tester_success(self) -> None:
        """Test that closing an open tester succeeds."""
        # First, open it
        self.server.OpenTester(
            usb_tester_service_pb2.OpenTesterRequest(id=FAKE_SERIAL_UTC), None
        )
        self.assertIn(FAKE_SERIAL_UTC, self.server._open_devices)

        # Now, test closing it
        request = usb_tester_service_pb2.CloseTesterRequest(id=FAKE_SERIAL_UTC)
        reply = self.server.CloseTester(request, None)

        self.mock_utclib_instance.close_device.assert_called_once_with(
            serial_num=FAKE_SERIAL_UTC
        )
        self.assertNotIn(FAKE_SERIAL_UTC, self.server._open_devices)
        self.assertNotIn(FAKE_SERIAL_UTC, self.server._serial_locks)
        self.assertEqual(reply.err_code, 0)

    def test_close_tester_not_open_raises_error(self) -> None:
        """Test that closing a tester that isn't open raises ProcessLookupError."""
        request = usb_tester_service_pb2.CloseTesterRequest(
            id="NOT_OPEN_SERIAL"
        )

        with self.assertRaises(ProcessLookupError):
            self.server.CloseTester(request, None)

    def test_get_tester_capability_success(self) -> None:
        """Test getting a capability from an open tester."""
        self.mock_device.pd.power_role.return_value = 0  # Represents SNK

        with self._open_tester_context(FAKE_SERIAL_UTC):
            request = usb_tester_service_pb2.GetUsbTesterCapabilityRequest(
                id=FAKE_SERIAL_UTC,
                capability=usb_tester_service_pb2.POWER_ROLE,
            )
            reply = self.server.GetTesterCapability(request, None)

            self.mock_device.pd.update_power_role.assert_called_once()
            self.mock_device.pd.power_role.assert_called_once()
            self.assertEqual(reply.err_code, 0)
            self.assertEqual(reply.power_role, usb_tester_service_pb2.SNK)

    def test_replug_cable_failure(self) -> None:
        """Test a failed cable replug reports an error."""
        self.mock_device.pd.replug.return_value = -1

        with self._open_tester_context(FAKE_SERIAL_UTC):
            request = usb_tester_service_pb2.DoCableReplugRequest(
                id=FAKE_SERIAL_UTC
            )
            reply = self.server.ReplugCable(request, None)

            self.mock_device.pd.replug.assert_called_once()
            self.assertEqual(reply.err_code, -1)
            self.assertIn("failed", reply.error_msg)

    @unittest.mock.patch("utc274.server.tempfile.NamedTemporaryFile")
    def test_load_edid(self, mock_tempfile):
        """Test loading an EDID file."""
        mock_file = unittest.mock.MagicMock()
        mock_file.name = "/tmp/fake_edid.bin"
        mock_tempfile.return_value = mock_file

        self.server.OpenTester(
            usb_tester_service_pb2.OpenTesterRequest(id=FAKE_SERIAL_UTC), None
        )
        self.mock_device.hw.load_edid.return_value = 0

        edid_data = b"\x00\xff\xff\x00"
        request = usb_tester_service_pb2.LoadEdidRequest(
            id=FAKE_SERIAL_UTC, edid=edid_data
        )

        with unittest.mock.patch(
            "builtins.open", unittest.mock.mock_open()
        ) as mock_builtin_open:
            reply = self.server.LoadEdid(request, None)
            mock_builtin_open.assert_called_once_with(mock_file.name, "wb")
            handle = mock_builtin_open()
            handle.write.assert_called_once_with(edid_data)

        self.mock_device.hw.load_edid.assert_called_once_with(mock_file.name)
        self.assertEqual(reply.err_code, 0)


if __name__ == "__main__":
    unittest.main()
