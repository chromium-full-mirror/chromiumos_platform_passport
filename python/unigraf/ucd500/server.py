# Copyright 2025 The ChromiumOS Authors
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

"""Provides a gRPC server to control Unigraf video testing hardware.

This module implements the VideoTesterService gRPC service, allowing clients
to discover, open, close, and configure Unigraf UCD-500 series video testers
using the UniTAP library.
"""

import atexit
import logging
import re

# pylint: disable=import-error
from chromiumos.test.lab.api.passport import (
    video_tester_service_pb2 as video_pb2,
)
from chromiumos.test.lab.api.passport import (
    video_tester_service_pb2_grpc as video_pb2_grpc,
)
import grpc
import UniTAP

from utils import log_functionality


# pylint: enable=import-error


class UnigrafServer(video_pb2_grpc.VideoTesterServiceServicer):
    """Implements the gRPC service for controlling Unigraf video testers.

    This class provides methods to discover, open, close, and configure
    Unigraf UCD-500 series video testing devices. It uses the UniTAP library
    to interact with the hardware.
    """

    @log_functionality.logger
    def __init__(self):
        self._dev = None
        self._serial = None
        self._role = None

        self._tsilib = UniTAP.TsiLib()
        atexit.register(self.__del__)

        logging.info("VideoTesterServiceServicer init done")

    @log_functionality.logger
    def GetVideoTesters(self, _, context):
        """Retrieves a list of available video testers."""

        testers = self._tsilib.get_list_of_available_devices()
        ret = []
        # Output of `get_list_of_available_devices` is of the form
        # ['0: UCD-500 [xxxxxxx]', '1: UCD-500 [xxxxx]']
        # where the number between the square brackets is the device serial.
        for tester in testers:
            serials = re.findall(r"\[([^]]*)\]", tester)
            if len(serials) != 1:
                logging.error("Serial parsing is malformed %s", tester)
                context.set_code(grpc.StatusCode.INTERNAL)
                context.set_details("Serial parsing is malformed")
                raise RuntimeError("Serial parsing is malformed!")

            ret.append(
                video_pb2.VideoTester(
                    id=serials[0],
                    name="UCD-500",
                )
            )

        return video_pb2.GetVideoTestersResponse(testers=ret)

    @log_functionality.logger
    def OpenVideoTester(self, request, context):
        """Opens a specific video tester for interaction."""

        try:
            self._dev = self._tsilib.open(request.id)
        except Exception as e:
            context.set_code(grpc.StatusCode.INTERNAL)
            raise RuntimeError(f"Failed to open device: {e}")

        self._serial = request.id

        return video_pb2.OpenVideoTesterResponse(success=True)

    @log_functionality.logger
    def CloseVideoTester(self, request, _):
        """Closes an opened video tester."""

        if request.id != self._serial:
            raise RuntimeError(
                f"Serials dont match, got {request.id} expected {self._serial}"
            )

        if self._dev is None:
            raise RuntimeError(f"Serial {request.id} was never open")

        self._tsilib.close(self._dev)

        return video_pb2.CloseVideoTesterResponse(success=True)

    @log_functionality.logger
    def SetRoleVideoTester(self, request, _):
        """Selects a specific role for a given video tester."""

        if request.id != self._serial:
            raise RuntimeError(
                f"Serials dont match, got {request.id} expected {self._serial}"
            )

        roles = {
            video_pb2.ROLE_DPSOURCE_USBCSINK: UniTAP.dev.UCD500.DPSourceUSBCSink,
            video_pb2.ROLE_DPSOURCE_DPSINK: UniTAP.dev.UCD500.DPSourceDPSink,
            video_pb2.ROLE_USBCSOURCE_USBCSINK: UniTAP.dev.UCD500.USBCSourceUSBCSink,
            video_pb2.ROLE_USBCSOURCE_DPSINK: UniTAP.dev.UCD500.USBCSourceDPSink,
        }

        if request.role not in roles:
            raise RuntimeError(f"Role is unknwon {request.role}")

        self._role = self._dev.select_role(roles[request.role])

        return video_pb2.SetRoleResponse(success=True)

    @log_functionality.logger
    def __del__(self):
        logging.info("Delete function will ran")
        if self._dev is not None:
            self._tsilib.close(self._dev)
        self._tsilib.cleanup()
