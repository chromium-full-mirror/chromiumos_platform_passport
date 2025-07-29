// Copyright 2025 The ChromiumOS Authors
// Use of this source code is governed by a BSD-style license that can be
// found in the LICENSE file.
package port

import (
	"testing"

	"github.com/google/go-cmp/cmp"
	"github.com/google/go-cmp/cmp/cmpopts"
)

func lessStrings(a, b string) bool {
	return a < b
}

func TestUsedPorts(t *testing.T) {
	pm := PortManager{}

	pm.UsePort("port1")
	pm.UsePort("port2")
	pm.UsePort("port3")
	pm.ReleasePort("port2")
	usedPorts := pm.GetUsedPorts()
	if !cmp.Equal(usedPorts, []string{"port1", "port3"}, cmpopts.SortSlices(lessStrings)) {
		t.Errorf("GetUsedPorts Want: %v, Got: %v", []string{"port1", "port3"}, usedPorts)
	}
	pm.ReleasePort("port3")
	usedPorts = pm.GetUsedPorts()
	if !cmp.Equal(usedPorts, []string{"port1"}, cmpopts.SortSlices(lessStrings)) {
		t.Errorf("GetUsedPorts Want: %v, Got: %v", []string{"port1"}, usedPorts)
	}
}

func TestIgnore(t *testing.T) {
	pm := PortManager{}
	pm.UsePort("port1")
	pm.UpdateIgnoredPorts([]string{"port1", "port2", "port3"})
	// ports we are using should not be ignored
	if pm.IsIgnored("port1") {
		t.Errorf("IsIgnored(port1) Want false, Got true")
	}

	if !pm.IsIgnored("port2") {
		t.Errorf("IsIgnored(port1) Want true, Got false")
	}

	if !pm.IsIgnored("port3") {
		t.Errorf("IsIgnored(port1) Want true, Got false")
	}

	if pm.IsIgnored("port4") {
		t.Errorf("IsIgnored(port1) Want false, Got true")
	}

	// check that update clears out old list
	pm.UpdateIgnoredPorts([]string{"port2"})

	if !pm.IsIgnored("port2") {
		t.Errorf("IsIgnored(port1) Want true, Got false")
	}

	if pm.IsIgnored("port3") {
		t.Errorf("IsIgnored(port1) Want false, Got true")
	}
}

func TestReleaseIgnored(t *testing.T) {
	pm := PortManager{}
	pm.UsePort("port1")
	pm.UpdateIgnoredPorts([]string{"port1"})
	// ports we are using should not be ignored
	if pm.IsIgnored("port1") {
		t.Errorf("IsIgnored(port1) Want false, Got true")
	}
	pm.ReleasePort("port1")
	if pm.IsIgnored("port1") {
		t.Errorf("IsIgnored(port1) Want false, Got true")
	}
}
