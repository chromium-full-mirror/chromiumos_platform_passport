"""Translate values to and from gRPC to UCD500 specific values."""

# Copyright 2025 The ChromiumOS Authors
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

# pylint: disable=import-error
from chromiumos.test.lab.api.passport import (
    video_tester_service_pb2 as video_pb2,
)
import UniTAP


# pylint: enable=import-error
UCD_422_ROLES = {
    video_pb2.ROLE_HDMISOURCE_HDMISINK: UniTAP.dev.UCD422.HDMISourceHDMISink,
}

TEST_UNITAP_TO_GRPC = {
    0: video_pb2.COMPLIANCE_TEST_PASSED,
    1: video_pb2.COMPLIANCE_TEST_FAILED,
    2: video_pb2.COMPLIANCE_TEST_SKIPPED,
    3: video_pb2.COMPLIANCE_TEST_ABORTED,
}

UCD422_TEST_GROUPS = {
    video_pb2.GROUP_HDMI_RX_CRC_TEST: {
        "group_id": UniTAP.TestGroupId.HDMI_RX_CRC,
        "default_params": UniTAP.CrcVideoTestParam,
    },
    video_pb2.GROUP_HDMI_RX_VRR_TEST: {
        "group_id": UniTAP.TestGroupId.HDMI_RX_VRR,
        "default_params": UniTAP.VrrSourceDUTTestParam,
    },
    video_pb2.GROUP_HD_TX_CONTINUITY_TEST: {
        "group_id": UniTAP.TestGroupId.HD_TX_CONTINUITY,
        "default_params": UniTAP.HdmiSinkContinuityDUTTestParam,
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
