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
