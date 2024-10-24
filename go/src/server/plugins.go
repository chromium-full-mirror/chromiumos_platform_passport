// Copyright 2024 The ChromiumOS Authors
// Use of this source code is governed by a BSD-style license that can be
// found in the LICENSE file.

package server

import (
	"go.chromium.org/chromiumos/config/go/test/lab/api/passport"
)

// module variables containing all registered plugins.
var (
	switchPlugins []SwitchPlugin
	cameraPlugins []CameraPlugin
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
