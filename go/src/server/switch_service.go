// Copyright 2024 The ChromiumOS Authors
// Use of this source code is governed by a BSD-style license that can be
// found in the LICENSE file.

package server

import (
	"context"
	"fmt"

	"go.chromium.org/chromiumos/config/go/test/lab/api/passport"
)

// switchServiceServer implements api/passport.SwitchServiceServer and wraps individual
// switch plugins.
type switchServiceServer struct {
}

func newSwitchServiceServer(ctx context.Context) (passport.SwitchServiceServer, error) {
	return &switchServiceServer{}, nil
}

// GetSwitches probes all connected switches to the host device.
func (s *switchServiceServer) GetSwitches(ctx context.Context, req *passport.GetSwitchesRequest) (*passport.GetSwitchesResponse, error) {
	return nil, fmt.Errorf("not implemented")
}

// ResetAllSwitches re-initializes all found switches and sets them to the "disabled" state.
func (s *switchServiceServer) ResetAllSwitches(ctx context.Context, req *passport.ResetAllSwitchesRequest) (*passport.ResetAllSwitchesResponse, error) {
	return nil, fmt.Errorf("not implemented")
}

// ConfigureSwitchPort configures a single port on a switch.
func (s *switchServiceServer) ConfigureSwitchPort(ctx context.Context, req *passport.ConfigureSwitchPortRequest) (*passport.ConfigureSwitchPortResponse, error) {
	return nil, fmt.Errorf("not implemented")
}
