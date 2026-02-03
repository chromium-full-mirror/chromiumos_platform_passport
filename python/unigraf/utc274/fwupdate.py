# Copyright 2025 The ChromiumOS Authors
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

"""Provides functionality to update the firmware of UTC274 devices.

This module interacts with the UTCLibrary to manage and perform firmware
updates on connected UTC274 devices. It allows for updating all devices
or a specific device by its serial number, with options to force the
update regardless of the current firmware versions.
"""

import hashlib
import logging
import os
import urllib

# pylint: disable=import-error
import UTCLibrary
import wget

from utils import constants
from utils import log_functionality


# pylint: enable=import-error


class Utc274FwUpdater:
    """Manages and performs firmware updates for UTC274 devices.

    This class provides methods to update the firmware on connected UTC274
    devices, either all at once or individually by serial number. It
    handles device selection, firmware version checking, and the actual
    update process using the UTCLibrary.

    Attributes:
        force_fw (bool):  If True, forces the firmware update even if the
            current firmware version matches or is lower than the bundle
            version.
    """

    @log_functionality.logger
    def __init__(self, force_fw, fw_version):
        self._fw_blob_path = "/opt/unigraf/"
        self._force_fw = force_fw
        self._fw_version = fw_version

        self._download_component_fw("pd")
        self._download_component_fw("ms")

        self._utc_lib = UTCLibrary.UTCLib()
        self._fw_updater = UTCLibrary.FWUpdate(self._utc_lib)
        logging.info(
            "Utc274FwUpdater params fwpath:%s force: %s",
            self._fw_blob_path,
            self._force_fw,
        )

    def _download_component_fw(self, component):
        fw_name = constants.UTC_274_FW[self._fw_version][component]["name"]
        fw_checksum = constants.UTC_274_FW[self._fw_version][component][
            "checksum"
        ]
        fw_url = urllib.parse.urljoin(
            constants.UTC_274_FIRMWARE_BASE_LINK,
            fw_name,
        )
        path = self._fw_blob_path + self._get_clean_fw_name(fw_name)
        self._download_firmware(fw_url, path)
        self._check_file_hash(path, fw_checksum)

    def _download_firmware(self, url, path):
        if os.path.exists(path):
            logging.info("Removed existing file %s.", path)
            os.remove(path)

        logging.info("Download firmware from url: %s", url)
        wget.download(url, path)
        logging.info("Firmware download finished")

    def _check_file_hash(self, path, expected):
        with open(path, "rb", buffering=0) as f:
            actual = hashlib.file_digest(f, "sha256").hexdigest()
            if actual != expected:
                raise Exception(
                    f"Hash for file {path} is {actual}, expected {expected}"
                )
            logging.info("Hashes for file %s match.", path)

    def _get_clean_fw_name(self, fw_name):
        prefix_clear_name = fw_name.removeprefix("utc274_")

        head, sep, tail = prefix_clear_name.rpartition("_")
        if sep == "_" and tail.isdigit():
            return head

        return prefix_clear_name

    @log_functionality.logger
    def update_all_devices(self):
        logging.info("Starting update for all connected devices")

        devices = self._fw_updater.device_list()
        for _, device in enumerate(devices):
            self._update_with_serial(
                device[constants.UTC_274_SERIAL_STRUCT_IDX]
            )

        logging.info("Finished attempting to update all connected devices")

    @log_functionality.logger
    def update_device(self, serial):
        for device in self._fw_updater.device_list():
            # Check if device is open. Update FW only if the device is
            # not in use and the serials match.
            if device[constants.UTC_274_SERIAL_STRUCT_IDX] == serial and (
                not device[constants.UTC_274_LOCKED_NAME_STRUCT_IDX]
            ):
                return self._update_with_serial(serial)

        raise Exception(f"Device with serial {serial} was not performed")

    @log_functionality.logger
    def _update_with_serial(self, serial):
        self._fw_updater.set_fw_folder_path(self._fw_blob_path)

        logging.info("Selecting device, serial %s", serial)
        self._fw_updater.select_device_to_update(serial_number=serial)

        logging.info(
            "PDC FW version, bundle:%s current: %s",
            self._fw_updater.bundle_pd_version(),
            self._fw_updater.current_pd_version(),
        )

        logging.info(
            "MS FW version, bundle: %s current:%s",
            self._fw_updater.bundle_ms_version(),
            self._fw_updater.current_ms_version(),
        )

        # Select target device to update only if force or the update is needed
        if not self._fw_updater.is_ms_update_required() and not self._force_fw:
            logging.info("MS update not required, skipping update for device")
            return

        # Select target device to update only if force or the update is needed
        if not self._fw_updater.is_pd_update_required() and not self._force_fw:
            logging.info("PDC update not required, skipping update for device")
            return

        logging.info("Starting firmware update")
        # Run the actual firmware update
        self._fw_updater.update_fw(
            advanced=self._force_fw,
            update_advanced_pd=self._force_fw,
            update_advanced_ms=self._force_fw,
        )
        logging.info("Firmware update process completed")
