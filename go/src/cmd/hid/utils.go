// Copyright 2025 The ChromiumOS Authors
// Use of this source code is governed by a BSD-style license that can be
// found in the LICENSE file.

package hid

import (
	"context"
	"fmt"
	"log/slog"

	"go.chromium.org/chromiumos/config/go/test/lab/api/passport"
)

func getHIDDevices(ctx context.Context, client passport.HIDServiceClient) ([]string, error) {
	resp1, err := client.GetHIDDevices(ctx, &passport.GetHIDDevicesRequest{})
	if err != nil {
		return nil, err
	}
	var res []string
	for _, hid := range resp1.GetDevices() {
		res = append(res, hid.GetId())
	}
	slog.Info("Detected HID devices", "devices", res)
	return res, nil
}

func wrapHIDAction(ctx context.Context, client passport.HIDServiceClient, hid string, action func() error) error {
	if _, err := client.InitHIDDevice(ctx, &passport.InitHIDDeviceRequest{DeviceId: hid}); err != nil {
		return fmt.Errorf("failed to initialize HID device: %v: %w", hid, err)
	}

	if err := action(); err != nil {
		return err
	}

	if _, err := client.CloseHIDDevice(ctx, &passport.CloseHIDDeviceRequest{DeviceId: hid}); err != nil {
		return fmt.Errorf("failed to initialize HID device: %v: %w", hid, err)
	}
	return nil
}
