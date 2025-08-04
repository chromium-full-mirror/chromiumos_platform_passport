# Copyright 2025 The ChromiumOS Authors
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

"""Integration tests for the Acroname SwitchService."""

import argparse
import logging
import time
import unittest

from chromiumos.test.lab.api.passport import (
    switch_service_pb2_grpc as switch_pb2_grpc,
)
from chromiumos.test.lab.api.passport import switch_service_pb2 as switch_pb2
import grpc


# Configure logging for informative output during test execution.
logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")
logger = logging.getLogger(__name__)

DEFAULT_SERVER_ADDRESS = "localhost:8300"


class TestSwitchServiceActions(unittest.TestCase):
    """Test case for exercising the SwitchService gRPC endpoints."""

    server_address: str = DEFAULT_SERVER_ADDRESS
    channel: grpc.Channel | None = None
    stub: switch_pb2_grpc.SwitchServiceStub | None = None
    switch_id: str | None = None

    @classmethod
    def setUpClass(cls):
        """Set up the gRPC connection and discover a switch for testing."""
        logger.info(
            "Connecting to server at %s for test setup...", cls.server_address
        )
        try:
            cls.channel = grpc.insecure_channel(cls.server_address)
            cls.stub = switch_pb2_grpc.SwitchServiceStub(cls.channel)

            # Discover available switches.
            get_switches_response = cls.stub.GetSwitches(
                switch_pb2.GetSwitchesRequest()
            )
            logger.info(
                "Discovered switches: %s", get_switches_response.switches
            )
            if not get_switches_response.switches:
                raise unittest.SkipTest(
                    "No switches found. Skipping all tests."
                )

            # Select the first switch for testing.
            cls.switch_id = get_switches_response.switches[0].id
            logger.info("Using switch ID: %s", cls.switch_id)

        except grpc.RpcError as e:
            logger.error("gRPC setup failed: %s", e.details())
            raise unittest.SkipTest(
                f"Failed to connect or find a switch: {e.details()}"
            )
        except Exception as e:
            logger.error("Unexpected error during setup: %s", e)
            raise unittest.SkipTest(f"Unexpected error during setup: {e}")

    @classmethod
    def tearDownClass(cls):
        """Close the gRPC channel."""
        if cls.channel:
            cls.channel.close()
            logger.info("gRPC channel closed.")

    def test_enable_port(self):
        """Tests enabling a switch port."""
        self.assertIsNotNone(self.stub, "gRPC stub not initialized.")
        self.assertIsNotNone(self.switch_id, "Switch ID not set.")

        logger.info("Enabling port 0 on switch %s...", self.switch_id)
        configure_request_enable = switch_pb2.ConfigureSwitchPortRequest(
            switch_id=self.switch_id,
            port_id="0",
            state=switch_pb2.SwitchPortState.SWITCH_PORT_ENABLED,
        )
        self.stub.ConfigureSwitchPort(configure_request_enable)
        logger.info("Port 0 enabled.")
        time.sleep(1)  # Wait a moment for the action to complete.

    def test_disable_port(self):
        """Tests disabling a switch port."""
        self.assertIsNotNone(self.stub, "gRPC stub not initialized.")
        self.assertIsNotNone(self.switch_id, "Switch ID not set.")

        logger.info("Disabling port 0 on switch %s...", self.switch_id)
        configure_request_disable = switch_pb2.ConfigureSwitchPortRequest(
            switch_id=self.switch_id,
            port_id="0",
            state=switch_pb2.SwitchPortState.SWITCH_PORT_DISABLED,
        )
        self.stub.ConfigureSwitchPort(configure_request_disable)
        logger.info("Port 0 disabled.")
        time.sleep(1)

    def test_reset_all_switches(self):
        """Tests resetting all switches."""
        self.assertIsNotNone(self.stub, "gRPC stub not initialized.")

        logger.info("Resetting all switches...")
        self.stub.ResetAllSwitches(switch_pb2.ResetAllSwitchesRequest())
        logger.info("All switches reset.")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="Run SwitchService action tests using unittest."
    )
    parser.add_argument(
        "--server_address",
        type=str,
        default=DEFAULT_SERVER_ADDRESS,
        help=f"The gRPC server address (e.g., 'localhost:8301'). "
        f"Defaults to '{DEFAULT_SERVER_ADDRESS}'.",
    )
    args, unknown_args = parser.parse_known_args()

    TestSwitchServiceActions.server_address = args.server_address

    # Pass remaining args to unittest.
    unittest.main(argv=[__file__] + unknown_args)
