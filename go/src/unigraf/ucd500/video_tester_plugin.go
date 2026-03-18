// Copyright 2025 The ChromiumOS Authors
// Use of this source code is governed by a BSD-style license that can be
// found in the LICENSE file.

// Package ucd500 implements a Passport plugin for controlling UCD500 video testers.
package ucd500

import (
	"context"
	"fmt"
	"log/slog"

	"google.golang.org/grpc"

	"go.chromium.org/chromiumos/config/go/test/lab/api/passport"
	"go.chromiumos.org/chromiumos/platform/passport/server"
	"go.chromiumos.org/chromiumos/platform/passport/utils"
)

// videoTesterPlugin implements the passport.VideoTesterPlugin interface
// for controlling UCD500 devices.
type videoTesterPlugin struct {
	// unigraf_control_client is the gRPC client for communicating with the
	// external Unigraf control application.
	unigraf_control_client passport.VideoTesterServiceClient
}

// Constants for the path, address, and port of the external Unigraf control application.
const (
	// UNIGRAF_APP_PATH is the file path to the Unigraf control application executable.
	UNIGRAF_APP_PATH = "/bin/testervideoctl"
	// UNIGRAF_APP_ADDR is the network address where the Unigraf control application listens.
	UNIGRAF_APP_ADDR = "localhost"
	// UNIGRAF_APP_PORT is the network port where the Unigraf control application listens.
	UNIGRAF_APP_PORT = 0
)

// init registers this plugin with the Passport server during package initialization.
func init() {
	// Create an instance of the videoTesterPlugin.
	plugin := videoTesterPlugin{}
	// Register the plugin with the Passport server, making its methods available
	// via the Passport gRPC API.
	server.RegisterVideoTester(&plugin)
}

// Init initializes the video tester plugin. This includes starting the
// external Unigraf control application and establishing a gRPC connection.
func (s *videoTesterPlugin) Init() error {
	// Check if the plugin is already initialized. If so, log a warning and return nil.
	if s.unigraf_control_client != nil {
		slog.Warn("Plugin is already initialized", "name", s.Name())
		return nil
	}

	// Call the helper
	// We pass "0" to let the helper logic parse the resulting dynamic port
	dynamicPort, cmd, err := utils.LaunchPythonBridgefAndGetPort(
		UNIGRAF_APP_PATH,
		UNIGRAF_APP_PORT,
		"UCD500",
	)

	if err != nil {
		return fmt.Errorf("failed to launch unigraf app: %w", err)
	}

	// Log that the Unigraf control application has been started.
	slog.Info(
		"Started unigraf external controll app",
		"path", UNIGRAF_APP_PATH,
		"port", dynamicPort,
	)

	// Build the URI for connecting to the Unigraf control application.
	unigrafAppURI := fmt.Sprintf("%s:%d", UNIGRAF_APP_ADDR, dynamicPort)

	// Establish a gRPC connection to the Unigraf control application.
	conn, err := grpc.Dial(
		unigrafAppURI,
		grpc.WithInsecure(),
		grpc.WithDefaultCallOptions(
			grpc.MaxCallRecvMsgSize(256*1024*1024),
			grpc.MaxCallSendMsgSize(256*1024*1024),
		),
	)

	if err != nil {
		utils.KillPythonControl(cmd)
		return fmt.Errorf("unigraf plugin didn't connect err=%w", err)
	}

	// Create a new gRPC client for the VideoTester service.
	s.unigraf_control_client = passport.NewVideoTesterServiceClient(conn)
	// Log that the plugin has been successfully initialized.
	slog.Info("Unigraf usb tester plugin initialized.")

	return nil
}

// Name returns the name of this video tester plugin.
func (s *videoTesterPlugin) Name() string {
	return "UCD500"
}

// GetVideoTesters forwards the GetVideoTesters request to the Unigraf control application.
func (s *videoTesterPlugin) GetVideoTesters(
	ctx context.Context,
	req *passport.GetVideoTestersRequest,
) (*passport.GetVideoTestersResponse, error) {
	return s.unigraf_control_client.GetVideoTesters(ctx, req)
}

// OpenVideoTester forwards the OpenVideoTester request to the Unigraf control application.
func (s *videoTesterPlugin) OpenVideoTester(
	ctx context.Context,
	req *passport.OpenVideoTesterRequest,
) (*passport.OpenVideoTesterResponse, error) {
	return s.unigraf_control_client.OpenVideoTester(ctx, req)
}

// CloseVideoTester forwards the CloseVideoTester request to the Unigraf control application.
func (s *videoTesterPlugin) CloseVideoTester(
	ctx context.Context,
	req *passport.CloseVideoTesterRequest,
) (*passport.CloseVideoTesterResponse, error) {
	return s.unigraf_control_client.CloseVideoTester(ctx, req)
}

// GetRolesVideoTester forwards the GetRolesVideoTester request to the Unigraf control application.
func (s *videoTesterPlugin) GetRolesVideoTester(
	ctx context.Context,
	req *passport.GetRolesRequest,
) (*passport.GetRolesResponse, error) {
	return s.unigraf_control_client.GetRolesVideoTester(ctx, req)
}

// SetRoleVideoTester forwards the SetRoleVideoTester request to the Unigraf control application.
func (s *videoTesterPlugin) SetRoleVideoTester(
	ctx context.Context,
	req *passport.SetRoleRequest,
) (*passport.SetRoleResponse, error) {
	return s.unigraf_control_client.SetRoleVideoTester(ctx, req)
}

// LoadEdidVideoTester forwards the LoadEdidVideoTester request to the Unigraf control application.
func (s *videoTesterPlugin) LoadEdidVideoTester(
	ctx context.Context,
	req *passport.LoadEdidVideoTesterRequest,
) (*passport.LoadEdidVideoTesterResponse, error) {
	return s.unigraf_control_client.LoadEdidVideoTester(ctx, req)
}

// GetStreamInfoVideoTester handles the GetStreamInfoVideoTester gRPC request.
// It calls the GetStreamInfoVideoTester method of the corresponding plugin.
func (s *videoTesterPlugin) GetStreamInfoVideoTester(
	ctx context.Context,
	req *passport.GetStreamInfoVideoTesterRequest,
) (*passport.GetStreamInfoVideoTesterResponse, error) {
	// Call the GetStreamInfoVideoTester method of the found plugin.
	return s.unigraf_control_client.GetStreamInfoVideoTester(ctx, req)
}

// ScreenshotVideoTester handles the ScreenshotVideoTester gRPC request.
// It calls the ScreenshotVideoTester method of the corresponding plugin.
func (s *videoTesterPlugin) ScreenshotVideoTester(
	ctx context.Context,
	req *passport.ScreenshotVideoTesterRequest,
) (*passport.ScreenshotVideoTesterResponse, error) {
	// Call the ScreenshotVideoTester method of the found plugin.
	return s.unigraf_control_client.ScreenshotVideoTester(ctx, req)
}

// SetLinkVideoTester handles the SetLinkVideoTester gRPC request.
// It calls the SetLinkVideoTester method of the corresponding plugin.
func (s *videoTesterPlugin) SetLinkVideoTester(
	ctx context.Context,
	req *passport.SetLinkVideoTesterRequest,
) (*passport.SetLinkVideoTesterResponse, error) {
	// Call the SetLinkVideoTester method of the found plugin.
	return s.unigraf_control_client.SetLinkVideoTester(ctx, req)
}

// GetLinkVideoTester handles the GetLinkVideoTester gRPC request.
// It calls the GetLinkVideoTester method of the corresponding plugin.
func (s *videoTesterPlugin) GetLinkVideoTester(
	ctx context.Context,
	req *passport.GetLinkVideoTesterRequest,
) (*passport.GetLinkVideoTesterResponse, error) {
	// Call the GetLinkVideoTester method of the found plugin.
	return s.unigraf_control_client.GetLinkVideoTester(ctx, req)
}

// AttachVideoTester handles the AttachVideoTester gRPC request.
// It calls the AttachVideoTester method of the corresponding plugin.
func (s *videoTesterPlugin) AttachVideoTester(
	ctx context.Context,
	req *passport.AttachVideoTesterRequest,
) (*passport.AttachVideoTesterResponse, error) {
	// Call the AttachVideoTester method of the found plugin.
	return s.unigraf_control_client.AttachVideoTester(ctx, req)
}

// HpdPulseVideoTester handles the AttachVideoTester gRPC request.
// It calls the HpdPulseVideoTester method of the corresponding plugin.
func (s *videoTesterPlugin) HpdPulseVideoTester(
	ctx context.Context,
	req *passport.HpdPulseVideoTesterRequest,
) (*passport.HpdPulseVideoTesterResponse, error) {
	// Call the AttachVideoTester method of the found plugin.
	return s.unigraf_control_client.HpdPulseVideoTester(ctx, req)
}

// RunComplianceTest runs compliance test(s).
func (s *videoTesterPlugin) RunComplianceTest(
	ctx context.Context,
	req *passport.RunComplianceTestRequest,
) (*passport.RunComplianceTestResponse, error) {
	// Call the AttachVideoTester method of the found plugin.
	return s.unigraf_control_client.RunComplianceTest(ctx, req)
}

// Runs StartEventCapture.
func (s *videoTesterPlugin) StartEventCapture(
	ctx context.Context,
	req *passport.StartEventCaptureRequest,
) (*passport.StartEventCaptureResponse, error) {
	// Call the StartEventCapture method of the found plugin.
	return s.unigraf_control_client.StartEventCapture(ctx, req)
}

// Runs StopEventCapture.
func (s *videoTesterPlugin) StopEventCapture(
	ctx context.Context,
	req *passport.StopEventCaptureRequest,
) (*passport.StopEventCaptureResponse, error) {
	// Call the StopEventCapture method of the found plugin.
	return s.unigraf_control_client.StopEventCapture(ctx, req)
}

// Runs PowerCycle.
func (s *videoTesterPlugin) PowerCycle(
	ctx context.Context,
	req *passport.PowerCycleRequest,
) (*passport.PowerCycleResponse, error) {
	// Call the PowerCycle method of the found plugin.
	return s.unigraf_control_client.PowerCycle(ctx, req)
}
