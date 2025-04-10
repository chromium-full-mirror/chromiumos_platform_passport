// Copyright 2024 The ChromiumOS Authors
// Use of this source code is governed by a BSD-style license that can be
// found in the LICENSE file.

package server

import (
	"go.chromium.org/chromiumos/config/go/test/lab/api/passport"
)

// module variables containing all registered plugins.
var (
	switchPlugins      []SwitchPlugin
	cameraPlugins      []CameraPlugin
	usbTesterPlugins   []UsbTesterPlugin
	videoTesterPlugins []VideoTesterPlugin
)

// SwitchPlugin provide passport.SwitchServiceServer implementations for individual groups of switches.
// i.e. different makes/models of switches may have different implementations for detection/control.
type SwitchPlugin interface {
	// Name returns the plugin's name for logging purposes.
	Name() string
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

// RegiseterVideoTester registers a video tester controller plugin with the server application.
func RegiseterVideoTester(plugin VideoTesterPlugin) {
	videoTesterPlugins = append(videoTesterPlugins, plugin)
}
