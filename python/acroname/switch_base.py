# Copyright 2025 The ChromiumOS Authors
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

"""Provides a gRPC server to control ACRONAME switches."""

import abc
import enum
import logging
import typing

# pylint: disable=import-error
import brainstem
from brainstem import result
from chromiumos.test.lab.api.passport import switch_service_pb2 as switch_pb2
from common import log_functionality


# pylint: enable=import-error


class SwitchError(Exception):
    """Errors that occur during switch operations."""


def _check_result(action: typing.Callable[[], []], description: str):
    """Runs an action and checks the Brainstem result.

    Args:
        action: the action to run.
        description: a description of the action being run.
    """
    code = action()
    if code != result.Result.NO_ERROR:
        raise SwitchError(
            f"failed to perform: {description}, error_code: {code}"
        )


class SwitchBase(abc.ABC):
    """Base class for switch controllers."""

    def __init__(self, spec):
        _check_result(
            lambda: self.stem.connect(spec.serial_number), "connect to switch"
        )

    @property
    @abc.abstractmethod
    def supports_flip(self) -> bool:
        """Gets if the module supports USB prot flipping.

        Returns:
            supported: True if the port supports flipping
        """

    @property
    @abc.abstractmethod
    def stem(self) -> brainstem.stem.Module:
        """Gets the brainstem.stem.Module corresponding to the switch.

        Returns:
            stem: The switch brainstem module.
        """

    @property
    @abc.abstractmethod
    def port_count(self) -> int:
        """Gets the number of ports supported by the switch.

        Returns:
            count: The number of ports.
        """

    @log_functionality.logger
    def disable_port(self, port: int) -> None:
        """Disables the specified port.

        Args:
            port: the port to disable.
        """
        _check_result(
            lambda: self.stem.usb.setPortDisable(port),
            "disable port: %s" % port,
        )

    @log_functionality.logger
    def enable_port(self, port: int) -> None:
        """Enables the specified port.

        Args:
            port: the port to enable.
        """
        _check_result(
            lambda: self.stem.usb.setPortEnable(port), "enable port: %s" % port
        )

    @log_functionality.logger
    def flip_port(self, port: int) -> None:
        """Flips the specified port orientation.

        Args:
            port: the port to enable.
        """
        if not self.supports_flip:
            raise SwitchError(
                "Port flipping not supported for this type of switch"
            )

        if self.stem.usb.getCableFlip(port).value == 0:
            _check_result(
                lambda: self.stem.usb.setCableFlip(port, 1),
                "flip port: %s" % port,
            )
        else:
            _check_result(
                lambda: self.stem.usb.setCableFlip(port, 0),
                "unflip port: %s" % port,
            )

    @log_functionality.logger
    def reset(self):
        """Resets all of the switch ports."""
        for port in range(self.port_count):
            self.configure(port, switch_pb2.SWITCH_PORT_DISABLED)

    @log_functionality.logger
    def configure(self, port: int, state: switch_pb2.SwitchPortState):
        """Configures a single switch port.

        Args:
            port: the port to configure.
            state: the state to set the port to.
        """
        if state == switch_pb2.SwitchPortState.SWITCH_PORT_DISABLED:
            self.disable_port(port)
        elif state == switch_pb2.SwitchPortState.SWITCH_PORT_ENABLED:
            self.enable_port(port)
        elif state == switch_pb2.SwitchPortState.SWITCH_PORT_FLIP:
            self.flip_port(port)
        else:
            raise ValueError(f"unknown switch state: {state}")

    @log_functionality.logger
    def close(self):
        try:
            self.stem.disconnect()
        except Exception as e:
            logging.error("failed to disconnect module: %s", e)


class USBHub2x4(SwitchBase):
    """Controller for USBHub2x4 Brainstem module."""

    _stem = None

    @property
    def supports_flip(self) -> bool:
        """Gets if the module supports USB prot flipping.

        Returns:
            supported: True if the port supports flipping
        """
        return False

    @property
    def stem(self) -> brainstem.stem.Module:
        """Gets the brainstem.stem.Module corresponding to the switch.

        Returns:
            stem: The switch brainstem module.
        """
        if not self._stem:
            self._stem = brainstem.stem.USBHub2x4()
        return self._stem

    @property
    def port_count(self) -> int:
        """Gets the number of ports supported by the switch.

        Returns:
            count: The number of ports.
        """
        return 4


class USBHub3p(SwitchBase):
    """Controller for USBHub3b Brainstem module."""

    _stem = None

    @property
    def supports_flip(self) -> bool:
        """Gets if the module supports USB prot flipping.

        Returns:
            supported: True if the port supports flipping
        """
        return False

    @property
    def stem(self) -> brainstem.stem.Module:
        """Gets the brainstem.stem.Module corresponding to the switch.

        Returns:
            stem: The switch brainstem module.
        """
        if not self._stem:
            self._stem = brainstem.stem.USBHub3p()
        return self._stem

    @property
    def port_count(self) -> int:
        """Gets the number of ports supported by the switch.

        Returns:
            count: The number of ports.
        """
        return 8


class USBHub3c(SwitchBase):
    """Controller for USBHub3c Brainstem module."""

    _stem = None

    @property
    def supports_flip(self) -> bool:
        """Gets if the module supports USB prot flipping.

        Returns:
            supported: True if the port supports flipping
        """
        return False

    @property
    def stem(self) -> brainstem.stem.Module:
        """Gets the brainstem.stem.Module corresponding to the switch.

        Returns:
            stem: The switch brainstem module.
        """
        if not self._stem:
            self._stem = brainstem.stem.USBHub3c()
        return self._stem

    @property
    def port_count(self) -> int:
        """Gets the number of ports supported by the switch.

        Returns:
            count: The number of ports.
        """
        return 6

    @log_functionality.logger
    def disable_port(self, port: int) -> None:
        """Disables the specified port.

        Args:
            port: the port to disable.
        """
        _check_result(
            lambda: self.stem.hub.port[port].setEnabled(0),
            "disable port: %s" % port,
        )

    @log_functionality.logger
    def enable_port(self, port: int) -> None:
        """Enables the specified port.

        Args:
            port: the port to enable.
        """
        _check_result(
            lambda: self.stem.hub.port[port].setEnabled(1),
            "enable port: %s" % port,
        )


class USBCSwitch(SwitchBase):
    """Controller for USBCSwitch Brainstem module."""

    _stem = None

    @property
    def supports_flip(self) -> bool:
        """Gets if the module supports USB prot flipping.

        Returns:
            supported: True if the port supports flipping
        """
        return True

    @property
    def stem(self) -> brainstem.stem.Module:
        """Gets the brainstem.stem.Module corresponding to the switch.

        Returns:
            stem: The switch brainstem module.
        """
        if not self._stem:
            self._stem = brainstem.stem.USBCSwitch()
        return self._stem

    @property
    def port_count(self) -> int:
        """Gets the number of ports supported by the switch.

        Returns:
            count: The number of ports.
        """
        return 4

    @log_functionality.logger
    def disable_port(self, port: int) -> None:
        """Disables the specified port.

        Args:
            port: the port to disable.
        """
        _check_result(lambda: self.stem.usb.setPortDisable(0), "disable port")
        _check_result(lambda: self.stem.mux.setEnable(False), "disable mux")
        _check_result(lambda: self.stem.mux.setChannel(0), "reset mux channel")

    @log_functionality.logger
    def enable_port(self, port: int) -> None:
        """Enables the specified port.

        Args:
            port: the port to enable.
        """
        # Disable, set the new channel, and then enable.
        # Note port 0 is the "common" port that feeds to the upstream device.
        self.disable_port(port)
        _check_result(lambda: self.stem.mux.setChannel(port), "set mux channel")
        _check_result(lambda: self.stem.usb.setPortEnable(0), "enable port")
        _check_result(lambda: self.stem.mux.setEnable(True), "enable mux")


class BrainstemType(enum.Enum):
    """Supported Brainstem modules."""

    USBHub2x4 = 17
    USBHub3p = 19
    USBCSwitch = 21
    USBHub3c = 24


_MODEL_TO_CLASS = {
    BrainstemType.USBHub2x4: USBHub2x4,
    BrainstemType.USBHub3p: USBHub3p,
    BrainstemType.USBHub3c: USBHub3c,
    BrainstemType.USBCSwitch: USBCSwitch,
}


def create_switch_controller(spec: brainstem.link.Spec) -> SwitchBase:
    """Creates the correct switch controller for the brainstem module spec.

    Args:
        spec: Brainstem module spec to create a controller for.

    Returns:
        The SwitchBase controller to use.
    """
    model = BrainstemType(spec.model)
    if model in _MODEL_TO_CLASS:
        return _MODEL_TO_CLASS[model](spec)
    raise SwitchError(f"unknown switch type: {spec.model}")
