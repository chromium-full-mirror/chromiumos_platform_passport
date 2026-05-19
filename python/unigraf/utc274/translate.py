# Copyright 2025 The ChromiumOS Authors
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

"""Convert between values.

This module translated between the SDK values used by the unigraf and the
gRPC values.
"""

from enum import Enum

# pylint: disable=import-error
from chromiumos.test.lab.api.passport import usb_tester_service_pb2

from utils import constants


# pylint: enable=import-error


SDK_F_MAP = {
    usb_tester_service_pb2.PIN_ASSIGNMENT: [
        "pd.update_dp_pin_assignment",
        "pd.select_dp_pin_assignment",
    ],
    usb_tester_service_pb2.USB_CHANNEL: [
        "pd.update_usb_channel",
        "pd.select_usb_channel",
    ],
    usb_tester_service_pb2.POWER_ROLE: [
        "pd.update_power_role",
        "pd.select_power_role",
    ],
    usb_tester_service_pb2.DATA_ROLE: [
        "pd.update_data_role",
        "pd.select_data_role",
    ],
    usb_tester_service_pb2.ACTIVE_CC: [
        "pd.update_active_cc",
        "pd.select_active_cc",
    ],
    usb_tester_service_pb2.CABLE_MODE: [
        "pd.update_cable_mode",
        "pd.select_cable_mode",
    ],
    usb_tester_service_pb2.INIT_PD_STATE: [
        "pd.update_init_pd_state",
        "pd.select_init_pd_state",
    ],
    usb_tester_service_pb2.CURRENT_LOAD: [
        "pd.update_current_load",
        "pd.select_current_load",
    ],
    usb_tester_service_pb2.SRC_PULL_UP: [
        "pd.update_src_pull_up",
        "pd.select_src_pull_up",
    ],
    usb_tester_service_pb2.SNK_PDO_COUNT: [
        "pd.update_snk_pdo_count",
        "pd.select_snk_pdo_count",
    ],
    usb_tester_service_pb2.SRC_PDO_COUNT: [
        "pd.update_src_pdo_count",
        "pd.select_src_pdo_count",
    ],
    usb_tester_service_pb2.VBUS_VOLTAGE: [
        "pd.update_vbus_voltage",
        "pd.select_vbus_voltage",
    ],
    usb_tester_service_pb2.VBUS_CURRENT: [
        "pd.update_vbus_current",
        "pd.select_vbus_current",
    ],
    usb_tester_service_pb2.VBUS_CURRENT_LANE: [
        "pd.update_vbus_per_lane_deviation",
        "pd.select_vbus_per_lane_deviation",
    ],
    usb_tester_service_pb2.GND_CURRENT_LANE: [
        "pd.update_gnd_per_lane_deviation",
        "pd.select_gnd_per_lane_deviation",
    ],
    usb_tester_service_pb2.VBUS_EPU_VOLTAGE: [
        "pd.update_vbus_epu_voltage",
        "pd.select_vbus_epu_voltage",
    ],
    usb_tester_service_pb2.VBUS_CC1: [
        "pd.update_cc1_voltage",
        "pd.select_cc1_voltage",
    ],
    usb_tester_service_pb2.VBUS_CC2: [
        "pd.update_cc2_voltage",
        "pd.select_cc2_voltage",
    ],
    usb_tester_service_pb2.VBUS_SBU1: [
        "pd.update_sbu1_voltage",
        "pd.select_sbu1_voltage",
    ],
    usb_tester_service_pb2.VBUS_SBU2: [
        "pd.update_sbu2_voltage",
        "pd.select_sbu2_voltage",
    ],
    usb_tester_service_pb2.POWER_SWAP_POLICY: [
        "pd.update_power_role_swap_policy",
        "pd.select_power_role_swap_policy",
    ],
    usb_tester_service_pb2.DATA_SWAP_POLICY: [
        "pd.update_data_role_swap_policy",
        "pd.select_data_role_swap_policy",
    ],
    usb_tester_service_pb2.VCONN_SWAP_POLICY: [
        "pd.update_vconn_swap_policy",
        "pd.select_vconn_swap_policy",
    ],
    usb_tester_service_pb2.CONSTRAINED_POWER: [
        "hw.update_unconstrained_power_cap",
        "hw.select_unconstrained_power_cap",
    ],
    usb_tester_service_pb2.POWER_DELIVERY: [
        "hw.update_pd_cap",
        "hw.select_pd_cap",
    ],
    usb_tester_service_pb2.DISPLAY_PORT_AM: [
        "hw.update_dp_alt_mode_cap",
        "hw.select_dp_alt_mode_cap",
    ],
    usb_tester_service_pb2.USB_PATH: [
        "hw.update_usb_path",
        "hw.select_usb_path",
    ],
    usb_tester_service_pb2.TRY_BEHAVIOUR: [
        "pd.update_try_behavior",
        "pd.select_try_behavior",
    ],
    usb_tester_service_pb2.NON_PD_CURRENT: [
        "pd.update_nonpd_current_load",
        "pd.select_nonpd_current_load",
    ],
}

SELECT_SAFETY_DELAY_S_FMAP = {
    usb_tester_service_pb2.ACTIVE_CC: 3,
    usb_tester_service_pb2.INIT_PD_STATE: 3,
    usb_tester_service_pb2.POWER_DELIVERY: 3,
    usb_tester_service_pb2.DISPLAY_PORT_AM: 3,
}

CAPABILITY_RETURN_FIELD_MAP = {
    usb_tester_service_pb2.PIN_ASSIGNMENT: "pin_mode",
    usb_tester_service_pb2.USB_CHANNEL: "usb_channel",
    usb_tester_service_pb2.POWER_ROLE: "power_role",
    usb_tester_service_pb2.DATA_ROLE: "data_role",
    usb_tester_service_pb2.ACTIVE_CC: "active_cc",
    usb_tester_service_pb2.CABLE_MODE: "cable_mode",
    usb_tester_service_pb2.INIT_PD_STATE: "init_pd_state",
    usb_tester_service_pb2.CURRENT_LOAD: "non_descrete",
    usb_tester_service_pb2.SRC_PULL_UP: "non_descrete",
    usb_tester_service_pb2.SNK_PDO_COUNT: "non_descrete",
    usb_tester_service_pb2.SRC_PDO_COUNT: "non_descrete",
    usb_tester_service_pb2.VBUS_VOLTAGE: "non_descrete",
    usb_tester_service_pb2.VBUS_CURRENT: "non_descrete",
    usb_tester_service_pb2.VBUS_CURRENT_LANE: "non_descrete",
    usb_tester_service_pb2.GND_CURRENT_LANE: "non_descrete",
    usb_tester_service_pb2.VBUS_EPU_VOLTAGE: "non_descrete",
    usb_tester_service_pb2.VBUS_CC1: "non_descrete",
    usb_tester_service_pb2.VBUS_CC2: "non_descrete",
    usb_tester_service_pb2.VBUS_SBU1: "non_descrete",
    usb_tester_service_pb2.VBUS_SBU2: "non_descrete",
    usb_tester_service_pb2.DATA_SWAP_POLICY: "data_role_swap_policy",
    usb_tester_service_pb2.POWER_SWAP_POLICY: "power_role_swap_policy",
    usb_tester_service_pb2.VCONN_SWAP_POLICY: "vconn_swap_policy",
    usb_tester_service_pb2.CONSTRAINED_POWER: "constrained_power",
    usb_tester_service_pb2.POWER_DELIVERY: "power_delivery",
    usb_tester_service_pb2.DISPLAY_PORT_AM: "display_port_am",
    usb_tester_service_pb2.USB_PATH: "usb_path",
    usb_tester_service_pb2.TRY_BEHAVIOUR: "try_behaviour",
    usb_tester_service_pb2.NON_PD_CURRENT: "non_descrete",
}

DISCRETE_CAPABILITIES = [
    usb_tester_service_pb2.ACTIVE_CC,
    usb_tester_service_pb2.PIN_ASSIGNMENT,
    usb_tester_service_pb2.USB_CHANNEL,
    usb_tester_service_pb2.POWER_ROLE,
    usb_tester_service_pb2.DATA_ROLE,
    usb_tester_service_pb2.ACTIVE_CC,
    usb_tester_service_pb2.CABLE_MODE,
    usb_tester_service_pb2.INIT_PD_STATE,
    # The following are also discrete values but they use the bool type
    usb_tester_service_pb2.DATA_SWAP_POLICY,
    usb_tester_service_pb2.POWER_SWAP_POLICY,
    usb_tester_service_pb2.VCONN_SWAP_POLICY,
    usb_tester_service_pb2.CONSTRAINED_POWER,
    usb_tester_service_pb2.POWER_DELIVERY,
    usb_tester_service_pb2.DISPLAY_PORT_AM,
    usb_tester_service_pb2.USB_PATH,
    usb_tester_service_pb2.TRY_BEHAVIOUR,
]

NON_DISCRETE_CAPABILITIES = [
    usb_tester_service_pb2.CURRENT_LOAD,
    usb_tester_service_pb2.SRC_PULL_UP,
    usb_tester_service_pb2.SNK_PDO_COUNT,
    usb_tester_service_pb2.SRC_PDO_COUNT,
    usb_tester_service_pb2.VBUS_VOLTAGE,
    usb_tester_service_pb2.VBUS_CURRENT,
    usb_tester_service_pb2.VBUS_CURRENT_LANE,
    usb_tester_service_pb2.GND_CURRENT_LANE,
    usb_tester_service_pb2.VBUS_EPU_VOLTAGE,
    usb_tester_service_pb2.VBUS_CC1,
    usb_tester_service_pb2.VBUS_CC2,
    usb_tester_service_pb2.VBUS_SBU1,
    usb_tester_service_pb2.VBUS_SBU2,
    usb_tester_service_pb2.NON_PD_CURRENT,
]

# The values in this map are taken from the user manual,
# section 6, pages 26 to 32.
GRCP_CAPABILITY_SDK_VALUE_MAP_GRCP_VALUE = {
    (usb_tester_service_pb2.ACTIVE_CC, 0): usb_tester_service_pb2.CC1,
    (usb_tester_service_pb2.ACTIVE_CC, 1): usb_tester_service_pb2.CC2,
    (usb_tester_service_pb2.PIN_ASSIGNMENT, 0): usb_tester_service_pb2.C,
    (usb_tester_service_pb2.PIN_ASSIGNMENT, 1): usb_tester_service_pb2.D,
    (usb_tester_service_pb2.PIN_ASSIGNMENT, 2): usb_tester_service_pb2.E,
    (usb_tester_service_pb2.USB_CHANNEL, 0): usb_tester_service_pb2.USB_2_HS,
    (
        usb_tester_service_pb2.USB_CHANNEL,
        1,
    ): usb_tester_service_pb2.USB_3_AND_2_HS,
    (usb_tester_service_pb2.POWER_ROLE, 0): usb_tester_service_pb2.SNK,
    (usb_tester_service_pb2.POWER_ROLE, 1): usb_tester_service_pb2.SRC,
    (usb_tester_service_pb2.DATA_ROLE, 0): usb_tester_service_pb2.DATA_UFP,
    (usb_tester_service_pb2.DATA_ROLE, 1): usb_tester_service_pb2.DATA_DFP,
    (usb_tester_service_pb2.CABLE_MODE, 0): usb_tester_service_pb2.NORMAL,
    (usb_tester_service_pb2.CABLE_MODE, 1): usb_tester_service_pb2.ELEC_TEST,
    (usb_tester_service_pb2.INIT_PD_STATE, 0): usb_tester_service_pb2.PD_UFP,
    (usb_tester_service_pb2.INIT_PD_STATE, 1): usb_tester_service_pb2.PD_DFP,
    (usb_tester_service_pb2.INIT_PD_STATE, 2): usb_tester_service_pb2.PD_DRP,
    (
        usb_tester_service_pb2.DATA_SWAP_POLICY,
        0,
    ): usb_tester_service_pb2.PD_SWAP_POLICY_ALLOW,
    (
        usb_tester_service_pb2.DATA_SWAP_POLICY,
        1,
    ): usb_tester_service_pb2.PD_SWAP_POLICY_REJECT,
    (
        usb_tester_service_pb2.DATA_SWAP_POLICY,
        2,
    ): usb_tester_service_pb2.PD_SWAP_POLICY_WAIT,
    (
        usb_tester_service_pb2.POWER_SWAP_POLICY,
        0,
    ): usb_tester_service_pb2.PD_SWAP_POLICY_ALLOW,
    (
        usb_tester_service_pb2.POWER_SWAP_POLICY,
        1,
    ): usb_tester_service_pb2.PD_SWAP_POLICY_REJECT,
    (
        usb_tester_service_pb2.POWER_SWAP_POLICY,
        2,
    ): usb_tester_service_pb2.PD_SWAP_POLICY_WAIT,
    (
        usb_tester_service_pb2.VCONN_SWAP_POLICY,
        0,
    ): usb_tester_service_pb2.PD_SWAP_POLICY_ALLOW,
    (
        usb_tester_service_pb2.VCONN_SWAP_POLICY,
        1,
    ): usb_tester_service_pb2.PD_SWAP_POLICY_REJECT,
    (usb_tester_service_pb2.CONSTRAINED_POWER, 1): True,
    (usb_tester_service_pb2.CONSTRAINED_POWER, 0): False,
    (usb_tester_service_pb2.POWER_DELIVERY, 1): True,
    (usb_tester_service_pb2.POWER_DELIVERY, 0): False,
    (usb_tester_service_pb2.DISPLAY_PORT_AM, 1): True,
    (usb_tester_service_pb2.DISPLAY_PORT_AM, 0): False,
    (
        usb_tester_service_pb2.USB_PATH,
        0,
    ): usb_tester_service_pb2.USB_PATH_INTERNAL,
    (
        usb_tester_service_pb2.USB_PATH,
        1,
    ): usb_tester_service_pb2.USB_PATH_EXTERNAL,
    (
        usb_tester_service_pb2.TRY_BEHAVIOUR,
        0,
    ): usb_tester_service_pb2.TRY_BEHAVIOUR_NOT_SET,
    (usb_tester_service_pb2.TRY_BEHAVIOUR, 1): usb_tester_service_pb2.TRY_SNK,
    (usb_tester_service_pb2.TRY_BEHAVIOUR, 2): usb_tester_service_pb2.TRY_SRC,
}

# The values in this map are taken from the user manual,
# section 6, pages 26 to 32.
GRCP_CAPABILITY_VALUE_MAP_SDK_VALUE = {
    (usb_tester_service_pb2.ACTIVE_CC, usb_tester_service_pb2.CC1): 2,
    (usb_tester_service_pb2.ACTIVE_CC, usb_tester_service_pb2.CC2): 3,
    (usb_tester_service_pb2.PIN_ASSIGNMENT, usb_tester_service_pb2.C): 0,
    (usb_tester_service_pb2.PIN_ASSIGNMENT, usb_tester_service_pb2.D): 1,
    (usb_tester_service_pb2.PIN_ASSIGNMENT, usb_tester_service_pb2.E): 2,
    (usb_tester_service_pb2.USB_CHANNEL, usb_tester_service_pb2.USB_2_HS): 0,
    (
        usb_tester_service_pb2.USB_CHANNEL,
        usb_tester_service_pb2.USB_3_AND_2_HS,
    ): 1,
    (usb_tester_service_pb2.POWER_ROLE, usb_tester_service_pb2.SNK): 0,
    (usb_tester_service_pb2.POWER_ROLE, usb_tester_service_pb2.SRC): 1,
    (usb_tester_service_pb2.DATA_ROLE, usb_tester_service_pb2.DATA_UFP): 0,
    (usb_tester_service_pb2.DATA_ROLE, usb_tester_service_pb2.DATA_DFP): 1,
    (usb_tester_service_pb2.CABLE_MODE, usb_tester_service_pb2.NORMAL): 0,
    (usb_tester_service_pb2.CABLE_MODE, usb_tester_service_pb2.ELEC_TEST): 1,
    (usb_tester_service_pb2.INIT_PD_STATE, usb_tester_service_pb2.PD_UFP): 0,
    (usb_tester_service_pb2.INIT_PD_STATE, usb_tester_service_pb2.PD_DFP): 1,
    (usb_tester_service_pb2.INIT_PD_STATE, usb_tester_service_pb2.PD_DRP): 2,
    (
        usb_tester_service_pb2.DATA_SWAP_POLICY,
        usb_tester_service_pb2.PD_SWAP_POLICY_ALLOW,
    ): 0,
    (
        usb_tester_service_pb2.DATA_SWAP_POLICY,
        usb_tester_service_pb2.PD_SWAP_POLICY_REJECT,
    ): 1,
    (
        usb_tester_service_pb2.DATA_SWAP_POLICY,
        usb_tester_service_pb2.PD_SWAP_POLICY_WAIT,
    ): 2,
    (
        usb_tester_service_pb2.POWER_SWAP_POLICY,
        usb_tester_service_pb2.PD_SWAP_POLICY_ALLOW,
    ): 0,
    (
        usb_tester_service_pb2.POWER_SWAP_POLICY,
        usb_tester_service_pb2.PD_SWAP_POLICY_REJECT,
    ): 1,
    (
        usb_tester_service_pb2.POWER_SWAP_POLICY,
        usb_tester_service_pb2.PD_SWAP_POLICY_WAIT,
    ): 2,
    (
        usb_tester_service_pb2.VCONN_SWAP_POLICY,
        usb_tester_service_pb2.PD_SWAP_POLICY_ALLOW,
    ): 0,
    (
        usb_tester_service_pb2.VCONN_SWAP_POLICY,
        usb_tester_service_pb2.PD_SWAP_POLICY_REJECT,
    ): 1,
    (usb_tester_service_pb2.CONSTRAINED_POWER, True): 1,
    (usb_tester_service_pb2.CONSTRAINED_POWER, False): 0,
    (usb_tester_service_pb2.POWER_DELIVERY, True): 1,
    (usb_tester_service_pb2.POWER_DELIVERY, False): 0,
    (usb_tester_service_pb2.DISPLAY_PORT_AM, True): 1,
    (usb_tester_service_pb2.DISPLAY_PORT_AM, False): 0,
    (
        usb_tester_service_pb2.USB_PATH,
        usb_tester_service_pb2.USB_PATH_INTERNAL,
    ): 0,
    (
        usb_tester_service_pb2.USB_PATH,
        usb_tester_service_pb2.USB_PATH_EXTERNAL,
    ): 1,
    (
        usb_tester_service_pb2.TRY_BEHAVIOUR,
        usb_tester_service_pb2.TRY_BEHAVIOUR_NOT_SET,
    ): 0,
    (usb_tester_service_pb2.TRY_BEHAVIOUR, usb_tester_service_pb2.TRY_SNK): 1,
    (usb_tester_service_pb2.TRY_BEHAVIOUR, usb_tester_service_pb2.TRY_SRC): 2,
}

# Map to convert the PD alert type in gRPC to the SDK value.
GRCP_ALERT_TO_SDK_ALERT = {
    usb_tester_service_pb2.PD_ALERT_PB_RELEASE: 0,
    usb_tester_service_pb2.PD_ALERT_PB_PRESS: 1,
}


# Enum type to indicate the type of PD swaps for stats.
class PdSwapType(Enum):
    ACCEPT = 0
    REJECT = 1
    WAIT = 2


def sdk_capability_to_reply_set_member(capability):
    # Tester capability should always be associated with a return field.
    # If somehow we get an unknown request, we return nothig, this will cause
    # an exception in the get function.
    if capability not in CAPABILITY_RETURN_FIELD_MAP:
        return None

    return CAPABILITY_RETURN_FIELD_MAP[capability]


def grcp_set_val_to_sdk_set_val(request):
    """Translate between gRPC values and SDK values.

    This function is just the opposite of `sdk_get_val_to_grcp_get_val`
    """

    value = getattr(request, request.WhichOneof("value"))

    if (request.capability, value) in GRCP_CAPABILITY_VALUE_MAP_SDK_VALUE:
        return GRCP_CAPABILITY_VALUE_MAP_SDK_VALUE[(request.capability, value)]

    if request.capability in DISCRETE_CAPABILITIES:
        raise Exception(
            f"unknown value or bad value ({value}) when attempting to convert"
        )

    return value


def sdk_get_val_to_grcp_get_val(capability, value):
    """Translate between SDK values and gRPC values.

    This function will attempt to makp a `capability` and a SDK `value`
    to the corresponding value in the gRPC interface. Only discrete have a
    corresponding SDK value. For non-discretes, the value is returned as is.
    """

    if (capability, value) in GRCP_CAPABILITY_SDK_VALUE_MAP_GRCP_VALUE:
        return GRCP_CAPABILITY_SDK_VALUE_MAP_GRCP_VALUE[(capability, value)]

    if capability in DISCRETE_CAPABILITIES:
        raise Exception(
            f"unknown value or bad value ({value}) when attempting to convert"
        )

    return value


SDK_DP_INFO_VALUE_MAP_GRCP_VALUE = {
    ("link_rate", 0): usb_tester_service_pb2.RBR,
    ("link_rate", 1): usb_tester_service_pb2.HBR,
    ("link_rate", 2): usb_tester_service_pb2.HBR2,
    ("link_rate", 3): usb_tester_service_pb2.HBR3,
    ("color_depth", 0): usb_tester_service_pb2.BIT6,
    ("color_depth", 1): usb_tester_service_pb2.BIT8,
    ("color_depth", 2): usb_tester_service_pb2.BIT10,
    ("color_depth", 3): usb_tester_service_pb2.BIT12,
    ("color_depth", 4): usb_tester_service_pb2.BIT16,
    ("color_mode", 0): usb_tester_service_pb2.RGB,
    ("color_mode", 1): usb_tester_service_pb2.YCBCR444,
    ("color_mode", 2): usb_tester_service_pb2.YCBCR422,
    ("color_mode", 3): usb_tester_service_pb2.YCBCR420,
}

DP_INFO_SET_MEMBERS = ["color_depth", "color_mode", "link_rate"]


def sdk_dp_info_value_map_grcp_value(field_name, sdk_val):
    """Translate between SDK values and gRPC values.

    This function will attempt to map a SDK value and a set field name
    for the display port information to the gRPC set of values.
    """

    # The members that are not enum based are the same as in the SDK.
    if field_name not in DP_INFO_SET_MEMBERS:
        return sdk_val

    k = (field_name, sdk_val)
    if k not in SDK_DP_INFO_VALUE_MAP_GRCP_VALUE:
        raise Exception(
            f"unknown value or bad value ({k}) when attempting to convert"
        )

    return SDK_DP_INFO_VALUE_MAP_GRCP_VALUE[k]
