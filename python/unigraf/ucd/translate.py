# Copyright 2025 The ChromiumOS Authors
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

"""Translate values to and from gRPC to UCD500 specific values."""

# Copyright 2025 The ChromiumOS Authors
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

# pylint: disable=import-error
from chromiumos.test.lab.api.passport import (
    video_tester_service_pb2 as video_pb2,
)
import UniTAP
from UniTAP.dev.modules.dut_tests.dut_default_params import (
    dp_1_4_source_general_tab,
)


# pylint: enable=import-error
UCD_ROLES = {
    video_pb2.ROLE_HDMISOURCE_HDMISINK: UniTAP.dev.UCD422.HDMISourceHDMISink,
    video_pb2.ROLE_DPSOURCE_USBCSINK: UniTAP.dev.UCD500.DPSourceUSBCSink,
    video_pb2.ROLE_DPSOURCE_DPSINK: UniTAP.dev.UCD500.DPSourceDPSink,
    video_pb2.ROLE_USBCSOURCE_USBCSINK: UniTAP.dev.UCD500.USBCSourceUSBCSink,
    video_pb2.ROLE_USBCSOURCE_DPSINK: UniTAP.dev.UCD500.USBCSourceDPSink,
}

TEST_UNITAP_TO_GRPC = {
    0: video_pb2.COMPLIANCE_TEST_PASSED,
    1: video_pb2.COMPLIANCE_TEST_FAILED,
    2: video_pb2.COMPLIANCE_TEST_SKIPPED,
    3: video_pb2.COMPLIANCE_TEST_ABORTED,
}

INTEL_COMMON_PARAMS_CTS_DUT_SRC = {
    "default": {
        "general.timeout": 5000,
        "general.hpd_pulse_duration": 1000,
        "general.dut_caps.max_lanes": 4,
        "general.dut_caps.max_link_rate": 8.1,
        "general.dut_caps.dut_caps_flags.voltage_swing_supported": True,
        "general.dut_caps.dut_caps_flags.pre_emphasis_supported": True,
        "general.dut_caps.dut_caps_flags.fixed_timing_dut_supported": False,
        "general.dut_caps.dut_caps_flags.spread_spectrum_supported": False,
        "general.dut_caps.dut_caps_flags.change_vf_without_lt_supported": True,
        "general.dut_caps.dut_caps_flags.lane_count_reduction_without_lt_supported": False,
        "general.dut_caps.dut_caps_flags.e_ddc_protocol_supported": True,
        "general.dut_caps.dut_caps_flags.dut_is_type_c_device": True,
        "general.dut_caps.dut_caps_flags.fec_supported": True,
        "general.dut_caps.dut_caps_flags.fec_disable_sequence_supported": False,
        "general.dut_caps.dut_caps_flags.audio_without_video_supported": True,
        "general.dut_caps.dut_caps_flags.dsc_supported": False,
        "general.dut_caps.dut_caps_flags.dsc_block_prediction_supported": False,
        "general.test_automation.test_audio_pattern": False,
        "general.test_automation.test_video_pattern": False,
        "general.test_automation.test_edid_read": False,
        "general.test_automation.test_link_training": False,
    },
    # Params can be overridden on a by model base. For example
    # "redrix" : {
    #   "general.timeout": 8000,
    # }
}

INTEL_COMMON_PARAMS_DP_1_4_CTS_DUT_SRC = {
    "default": {
        **INTEL_COMMON_PARAMS_CTS_DUT_SRC["default"],
        "general.test_automation.event_indication": dp_1_4_source_general_tab.EventIndication.AlwaysReady,
    }
}

# For each test groups we have:
# - default param class
# - for each board that needs to support special params
#    - the params to be set and their value
#    - optional overrides for each model.
TEST_GROUPS = {
    video_pb2.GROUP_HDMI_RX_CRC_TEST: {
        "group_id": UniTAP.TestGroupId.HDMI_RX_CRC,
        "default_param_class": UniTAP.CrcVideoTestParam,
    },
    video_pb2.GROUP_HDMI_RX_VRR_TEST: {
        "group_id": UniTAP.TestGroupId.HDMI_RX_VRR,
        "default_param_class": UniTAP.VrrSourceDUTTestParam,
    },
    video_pb2.GROUP_HD_TX_CONTINUITY_TEST: {
        "group_id": UniTAP.TestGroupId.HD_TX_CONTINUITY,
        "default_param_class": UniTAP.HdmiSinkContinuityDUTTestParam,
    },
    video_pb2.GROUP_AUDIO_TEST: {
        "group_id": UniTAP.TestGroupId.AUDIO_TEST,
        "default_param_class": UniTAP.AudioTestParam,
    },
    video_pb2.GROUP_PIXEL_LEVEL_VIDEO_TEST: {
        "group_id": UniTAP.TestGroupId.PIXEL_VIDEO_TEST,
        "default_param_class": UniTAP.VideoPixelTestParam,
    },
    video_pb2.GROUP_CRC_BASED_VIDEO_TEST: {
        "group_id": UniTAP.TestGroupId.DP_RX_CRC,
        "default_param_class": UniTAP.CrcVideoTestParam,
    },
    video_pb2.GROUP_LINK_TEST: {
        "group_id": UniTAP.TestGroupId.DP_RX_SIMPLE_LT,
        "default_param_class": UniTAP.LinkConfigTestParam,
    },
    video_pb2.GROUP_DISPLAYPORT_1_4_LINK_LAYER_CTS: {
        "group_id": UniTAP.TestGroupId.DP_RX_LL_CTS,
        "default_param_class": UniTAP.Dp14SourceDUTTestParam,
        "brya": INTEL_COMMON_PARAMS_DP_1_4_CTS_DUT_SRC,
        "fatcat": INTEL_COMMON_PARAMS_DP_1_4_CTS_DUT_SRC,
    },
    video_pb2.GROUP_DISPLAYPORT_1_4_DSC_LINK_LAYER_CTS: {
        "group_id": UniTAP.TestGroupId.DP_RX_LL_CTS_DSC,
        "default_param_class": UniTAP.Dp14SourceDUTTestParam,
    },
    video_pb2.GROUP_DISPLAYPORT_1_4_DISPLAYID_CTS_SOURCE_TEST: {
        "group_id": UniTAP.TestGroupId.DP_RX_DISPLAYID,
        "default_param_class": UniTAP.Dp14SourceDUTTestParam,
    },
    video_pb2.GROUP_DISPLAYPORT_2_1_LINK_LAYER_SOURCE_DUT_CTS: {
        "group_id": UniTAP.TestGroupId.DP_2_1_RX_LL_CTS,
        "default_param_class": UniTAP.Dp21SourceDUTTestParam,
        "brya": INTEL_COMMON_PARAMS_CTS_DUT_SRC,
        "fatcat": INTEL_COMMON_PARAMS_CTS_DUT_SRC,
    },
    video_pb2.GROUP_DISPLAYPORT_2_1_DSC_CTS_SOURCE_DUT: {
        "group_id": UniTAP.TestGroupId.DP_2_1_RX_DSC_CTS,
        "default_param_class": UniTAP.Dp21SourceDUTTestParam,
    },
    video_pb2.GROUP_DISPLAYPORT_2_1_DISPLAYID_CTS_SOURCE_TEST: {
        "group_id": UniTAP.TestGroupId.DP_2_1_RX_DISPAYID,
        "default_param_class": UniTAP.Dp21SourceDUTTestParam,
    },
}

GRPC_VIDEO_SPEC_TO_SDK = {
    video_pb2.VIDEO_SPECIFICATION_HDMI_1_4: UniTAP.HdmiModeRx.HDMI_1_4,
    video_pb2.VIDEO_SPECIFICATION_HDMI_2_0: UniTAP.HdmiModeRx.HDMI_2_0,
    video_pb2.VIDEO_SPECIFICATION_HDMI_2_1: UniTAP.HdmiModeRx.HDMI_2_1,
}

SDK_VIDEO_SPEC_TO_RGPC = {
    UniTAP.HdmiModeRx.HDMI_1_4: video_pb2.VIDEO_SPECIFICATION_HDMI_1_4,
    UniTAP.HdmiModeRx.HDMI_2_0: video_pb2.VIDEO_SPECIFICATION_HDMI_2_0,
    UniTAP.HdmiModeRx.HDMI_2_1: video_pb2.VIDEO_SPECIFICATION_HDMI_2_1,
}


GRPC_FRL_MODE_TO_SDK = {
    video_pb2.FRL_MODE_DISABLE: UniTAP.FrlMode.Mode_Disable,
    video_pb2.FRL_MODE_3LANES_3GBPS: UniTAP.FrlMode.Mode_3lanes_3gbps,
    video_pb2.FRL_MODE_3LANES_6GBPS: UniTAP.FrlMode.Mode_3lanes_6gbps,
    video_pb2.FRL_MODE_4LANES_6GBPS: UniTAP.FrlMode.Mode_4lanes_6gbps,
    video_pb2.FRL_MODE_4LANES_8GBPS: UniTAP.FrlMode.Mode_4lanes_8gbps,
    video_pb2.FRL_MODE_4LANES_10GBPS: UniTAP.FrlMode.Mode_4lanes_10gbps,
    video_pb2.FRL_MODE_4LANES_12GBPS: UniTAP.FrlMode.Mode_4lanes_12gbps,
}

SDK_FRL_MODE_TO_GRPC = {
    UniTAP.FrlMode.Mode_Unknown: video_pb2.FRL_MODE_UNKNOWN,
    UniTAP.FrlMode.Mode_Disable: video_pb2.FRL_MODE_DISABLE,
    UniTAP.FrlMode.Mode_3lanes_3gbps: video_pb2.FRL_MODE_3LANES_3GBPS,
    UniTAP.FrlMode.Mode_3lanes_6gbps: video_pb2.FRL_MODE_3LANES_6GBPS,
    UniTAP.FrlMode.Mode_4lanes_6gbps: video_pb2.FRL_MODE_4LANES_6GBPS,
    UniTAP.FrlMode.Mode_4lanes_8gbps: video_pb2.FRL_MODE_4LANES_8GBPS,
    UniTAP.FrlMode.Mode_4lanes_10gbps: video_pb2.FRL_MODE_4LANES_10GBPS,
    UniTAP.FrlMode.Mode_4lanes_12gbps: video_pb2.FRL_MODE_4LANES_12GBPS,
}

SDK_COLOR_FORMAT_TO_GRPC = {
    UniTAP.ColorInfo.ColorFormat.CF_NONE: video_pb2.STREAM_INFO_CF_NONE,
    UniTAP.ColorInfo.ColorFormat.CF_UNKNOWN: video_pb2.STREAM_INFO_CF_UNKNOWN,
    UniTAP.ColorInfo.ColorFormat.CF_RGB: video_pb2.STREAM_INFO_CF_RGB,
    UniTAP.ColorInfo.ColorFormat.CF_YCbCr_422: video_pb2.STREAM_INFO_CF_YCBCR_422,
    UniTAP.ColorInfo.ColorFormat.CF_YCbCr_444: video_pb2.STREAM_INFO_CF_YCBCR_444,
    UniTAP.ColorInfo.ColorFormat.CF_YCbCr_420: video_pb2.STREAM_INFO_CF_YCBCR_420,
    UniTAP.ColorInfo.ColorFormat.CF_IDO_DEFINED: video_pb2.STREAM_INFO_CF_IDO_DEFINED,
    UniTAP.ColorInfo.ColorFormat.CF_Y_ONLY: video_pb2.STREAM_INFO_CF_Y_ONLY,
    UniTAP.ColorInfo.ColorFormat.CF_RAW: video_pb2.STREAM_INFO_CF_RAW,
    UniTAP.ColorInfo.ColorFormat.CF_DSC: video_pb2.STREAM_INFO_CF_DSC,
}

SDK_COLOMETRY_TO_GRPC = {
    UniTAP.ColorInfo.Colorimetry.CM_NONE: video_pb2.STREAM_INFO_CM_NONE,
    UniTAP.ColorInfo.Colorimetry.CM_RESERVED: video_pb2.STREAM_INFO_CM_RESERVED,
    UniTAP.ColorInfo.Colorimetry.CM_sRGB: video_pb2.STREAM_INFO_CM_SRGB,
    UniTAP.ColorInfo.Colorimetry.CM_SMPTE_170M: video_pb2.STREAM_INFO_CM_SMPTE_170M,
    UniTAP.ColorInfo.Colorimetry.CM_ITUR_BT601: video_pb2.STREAM_INFO_CM_ITUR_BT601,
    UniTAP.ColorInfo.Colorimetry.CM_ITUR_BT709: video_pb2.STREAM_INFO_CM_ITUR_BT709,
    UniTAP.ColorInfo.Colorimetry.CM_xvYCC601: video_pb2.STREAM_INFO_CM_XVYCC601,
    UniTAP.ColorInfo.Colorimetry.CM_xvYCC709: video_pb2.STREAM_INFO_CM_XVYCC709,
    UniTAP.ColorInfo.Colorimetry.CM_sYCC601: video_pb2.STREAM_INFO_CM_SYCC601,
    UniTAP.ColorInfo.Colorimetry.CM_AdobeYCC601: video_pb2.STREAM_INFO_CM_ADOBEYCC601,
    UniTAP.ColorInfo.Colorimetry.CM_AdobeRGB: video_pb2.STREAM_INFO_CM_ADOBERGB,
    UniTAP.ColorInfo.Colorimetry.CM_ITUR_BT2020_YcCbcCrc: video_pb2.STREAM_INFO_CM_ITUR_BT2020_YCCBCCRC,
    UniTAP.ColorInfo.Colorimetry.CM_ITUR_BT2020_YCbCr: video_pb2.STREAM_INFO_CM_ITUR_BT2020_YCBCR,
    UniTAP.ColorInfo.Colorimetry.CM_ITUR_BT2020_RGB: video_pb2.STREAM_INFO_CM_ITUR_BT2020_RGB,
    UniTAP.ColorInfo.Colorimetry.CM_RGB_WIDE_GAMUT_FIX: video_pb2.STREAM_INFO_CM_RGB_WIDE_GAMUT_FIX,
    UniTAP.ColorInfo.Colorimetry.CM_RGB_WIDE_GAMUT_FLT: video_pb2.STREAM_INFO_CM_RGB_WIDE_GAMUT_FLT,
    UniTAP.ColorInfo.Colorimetry.CM_DCI_P3: video_pb2.STREAM_INFO_CM_DCI_P3,
    UniTAP.ColorInfo.Colorimetry.CM_DICOM_1_4_GRAY_SCALE: video_pb2.STREAM_INFO_CM_DICOM_1_4_GRAY_SCALE,
    UniTAP.ColorInfo.Colorimetry.CM_CUSTOM_COLOR_PROFILE: video_pb2.STREAM_INFO_CM_CUSTOM_COLOR_PROFILE,
    UniTAP.ColorInfo.Colorimetry.CM_opYCC601: video_pb2.STREAM_INFO_CM_OPYCC601,
    UniTAP.ColorInfo.Colorimetry.CM_opRGB: video_pb2.STREAM_INFO_CM_OPRGB,
}

SDK_DYNAMIC_RANGE_TO_GRPC = {
    UniTAP.ColorInfo.DynamicRange.DR_UNKNOWN: video_pb2.STREAM_INFO_DR_UNKNOWN,
    UniTAP.ColorInfo.DynamicRange.DR_VESA: video_pb2.STREAM_INFO_DR_VESA,
    UniTAP.ColorInfo.DynamicRange.DR_CTA: video_pb2.STREAM_INFO_DR_CTA,
}

SDK_COLOR_FORMAT_TO_GRPC = {
    UniTAP.ColorInfo.ColorFormat.CF_NONE: video_pb2.STREAM_INFO_CF_NONE,
    UniTAP.ColorInfo.ColorFormat.CF_UNKNOWN: video_pb2.STREAM_INFO_CF_UNKNOWN,
    UniTAP.ColorInfo.ColorFormat.CF_RGB: video_pb2.STREAM_INFO_CF_RGB,
    UniTAP.ColorInfo.ColorFormat.CF_YCbCr_422: video_pb2.STREAM_INFO_CF_YCBCR_422,
    UniTAP.ColorInfo.ColorFormat.CF_YCbCr_444: video_pb2.STREAM_INFO_CF_YCBCR_444,
    UniTAP.ColorInfo.ColorFormat.CF_YCbCr_420: video_pb2.STREAM_INFO_CF_YCBCR_420,
    UniTAP.ColorInfo.ColorFormat.CF_IDO_DEFINED: video_pb2.STREAM_INFO_CF_IDO_DEFINED,
    UniTAP.ColorInfo.ColorFormat.CF_Y_ONLY: video_pb2.STREAM_INFO_CF_Y_ONLY,
    UniTAP.ColorInfo.ColorFormat.CF_RAW: video_pb2.STREAM_INFO_CF_RAW,
    UniTAP.ColorInfo.ColorFormat.CF_DSC: video_pb2.STREAM_INFO_CF_DSC,
}

SDK_COLOMETRY_TO_GRPC = {
    UniTAP.ColorInfo.Colorimetry.CM_NONE: video_pb2.STREAM_INFO_CM_NONE,
    UniTAP.ColorInfo.Colorimetry.CM_RESERVED: video_pb2.STREAM_INFO_CM_RESERVED,
    UniTAP.ColorInfo.Colorimetry.CM_sRGB: video_pb2.STREAM_INFO_CM_SRGB,
    UniTAP.ColorInfo.Colorimetry.CM_SMPTE_170M: video_pb2.STREAM_INFO_CM_SMPTE_170M,
    UniTAP.ColorInfo.Colorimetry.CM_ITUR_BT601: video_pb2.STREAM_INFO_CM_ITUR_BT601,
    UniTAP.ColorInfo.Colorimetry.CM_ITUR_BT709: video_pb2.STREAM_INFO_CM_ITUR_BT709,
    UniTAP.ColorInfo.Colorimetry.CM_xvYCC601: video_pb2.STREAM_INFO_CM_XVYCC601,
    UniTAP.ColorInfo.Colorimetry.CM_xvYCC709: video_pb2.STREAM_INFO_CM_XVYCC709,
    UniTAP.ColorInfo.Colorimetry.CM_sYCC601: video_pb2.STREAM_INFO_CM_SYCC601,
    UniTAP.ColorInfo.Colorimetry.CM_AdobeYCC601: video_pb2.STREAM_INFO_CM_ADOBEYCC601,
    UniTAP.ColorInfo.Colorimetry.CM_AdobeRGB: video_pb2.STREAM_INFO_CM_ADOBERGB,
    UniTAP.ColorInfo.Colorimetry.CM_ITUR_BT2020_YcCbcCrc: video_pb2.STREAM_INFO_CM_ITUR_BT2020_YCCBCCRC,
    UniTAP.ColorInfo.Colorimetry.CM_ITUR_BT2020_YCbCr: video_pb2.STREAM_INFO_CM_ITUR_BT2020_YCBCR,
    UniTAP.ColorInfo.Colorimetry.CM_ITUR_BT2020_RGB: video_pb2.STREAM_INFO_CM_ITUR_BT2020_RGB,
    UniTAP.ColorInfo.Colorimetry.CM_RGB_WIDE_GAMUT_FIX: video_pb2.STREAM_INFO_CM_RGB_WIDE_GAMUT_FIX,
    UniTAP.ColorInfo.Colorimetry.CM_RGB_WIDE_GAMUT_FLT: video_pb2.STREAM_INFO_CM_RGB_WIDE_GAMUT_FLT,
    UniTAP.ColorInfo.Colorimetry.CM_DCI_P3: video_pb2.STREAM_INFO_CM_DCI_P3,
    UniTAP.ColorInfo.Colorimetry.CM_DICOM_1_4_GRAY_SCALE: video_pb2.STREAM_INFO_CM_DICOM_1_4_GRAY_SCALE,
    UniTAP.ColorInfo.Colorimetry.CM_CUSTOM_COLOR_PROFILE: video_pb2.STREAM_INFO_CM_CUSTOM_COLOR_PROFILE,
    UniTAP.ColorInfo.Colorimetry.CM_opYCC601: video_pb2.STREAM_INFO_CM_OPYCC601,
    UniTAP.ColorInfo.Colorimetry.CM_opRGB: video_pb2.STREAM_INFO_CM_OPRGB,
}

SDK_DYNAMIC_RANGE_TO_GRPC = {
    UniTAP.ColorInfo.DynamicRange.DR_UNKNOWN: video_pb2.STREAM_INFO_DR_UNKNOWN,
    UniTAP.ColorInfo.DynamicRange.DR_VESA: video_pb2.STREAM_INFO_DR_VESA,
    UniTAP.ColorInfo.DynamicRange.DR_CTA: video_pb2.STREAM_INFO_DR_CTA,
}
