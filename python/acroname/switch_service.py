# Copyright 2025 The ChromiumOS Authors
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

"""Provides a gRPC server to control ACRONAME switches."""

import atexit
import logging

from acroname import switch_base

# pylint: disable=import-error
import brainstem
from chromiumos.test.lab.api.passport import (
    switch_service_pb2_grpc as switch_pb2_grpc,
)
from chromiumos.test.lab.api.passport import switch_service_pb2 as switch_pb2
from common import log_functionality


# pylint: enable=import-error


class SwitchService(switch_pb2_grpc.SwitchServiceServicer):
    """Implements the PassPort gRPC APIs for controlling Brainstem switches."""

    @log_functionality.logger
    def __init__(self):
        self._switches = {}

        atexit.register(self.__del__)
        logging.info("Init Brainstem Switch Server")

    @log_functionality.logger
    def GetSwitches(self, request, context):  # pylint: disable=W0613
        """Probes all known switches connected to the system."""
        res = switch_pb2.GetSwitchesResponse()
        for spec in brainstem.discover.findAllModules(brainstem.link.Spec.USB):
            serial = str(spec.serial_number)
            logging.info("found switch: %s", serial)
            res.switches.append(switch_pb2.SwitchFixture(id=serial))

            if serial not in self._switches:
                self._switches[serial] = switch_base.create_switch_controller(
                    spec
                )

        return res

    @log_functionality.logger
    def ResetAllSwitches(self, request, context):  # pylint: disable=W0613
        """Re-initializes all switches and sets them to "disabled" state."""
        for switch in self.GetSwitches(None, context).switches:
            logging.info("resetting switch: %s", switch.id)
            self._switches[switch.id].reset()

        return switch_pb2.ResetAllSwitchesResponse()

    @log_functionality.logger
    def ConfigureSwitchPort(self, request, context):  # pylint: disable=W0613
        """Configures a single port on a switch."""
        self.GetSwitches(None, context)
        if request.switch_id not in self._switches:
            raise ValueError(f"unknown switch id: {request.switch_id}")

        if request.port_id == "":
            logging.warning("Port ID is empty, defaulting to 0")
            port = 0
        elif request.port_id.isdigit():
            port = int(request.port_id)
        else:
            raise ValueError(f"invalid switch port ID {request.port_id}")

        self._switches[request.switch_id].configure(port, request.state)

        return switch_pb2.ConfigureSwitchPortResponse()

    def __del__(self):
        for switch in self._switches.values():
            switch.close()
        self._switches = {}
