// Copyright 2025 The ChromiumOS Authors
// Use of this source code is governed by a BSD-style license that can be
// found in the LICENSE file.

package server

import (
	"context"
	"fmt"
	"log/slog"

	"go.chromium.org/chromiumos/config/go/test/lab/api/passport"
)

// hidServiceServer implements api/passport.HIDServiceServer and wraps individual
// HID plugins.
type hidServiceServer struct {
	// Maps individual hid IDs to their controlling plugin.
	hidMap map[string]HIDPlugin
	// All registered plugins.
	plugins []HIDPlugin
}

func newHIDServiceServer(ctx context.Context) (passport.HIDServiceServer, error) {
	s := &hidServiceServer{
		hidMap:  make(map[string]HIDPlugin),
		plugins: hidPlugins,
	}

	return s, nil
}

// GetHIDDevices probes for all HID Simulators.
func (h *hidServiceServer) GetHIDDevices(ctx context.Context, req *passport.GetHIDDevicesRequest) (*passport.GetHIDDevicesResponse, error) {
	slog.Info("Received passport.GetHIDDevicesRequest", "req", req)
	HIDs, err := h.refreshHIDs(ctx, req)
	if err != nil {
		return nil, fmt.Errorf("failed to refresh HIDs: %w", err)
	}

	return &passport.GetHIDDevicesResponse{
		Devices: HIDs,
	}, nil
}

// InitHIDDevice initializes the specified HID device.
func (h *hidServiceServer) InitHIDDevice(ctx context.Context, req *passport.InitHIDDeviceRequest) (*passport.InitHIDDeviceResponse, error) {
	slog.Info("Received passport.InitHIDDevice", "req", req)
	plugin, err := h.pluginForHID(ctx, req.GetDeviceId())
	if err != nil {
		return nil, fmt.Errorf("failed to fetch plugin for HID: %w", err)
	}

	slog.Info("Initializing HID", "id", req.GetDeviceId(), "plugin", plugin.Name())
	if _, err := plugin.InitHIDDevice(ctx, req); err != nil {
		return nil, fmt.Errorf("failed to initialize HID: %w", err)
	}
	return &passport.InitHIDDeviceResponse{}, nil
}

// CloseHIDDevice releases the specified HID device and releases any resources held open.
func (h *hidServiceServer) CloseHIDDevice(ctx context.Context, req *passport.CloseHIDDeviceRequest) (*passport.CloseHIDDeviceResponse, error) {
	slog.Info("Received passport.CloseHIDDevice", "req", req)
	plugin, err := h.pluginForHID(ctx, req.GetDeviceId())
	if err != nil {
		return nil, fmt.Errorf("failed to fetch plugin for HID: %w", err)
	}

	slog.Info("Closing HID", "id", req.GetDeviceId(), "plugin", plugin.Name())
	if _, err := plugin.CloseHIDDevice(ctx, req); err != nil {
		return nil, fmt.Errorf("failed to close HID: %w", err)
	}
	return &passport.CloseHIDDeviceResponse{}, nil
}

// KeyboardAction performs the requested keyboard action.
func (h *hidServiceServer) KeyboardAction(ctx context.Context, req *passport.KeyboardActionRequest) (*passport.KeyboardActionResponse, error) {
	slog.Info("Received passport.KeyboardAction", "req", req)
	plugin, err := h.pluginForHID(ctx, req.GetDeviceId())
	if err != nil {
		return nil, fmt.Errorf("failed to fetch plugin for HID: %w", err)
	}

	if _, err := plugin.KeyboardAction(ctx, req); err != nil {
		return nil, fmt.Errorf("failed to perform key action: %w", err)
	}
	return &passport.KeyboardActionResponse{}, nil
}

// MouseAction performs the requested mouse action.
func (h *hidServiceServer) MouseAction(ctx context.Context, req *passport.MouseActionRequest) (*passport.MouseActionResponse, error) {
	slog.Info("Received passport.MouseAction", "req", req)
	plugin, err := h.pluginForHID(ctx, req.GetDeviceId())
	if err != nil {
		return nil, fmt.Errorf("failed to fetch plugin for HID: %w", err)
	}

	if _, err := plugin.MouseAction(ctx, req); err != nil {
		return nil, fmt.Errorf("failed to perform mouse action: %w", err)
	}
	return &passport.MouseActionResponse{}, nil
}

// pluginForHID gets the plugin that controls a specific hid.
func (h *hidServiceServer) pluginForHID(ctx context.Context, id string) (HIDPlugin, error) {
	// Check if we've cached the plugin for this hid ID.
	if c, ok := h.hidMap[id]; ok {
		return c, nil
	}

	// Unknown which plugin controls this hid -> refresh.
	if _, err := h.refreshHIDs(ctx, &passport.GetHIDDevicesRequest{}); err != nil {
		return nil, fmt.Errorf("failed to refresh HIDs: %w", err)
	}

	if c, ok := h.hidMap[id]; ok {
		return c, nil
	}

	return nil, fmt.Errorf("unknown hid with ID: %q", id)
}

// refreshHIDs refreshes the cached HIDs by probing the plugins.
func (h *hidServiceServer) refreshHIDs(ctx context.Context, req *passport.GetHIDDevicesRequest) ([]*passport.HIDDevice, error) {
	var hids []*passport.HIDDevice
	hidMap := make(map[string]HIDPlugin)
	for _, plugin := range h.plugins {
		resp, err := plugin.GetHIDDevices(ctx, req)
		if err != nil {
			return nil, fmt.Errorf("failed to get HIDs for plugin %q: %w", plugin.Name(), err)
		}

		for _, dev := range resp.GetDevices() {
			id := dev.GetId()
			if id == "" {
				return nil, fmt.Errorf("received empty hid ID, plugin: %q", plugin.Name())
			}
			if pOld, ok := hidMap[id]; ok {
				return nil, fmt.Errorf("received duplicate hid ID: %q, plugin1 %q, plugin2 %q", id, pOld.Name(), plugin.Name())
			}
			hids = append(hids, dev)
			hidMap[id] = plugin
		}
	}

	slog.Info("Found HIDs", "HIDs", hids)
	h.hidMap = hidMap
	return hids, nil
}
