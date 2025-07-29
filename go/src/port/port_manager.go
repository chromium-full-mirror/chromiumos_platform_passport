// Copyright 2025 The ChromiumOS Authors
// Use of this source code is governed by a BSD-style license that can be
// found in the LICENSE file.

// Package port provides support for managing which ports are used by plugins
// and preventing duplicate probes.
package port

// PortManager can be embedded in a plugin to help manage serial port usage.
type PortManager struct {
	ignoredPorts map[string]struct{}
	usedPorts    map[string]struct{}
}

// UpdateIgnoredPorts informs the plugin of serial ports that are in use
// and should be ignored during probing.
func (pm *PortManager) UpdateIgnoredPorts(ports []string) {
	pm.ignoredPorts = make(map[string]struct{})
	for _, port := range ports {
		pm.ignoredPorts[port] = struct{}{}
	}
}

// GetUsedPorts returns a list of ports that the plugin is currently using.
func (pm *PortManager) GetUsedPorts() []string {
	usedPorts := []string{}
	for port := range pm.usedPorts {
		usedPorts = append(usedPorts, port)
	}
	return usedPorts
}

// UsePort marks a port as used by the plugin
func (pm *PortManager) UsePort(port string) {
	if pm.usedPorts == nil {
		pm.usedPorts = make(map[string]struct{})
	}
	pm.usedPorts[port] = struct{}{}
}

// UsePort marks a port as used by the plugin
func (pm *PortManager) ReleasePort(port string) {
	delete(pm.usedPorts, port)
	delete(pm.ignoredPorts, port)
}

// IsIgnored checks if a given port should be ignored.
func (pm *PortManager) IsIgnored(port string) bool {
	if _, ok := pm.usedPorts[port]; ok {
		return false
	}
	_, ok := pm.ignoredPorts[port]
	return ok
}
