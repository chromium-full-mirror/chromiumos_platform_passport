# Copyright 2025 The ChromiumOS Authors
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

"""Constants used in the unigrafctl application."""

UTC_274_LATEST_FW = "1.1.44"
UTC_274_FW = {
    "1.1.44": {
        "ms": {
            "name": "utc274_firmware.ms274.1.0.33",
            "checksum": "09db6514ea2bcc62bb92650d7dfed9541a3489e07d94031d22e329031d260769",
        },
        "pd": {
            "name": "utc274_firmware.pd274.1.0.31_2",
            "checksum": "22728ce3be55827ddb96cf1d87f20238d18765a6616e69e596226077b433c873",
        },
    },
    "1.0.31": {
        "ms": {
            "name": "utc274_firmware.ms274.1.0.31",
            "checksum": "20e279966e93e27762a25c8de48b0eac557a9a2117ea489fca6cd18d6919887a",
        },
        "pd": {
            "name": "utc274_firmware.pd274.1.0.31",
            "checksum": "78d8a040a8d269d194fee4f81fc292f7833cc68d935f622f5a9258324e905978",
        },
    },
    "1.0.29": {
        "ms": {
            "name": "utc274_firmware.ms274.1.0.29",
            "checksum": "545d1b6bc092abd832036edf5ef249bfe6e56f9fcbc2b4fef86c628ce8ee29c5",
        },
        "pd": {
            "name": "utc274_firmware.pd274.1.0.28",
            "checksum": "5a61c520bbfa9030e945d9f59415365a23a0b30cebea0c6235275686a1b5e551",
        },
    },
    "1.0.24": {
        "ms": {
            "name": "utc274_firmware.ms274.1.0.24",
            "checksum": "fddf640e97c159287f302357cf836d30b0693e630612814e74e2f08efa0e77a5",
        },
        "pd": {
            "name": "utc274_firmware.pd274.1.0.24",
            "checksum": "a8d58961bcf2b77ca489a45f4eae36430a2e4f9dcf20d96dc89db2d62d8157fd",
        },
    },
    "1.0.21": {
        "ms": {
            "name": "utc274_firmware.ms274.1.0.21",
            "checksum": "3e39720265035389c061fd7f40abb30366ebb8fa10de4a56a0213ca23c001481",
        },
        "pd": {
            "name": "utc274_firmware.pd274.1.0.21",
            "checksum": "4ef4172109f0fc8f71b06eaaf61333191316a8e86fa50a6564c36d627e6f112e",
        },
    },
    "1.0.18": {
        "ms": {
            "name": "utc274_firmware.ms274.1.0.18",
            "checksum": "cdd60acaded2a9365978ee4e3c0df9a448215f45df4e5cb25fcc54361f208405",
        },
        "pd": {
            "name": "utc274_firmware.pd274.1.0.18",
            "checksum": "e766d01b1c7a5540c8fc3ecc8c5427eb8863f5d90440daab56b1da55320fd4ed",
        },
    },
}
UTC_274_FIRMWARE_BASE_LINK = (
    "https://storage.googleapis.com/chromeos-localmirror/distfiles/"
)
UTC_274_DELAY_S = 0.35
UTC_274_DELAY_MS = UTC_274_DELAY_S * 1000
UTC_274_STABILITY_S = 5
UTC_274_STABILITY_MS = UTC_274_STABILITY_S * 1000
