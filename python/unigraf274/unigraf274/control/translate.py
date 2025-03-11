# Copyright 2025 The ChromiumOS Authors
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.
from chromiumos.test.lab.api.passport import usb_tester_service_pb2

SDK_F_MAP = {
    usb_tester_service_pb2.PIN_ASSIGMENT: [
        "dp_pin_assigment",
        "update_dp_pin_assigment",
        "select_dp_pin_assigment",
    ],
    usb_tester_service_pb2.USB_CHANNEL: [
        "usb_channel",
        "update_usb_channel",
        "select_usb_channel",
    ],
    usb_tester_service_pb2.POWER_ROLE: [
        "power_role",
        "update_power_role",
        "select_power_role",
    ],
    usb_tester_service_pb2.DATA_ROLE: [
        "data_role",
        "update_data_role",
        "select_data_role",
    ],
    usb_tester_service_pb2.ACTIVE_CC: [
        "active_cc",
        "update_active_cc",
        "select_active_cc",
    ],
    usb_tester_service_pb2.CABLE_MODE: [
        "cable_mode",
        "update_cable_mode",
        "select_cable_mode",
    ],
    usb_tester_service_pb2.INIT_PD_STATE: [
        "init_pd_state",
        "update_init_pd_state",
        "select_init_pd_state",
    ],
    usb_tester_service_pb2.CURRENT_LOAD: [
        "current_load",
        "update_current_load",
        "select_current_load",
    ],
    usb_tester_service_pb2.SRC_PULL_UP: [
        "src_pull_up",
        "update_src_pull_up",
        "select_src_pull_up",
    ],
    usb_tester_service_pb2.SNK_PDO_COUNT: [
        "snk_pdo_count",
        "update_snk_pdo_count",
        "select_snk_pdo_count",
    ],
    usb_tester_service_pb2.SRC_PDO_COUNT: [
        "src_pdo_count",
        "update_src_pdo_count",
        "select_src_pdo_count",
    ],
    usb_tester_service_pb2.VBUS_VOLTAGE: [
        "vbus_voltage",
        "update_vbus_voltage",
        "select_vbus_voltage",
    ],
    usb_tester_service_pb2.VBUS_CURRENT: [
        "vbus_current",
        "update_vbus_current",
        "select_vbus_current",
    ],
    usb_tester_service_pb2.VBUS_CURRENT_LANE: [
        "vbus_current_lane",
        "update_vbus_current_lane",
        "select_vbus_current_lane",
    ],
    usb_tester_service_pb2.GND_CURRENT_LANE: [
        "gnd_current_lane",
        "update_gnd_current_lane",
        "select_gnd_current_lane",
    ],
    usb_tester_service_pb2.VBUS_EPU_VOLTAGE: [
        "vbus_epu_voltage",
        "update_vbus_epu_voltage",
        "select_vbus_epu_voltage",
    ],
    usb_tester_service_pb2.VBUS_CC1: [
        "vbus_cc1",
        "update_vbus_cc1",
        "select_vbus_cc1",
    ],
    usb_tester_service_pb2.VBUS_CC2: [
        "vbus_cc2",
        "update_vbus_cc2",
        "select_vbus_cc2",
    ],
    usb_tester_service_pb2.VBUS_SBU1: [
        "vbus_sbu1",
        "update_vbus_sbu1",
        "select_vbus_sbu1",
    ],
    usb_tester_service_pb2.VBUS_SBU2: [
        "vbus_sbu2",
        "update_vbus_sbu2",
        "select_vbus_sbu2",
    ],
}

CAPABILITY_RETURN_FIELD_MAP = {
    usb_tester_service_pb2.PIN_ASSIGMENT: "pin_mode",
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
}

DISCRETE_CAPABILITIES = [
    usb_tester_service_pb2.ACTIVE_CC,
    usb_tester_service_pb2.PIN_ASSIGMENT,
    usb_tester_service_pb2.USB_CHANNEL,
    usb_tester_service_pb2.POWER_ROLE,
    usb_tester_service_pb2.DATA_ROLE,
    usb_tester_service_pb2.ACTIVE_CC,
    usb_tester_service_pb2.CABLE_MODE,
    usb_tester_service_pb2.INIT_PD_STATE,
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
]

# The values in this map are taken from the user manual,
# section 6, pages 26 to 32.
GRCP_CAPABILITY_SDK_VALUE_MAP_GRCP_VALUE = {
    (usb_tester_service_pb2.ACTIVE_CC, 0): usb_tester_service_pb2.CC1,
    (usb_tester_service_pb2.ACTIVE_CC, 1): usb_tester_service_pb2.CC2,
    (usb_tester_service_pb2.PIN_ASSIGMENT, 0): usb_tester_service_pb2.C,
    (usb_tester_service_pb2.PIN_ASSIGMENT, 1): usb_tester_service_pb2.D,
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
}

# The values in this map are taken from the user manual,
# section 6, pages 26 to 32.
GRCP_CAPABILITY_VALUE_MAP_SDK_VALUE = {
    (usb_tester_service_pb2.ACTIVE_CC, usb_tester_service_pb2.CC1): 0,
    (usb_tester_service_pb2.ACTIVE_CC, usb_tester_service_pb2.CC2): 1,
    (usb_tester_service_pb2.PIN_ASSIGMENT, usb_tester_service_pb2.C): 0,
    (usb_tester_service_pb2.PIN_ASSIGMENT, usb_tester_service_pb2.D): 1,
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
}


def sdk_capability_to_reply_set_member(capability):
    # Tester capability should always be associated with a return field.
    # If somehow we get an unknown request, we return nothig, this will cause
    # an exception in the get function.
    if capability not in CAPABILITY_RETURN_FIELD_MAP:
        return None

    return CAPABILITY_RETURN_FIELD_MAP[capability]


def grcp_set_val_to_sdk_set_val(request):
    """This function is just the opposite of `sdk_get_val_to_grcp_get_val`"""

    value = getattr(request, request.WhichOneof("value"))

    if (request.capability, value) in GRCP_CAPABILITY_VALUE_MAP_SDK_VALUE:
        return GRCP_CAPABILITY_VALUE_MAP_SDK_VALUE[(request.capability, value)]

    if request.capability in DISCRETE_CAPABILITIES:
        raise Exception(
            f"unknown value or bad value ({value}) when attempting to convert"
        )

    return value


def sdk_get_val_to_grcp_get_val(capability, value):
    """This function will attempt to makp a `capability` and a SDK `value`
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
    """This function will attempt to map a SDK value and a set field name
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
