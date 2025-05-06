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

# Maps test groups to the enum provided by UniTAP
UCD500_TEST_GROUPS = {
    video_pb2.GROUP_AUDIO_TEST: {
        "group_id": UniTAP.TestGroupId.AUDIO_TEST,
        "default_params": UniTAP.AudioTestParam,
    },
    video_pb2.GROUP_PIXEL_LEVEL_VIDEO_TEST: {
        "group_id": UniTAP.TestGroupId.PIXEL_VIDEO_TEST,
        "default_params": UniTAP.VideoPixelTestParam,
    },
    video_pb2.GROUP_CRC_BASED_VIDEO_TEST: {
        "group_id": UniTAP.TestGroupId.DP_RX_CRC,
        "default_params": UniTAP.CrcVideoTestParam,
    },
    video_pb2.GROUP_LINK_TEST: {
        "group_id": UniTAP.TestGroupId.DP_RX_SIMPLE_LT,
        "default_params": UniTAP.LinkConfigTestParam,
    },
    video_pb2.GROUP_DISPLAYPORT_1_4_LINK_LAYER_CTS: {
        "group_id": UniTAP.TestGroupId.DP_RX_LL_CTS,
        "default_params": UniTAP.Dp14SourceDUTTestParam,
    },
    video_pb2.GROUP_DISPLAYPORT_1_4_DSC_LINK_LAYER_CTS: {
        "group_id": UniTAP.TestGroupId.DP_RX_LL_CTS_DSC,
        "default_params": UniTAP.Dp14SourceDUTTestParam,
    },
    video_pb2.GROUP_DISPLAYPORT_1_4_DISPLAYID_CTS_SOURCE_TEST: {
        "group_id": UniTAP.TestGroupId.DP_RX_DISPLAYID,
        "default_params": UniTAP.Dp14SourceDUTTestParam,
    },
    video_pb2.GROUP_DISPLAYPORT_2_1_LINK_LAYER_SOURCE_DUT_CTS: {
        "group_id": UniTAP.TestGroupId.DP_2_1_RX_LL_CTS,
        "default_params": UniTAP.Dp21SourceDUTTestParam,
    },
    video_pb2.GROUP_DISPLAYPORT_2_1_DSC_CTS_SOURCE_DUT: {
        "group_id": UniTAP.TestGroupId.DP_2_1_RX_DSC_CTS,
        "default_params": UniTAP.Dp21SourceDUTTestParam,
    },
    video_pb2.GROUP_DISPLAYPORT_2_1_DISPLAYID_CTS_SOURCE_TEST: {
        "group_id": UniTAP.TestGroupId.DP_2_1_RX_DISPAYID,
        "default_params": UniTAP.Dp21SourceDUTTestParam,
    },
}

TEST_UNITAP_TO_GRPC = {
    0: video_pb2.COMPLIANCE_TEST_PASSED,
    1: video_pb2.COMPLIANCE_TEST_FAILED,
    2: video_pb2.COMPLIANCE_TEST_SKIPPED,
    3: video_pb2.COMPLIANCE_TEST_ABORTED,
}
