# Copyright 2025 The ChromiumOS Authors
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

"""This script provides a unittest-based test suite for a USB tester.

This script provides a unittest-based test suite for a USB tester interacting
with it via a gRPC service. It includes individual tests for various
capabilities and information retrieval methods, ensuring granular test
reporting.
"""

import argparse
import logging
import time
import unittest

from chromiumos.test.lab.api.passport import (
    usb_tester_service_pb2_grpc as usb_pb2_grpc,
)
from chromiumos.test.lab.api.passport import usb_tester_service_pb2 as usb_pb2
import grpc


# Configure logging for informative output during test execution.
logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")
logger = logging.getLogger(__name__)

DEFAULT_SERVER_ADDRESS = "localhost:8300"
CAPABILITIES_TO_TEST = [
    usb_pb2.PIN_ASSIGNMENT,
    usb_pb2.USB_CHANNEL,
    usb_pb2.POWER_ROLE,
    usb_pb2.DATA_ROLE,
    usb_pb2.ACTIVE_CC,
    usb_pb2.CABLE_MODE,
    usb_pb2.INIT_PD_STATE,
    usb_pb2.CURRENT_LOAD,
    usb_pb2.SRC_PULL_UP,
    usb_pb2.SNK_PDO_COUNT,
    usb_pb2.SRC_PDO_COUNT,
    usb_pb2.VBUS_VOLTAGE,
    usb_pb2.VBUS_CURRENT,
    usb_pb2.VBUS_CURRENT_LANE,
    usb_pb2.GND_CURRENT_LANE,
    usb_pb2.VBUS_EPU_VOLTAGE,
    usb_pb2.VBUS_CC1,
    usb_pb2.VBUS_CC2,
    usb_pb2.VBUS_SBU1,
    usb_pb2.VBUS_SBU2,
    usb_pb2.POWER_SWAP_POLICY,
    usb_pb2.DATA_SWAP_POLICY,
    usb_pb2.VCONN_SWAP_POLICY,
    usb_pb2.CONSTRAINED_POWER,
    usb_pb2.POWER_DELIVERY,
    usb_pb2.DISPLAY_PORT_AM,
    usb_pb2.TRY_BEHAVIOUR,
    usb_pb2.NON_PD_CURRENT,
]


class UsbTesterIntegrationTestBase(unittest.TestCase):
    """Base class for USB tester integration tests."""

    server_address: str = DEFAULT_SERVER_ADDRESS
    channel: grpc.Channel | None = None
    stub: usb_pb2_grpc.UsbTesterServiceStub | None = None
    tester_id: str | None = None

    @classmethod
    def setUpClass(cls):
        logger.info(
            "Connecting to server at %s for test setup...", cls.server_address
        )
        try:
            cls.channel = grpc.insecure_channel(cls.server_address)
            cls.stub = usb_pb2_grpc.UsbTesterServiceStub(cls.channel)

            devices = cls.stub.GetTesters(usb_pb2.GetTestersRequest())
            logger.info("Discovered testers: %s", devices)
            if not devices.testers:
                raise unittest.SkipTest(
                    "No USB testers found. Skipping all tests."
                )
            cls.tester_id = devices.testers[0].id
            logger.info("Using tester ID: %s", cls.tester_id)

            open_response = cls.stub.OpenTester(
                usb_pb2.OpenTesterRequest(id=cls.tester_id)
            )
            logger.info("Opened tester '%s': %s", cls.tester_id, open_response)

        except grpc.RpcError as e:
            logger.error("gRPC setup failed: %s", e.details())
            raise unittest.SkipTest(
                "Failed to connect or open tester: %s" % e.details()
            )
        except Exception as e:
            logger.error("Unexpected error during setup: %s", e)
            raise unittest.SkipTest("Unexpected error during setup: %s" % e)

    @classmethod
    def tearDownClass(cls):
        if not cls.stub:
            return
        if not cls.tester_id:
            return

        try:
            close_response = cls.stub.CloseTester(
                usb_pb2.CloseTesterRequest(id=cls.tester_id)
            )
            logger.info("Closed tester '%s': %s", cls.tester_id, close_response)
        except grpc.RpcError as e:
            logger.warning(
                "Failed to close tester '%s': %s", cls.tester_id, e.details()
            )
        except Exception as e:
            logger.warning("Unexpected error during tester close: %s", e)

        if cls.channel:
            cls.channel.close()
            logger.info("gRPC channel closed.")


class TestUsbTesterGetters(UsbTesterIntegrationTestBase):
    """Test suite for getter methods of the USB tester service."""

    def test_get_dp_info(self):
        self.stub.GetDpInfo(usb_pb2.GetDpInfoRequest(id=self.tester_id))

    def test_get_pdos(self):
        self.stub.GetPdos(usb_pb2.GetPdosRequest(id=self.tester_id))

    def test_get_active_port(self):
        self.stub.GetActivePort(usb_pb2.GetActivePortRequest(id=self.tester_id))


class TestUsbTesterActions(UsbTesterIntegrationTestBase):
    """Test suite for action/command methods of the USB tester service."""

    def test_send_vdm_hpd(self):
        """Tests the SendVdmHpd method."""
        self.stub.SendVdmHpd(
            usb_pb2.SendVdmHpdRequest(
                id=self.tester_id, vdm_hpd=usb_pb2.VDM_HPD_IRQ
            )
        )

    def test_simulate_key_press(self):
        """Tests the SimulateKeyPress method."""
        self.stub.SimulateKeyPress(
            usb_pb2.SimulateKeyPressRequest(id=self.tester_id)
        )

    def test_port_stress(self):
        """Tests the SetActivePort method by switching between ports.

        This test iterates 20 times, switching between port 0 and 1,
        and toggling the port state (ON/OFF) to simulate stress testing
        on the USB tester ports.
        """
        for i in range(0, 20):
            self.stub.SetActivePort(
                usb_pb2.SetActivePortRequest(
                    id=self.tester_id,
                    port_id=i % 2,
                    state=(
                        usb_pb2.PORT_STATE_ON
                        if i % 3
                        else usb_pb2.PORT_STATE_OFF
                    ),
                )
            )


def _create_capability_test_method(capability_enum_value):
    cap_name = usb_pb2.Capability.Name(capability_enum_value)

    def test_method(self):
        self.stub.GetTesterCapability(
            usb_pb2.GetUsbTesterCapabilityRequest(
                id=self.tester_id,
                capability=capability_enum_value,
            )
        )

    test_method.__name__ = "test_get_capability_%s" % cap_name.lower()
    return test_method


for cap_enum in CAPABILITIES_TO_TEST:
    setattr(
        TestUsbTesterGetters,
        "test_get_capability_%s" % usb_pb2.Capability.Name(cap_enum).lower(),
        _create_capability_test_method(cap_enum),
    )

if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="Run a USB tester capability test using unittest."
    )

    parser.add_argument(
        "--server_address",
        type=str,
        default=DEFAULT_SERVER_ADDRESS,
        help="The address of the gRPC server (e.g., 'localhost:8300'). "
        "Defaults to '%s'." % DEFAULT_SERVER_ADDRESS,
    )

    args, unknown_args = parser.parse_known_args()

    UsbTesterIntegrationTestBase.server_address = args.server_address

    # Create a TestLoader and discover tests from the test classes.
    loader = unittest.TestLoader()
    suite = unittest.TestSuite(
        [
            loader.loadTestsFromTestCase(TestUsbTesterGetters),
            loader.loadTestsFromTestCase(TestUsbTesterActions),
        ]
    )

    # Use TextTestRunner with verbosity=2
    runner = unittest.runner.TextTestRunner(verbosity=2)
    runner.run(suite)
