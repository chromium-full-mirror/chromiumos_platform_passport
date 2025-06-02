# Copyright 2025 The ChromiumOS Authors
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.


import argparse
import logging
import unittest

from chromiumos.test.lab.api.passport import (
    video_tester_service_pb2 as video_pb2,
)
from chromiumos.test.lab.api.passport import (
    video_tester_service_pb2_grpc as video_pb2_grpc,
)
import grpc


# Configure logging for informative output during test execution.
logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")
logger = logging.getLogger(__name__)

DEFAULT_SERVER_ADDRESS = "localhost:8300"


class TestVideoTesterGetters(unittest.TestCase):
    server_address: str = DEFAULT_SERVER_ADDRESS
    channel: grpc.Channel | None = None
    stub: video_pb2_grpc.VideoTesterServiceStub | None = None
    tester_id: str | None = None

    @classmethod
    def setUpClass(cls):
        logger.info(
            "Connecting to server at %s for test setup...", cls.server_address
        )
        try:
            cls.channel = grpc.insecure_channel(cls.server_address)
            cls.stub = video_pb2_grpc.VideoTesterServiceStub(cls.channel)

            devices = cls.stub.GetVideoTesters(
                video_pb2.GetVideoTestersRequest()
            )
            logger.info("Discovered testers: %s", devices)
            if not devices.testers:
                raise unittest.skipTest(
                    "No video testers found. Skipping all tests."
                )
            cls.tester_id = devices.testers[0].id
            logger.info("Using tester ID: %s", cls.tester_id)

            open_response = cls.stub.OpenVideoTester(
                video_pb2.OpenVideoTesterRequest(id=cls.tester_id)
            )
            logger.info("Opened tester '%s': %s", cls.tester_id, open_response)

            role_response = cls.stub.SetRoleVideoTester(
                video_pb2.SetRoleRequest(
                    id=cls.tester_id,
                    role=video_pb2.Role.ROLE_USBCSOURCE_USBCSINK,
                )
            )
            logger.info("Role response: %s", role_response)
        except grpc.RpcError as e:
            logger.error("gRPC setup failed: %s", e.details())
            raise unittest.skipTest(
                "Failed to connect or open tester: %s" % e.details()
            )
        except Exception as e:
            logger.error("Unexpected error during setup: %s", e)
            raise unittest.skipTest("Unexpected error during setup: %s" % e)

    @classmethod
    def tearDownClass(cls):
        if not cls.stub:
            return
        if not cls.tester_id:
            return

        try:
            close_response = cls.stub.CloseVideoTester(
                video_pb2.CloseVideoTesterRequest(
                    id=cls.tester_id,
                )
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

    def test_get_roles_video_tester(self):
        """
        Tests the GetRolesVideoTester RPC.
        Verifies that supported roles are returned and include the role set during setup.
        """
        request = video_pb2.GetRolesRequest(id=self.tester_id)
        response = self.stub.GetRolesVideoTester(request)
        self.assertIsNotNone(
            response, "Response from GetRolesVideoTester should not be None"
        )
        self.assertGreater(
            len(response.roles), 0, "Expected at least one role to be supported"
        )
        # Check if the role we set in setup is present
        self.assertIn(
            video_pb2.Role.ROLE_USBCSOURCE_USBCSINK,
            response.roles,
            "Expected ROLE_USBCSOURCE_USBCSINK to be among supported roles",
        )
        logger.info(
            "GetRolesVideoTester successful. Supported roles: %s",
            [video_pb2.Role.Name(r) for r in response.roles],
        )

    def test_get_stream_info_video_tester(self):
        """
        Tests the GetStreamInfoVideoTester RPC.
        Verifies that stream information is returned (though specific values
        might depend on the active video signal).
        """
        self.stub.GetStreamInfoVideoTester(
            video_pb2.GetStreamInfoVideoTesterRequest(id=self.tester_id)
        )

    def test_get_link_video_tester(self):
        """
        Tests the GetLinkVideoTester RPC.
        Verifies that link parameters are returned.
        """
        request = video_pb2.GetLinkVideoTesterRequest(id=self.tester_id)
        response = self.stub.GetLinkVideoTester(request)
        self.assertIsNotNone(
            response, "Response from GetLinkVideoTester should not be None"
        )


if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="Run video tester capability tests using unittest."  # Changed description
    )

    parser.add_argument(
        "--server_address",
        type=str,
        default=DEFAULT_SERVER_ADDRESS,
        help="The address of the gRPC server (e.g., 'localhost:8300'). "
        "Defaults to '%s'." % DEFAULT_SERVER_ADDRESS,
    )

    args, unknown_args = parser.parse_known_args()

    TestVideoTesterGetters.server_address = args.server_address

    suite = unittest.TestSuite()
    suite.addTest(unittest.makeSuite(TestVideoTesterGetters))

    runner = unittest.runner.TextTestRunner(verbosity=2)
    runner.run(suite)
