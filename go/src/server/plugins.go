// Copyright 2024 The ChromiumOS Authors
// Use of this source code is governed by a BSD-style license that can be
// found in the LICENSE file.

package server

import (
	"context"

	"go.chromium.org/chromiumos/config/go/test/lab/api/passport"
)

// module variables containing all registered plugins.
var (
	switchPlugins      []SwitchPlugin
	cameraPlugins      []CameraPlugin
	usbTesterPlugins   []UsbTesterPlugin
	videoTesterPlugins []VideoTesterPlugin
	hidPlugins         []HIDPlugin
)

// SwitchPlugin provide passport.SwitchServiceServer implementations for individual groups of switches.
// i.e. different makes/models of switches may have different implementations for detection/control.
type SwitchPlugin interface {
	// Name returns the plugin's name for logging purposes.
	Name() string

	UpdateIgnoredPorts(ports []string)
	GetUsedPorts() []string

	// Initializes plugin.
	Init(context.Context) error

	// Inherit service interface for plugins.
	passport.SwitchServiceServer
}

// RegisterSwitchPlugin registers a switch controller plugin with the server application.
func RegisterSwitchPlugin(plugin SwitchPlugin) {
	switchPlugins = append(switchPlugins, plugin)
}

// CameraPlugin provide passport.CameraServiceServer implementations for individual groups of cameras.
// i.e. different makes/models of cameras may have different implementations for detection/control.
type CameraPlugin interface {
	// Name returns the plugin's name.
	Name() string
	// Inherit service interface for plugins.
	passport.CameraServiceServer
}

// RegisterCameraPlugin registers a switch controller plugin with the server application.
func RegisterCameraPlugin(plugin CameraPlugin) {
	cameraPlugins = append(cameraPlugins, plugin)
}

// HIDPlugin provides passport.HIDService implementations for individual HID devices.
type HIDPlugin interface {
	// Name returns the plugin's name.
	Name() string
	// GetHIDDevices probes for all HID Simulators.
	GetHIDDevices(ctx context.Context, req *passport.GetHIDDevicesRequest) (*passport.GetHIDDevicesResponse, error)
	// InitHIDDevice initializes the specified HID device.
	InitHIDDevice(ctx context.Context, req *passport.InitHIDDeviceRequest) (*passport.InitHIDDeviceResponse, error)
	// CloseHIDDevice releases the specified HID device and releases any resources held open.
	CloseHIDDevice(ctx context.Context, req *passport.CloseHIDDeviceRequest) (*passport.CloseHIDDeviceResponse, error)
	// KeyboardAction performs the requested keyboard action.
	KeyboardAction(ctx context.Context, req *passport.KeyboardActionRequest) (*passport.KeyboardActionResponse, error)
	// MouseAction performs the requested mouse action.
	MouseAction(ctx context.Context, req *passport.MouseActionRequest) (*passport.MouseActionResponse, error)
}

// RegisterHIDPlugin registers a HID controller plugin with the server application.
func RegisterHIDPlugin(plugin HIDPlugin) {
	hidPlugins = append(hidPlugins, plugin)
}

type UsbTesterPlugin interface {
	// Name returns the plugin's name.
	Name() string
	// Some testers require additional initialization to be done at a later time.
	Init() error
	// Inherit service interface for plugins.
	passport.UsbTesterServiceServer
}

// RegisterUsbTesterPlugin registers a usb tester controller plugin with the server application.
func RegisterUsbTesterPlugin(plugin UsbTesterPlugin) {
	usbTesterPlugins = append(usbTesterPlugins, plugin)
}

type VideoTesterPlugin interface {
	// Name returns the plugin's name.
	Name() string
	// Some testers require additional initialization to be done at a later time.
	Init() error
	// Inherit service interface for plugins.
	passport.VideoTesterServiceServer
}

// RegisterVideoTester registers a video tester controller plugin with the server application.
func RegisterVideoTester(plugin VideoTesterPlugin) {
	videoTesterPlugins = append(videoTesterPlugins, plugin)
}
