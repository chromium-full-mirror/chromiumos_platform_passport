// Copyright 2025 The ChromiumOS Authors
// Use of this source code is governed by a BSD-style license that can be
// found in the LICENSE file.

// Package acroname provides support for interacting with acroname devices.
package acroname

import (
	"context"
	"fmt"
	"log/slog"

	"go.chromium.org/chromiumos/config/go/test/lab/api/passport"
	"go.chromiumos.org/chromiumos/platform/passport/port"
	"go.chromiumos.org/chromiumos/platform/passport/server"
	"go.chromiumos.org/chromiumos/platform/passport/utils"
	"google.golang.org/grpc"
)

const (
	APP_PATH = "/bin/acronamectl"
	APP_ADDR = "localhost"
	APP_PORT = 0
)

// switchPlugin is an acroname switch plugin.
type switchPlugin struct {
	client passport.SwitchServiceClient

	// inherit port manager implementation to comply with the interface.
	// acroname switches do no use serial ports so there is no possible
	// interference between different switches.
	port.PortManager
}

func init() {
	// Register the switch plugin with the main passport application.
	server.RegisterSwitchPlugin(&switchPlugin{})
}

// Some testers require additional initialization to be done at a later time.
func (s *switchPlugin) Init(ctx context.Context) error {
	// Check if the plugin is already initialized. If so, log a warning and return nil.
	if s.client != nil {
		slog.Warn("Plugin is already initialized", "name", s.Name())
		return nil
	}

	// Call the helper
	// We pass "0" to let the helper logic parse the resulting dynamic port
	dynamicPort, cmd, err := utils.LaunchPythonBridgefAndGetPort(
		APP_PATH,
		APP_PORT,
		"",
	)

	if err != nil {
		return fmt.Errorf("failed to launch app: %w", err)
	}

	// Log that the control application has been started.
	slog.Info(
		"Started external controll app",
		"path", APP_PATH,
		"port", dynamicPort,
	)

	// Build the URI for connecting to the control application.
	acronameAppURI := fmt.Sprintf("%s:%d", APP_ADDR, dynamicPort)

	// Establish a gRPC connection to the control application.
	conn, err := grpc.Dial(
		acronameAppURI,
		grpc.WithInsecure(),
	)

	if err != nil {
		utils.KillPythonControl(cmd)
		return fmt.Errorf("acroname plugin didn't connect err=%w", err)
	}

	s.client = passport.NewSwitchServiceClient(conn)
	slog.Info("Acroname switch plugin initialized.")

	return nil
}

// GetSwitches probes all acroname switches connected to the host.
func (s *switchPlugin) GetSwitches(ctx context.Context, req *passport.GetSwitchesRequest) (*passport.GetSwitchesResponse, error) {
	slog.Info("Getting switches", "req", req)
	return s.client.GetSwitches(ctx, req)
}

// ConfigureSwitchPort configures a single port on a switch.
func (s *switchPlugin) ConfigureSwitchPort(ctx context.Context, req *passport.ConfigureSwitchPortRequest) (*passport.ConfigureSwitchPortResponse, error) {
	slog.Info("Configuring switch", "switch", req.GetSwitchId(), "state", req.GetState(), "port id", req.GetPortId())
	return s.client.ConfigureSwitchPort(ctx, req)
}

// ResetAllSwitches re-initializes all found switches and sets them to the "disabled" state.
func (s *switchPlugin) ResetAllSwitches(ctx context.Context, req *passport.ResetAllSwitchesRequest) (*passport.ResetAllSwitchesResponse, error) {
	slog.Info("Resetting switches", "req", req)
	return s.client.ResetAllSwitches(ctx, req)
}

// Name returns the plugin's name for logging purposes.
func (s *switchPlugin) Name() string {
	return "acroname_switch_plugin"
}
