// Copyright 2025 The ChromiumOS Authors
// Use of this source code is governed by a BSD-style license that can be
// found in the LICENSE file.

// Package unigraf provides support for interacting with unigraf usb testers.
package utc274

import (
	"context"
	"fmt"
	"log/slog"

	"google.golang.org/grpc"
	"google.golang.org/grpc/credentials/insecure"

	"go.chromium.org/chromiumos/config/go/test/lab/api/passport"
	"go.chromiumos.org/chromiumos/platform/passport/server"
	"go.chromiumos.org/chromiumos/platform/passport/utils"
)

// usbTesterPlugin is an unigraf usb tester plugin.
type usbTesterPlugin struct {
	unigraf_control_client passport.UsbTesterServiceClient
}

const (
	UNIGRAF_APP_PATH = "/bin/testerusbctl"
	UNIGRAF_APP_ADDR = "localhost"
	UNIGRAF_APP_PORT = 0
)

func init() {
	plugin := usbTesterPlugin{}

	// Register the unigraf tester plugin with the main passport application.
	server.RegisterUsbTesterPlugin(&plugin)
}

// Some testers require additional initialization to be done at a later time.
func (s *usbTesterPlugin) Init() error {
	if s.unigraf_control_client != nil {
		slog.Warn("Plugin is already initialized", "name", s.Name())
		return nil
	}

	// Call the helper
	// We pass "0" to let the helper logic parse the resulting dynamic port
	dynamicPort, cmd, err := utils.LaunchPythonBridgefAndGetPort(
		UNIGRAF_APP_PATH,
		UNIGRAF_APP_PORT,
		"UTC274",
	)

	if err != nil {
		return fmt.Errorf("failed to launch unigraf app: %w", err)
	}

	slog.Info(
		"Started unigraf external control app",
		"path", UNIGRAF_APP_PATH,
		"port", dynamicPort,
	)

	// Build URI and Dial
	unigrafAppURI := fmt.Sprintf("%s:%d", UNIGRAF_APP_ADDR, dynamicPort)

	conn, err := grpc.Dial(
		unigrafAppURI,
		grpc.WithTransportCredentials(insecure.NewCredentials()),
	)

	if err != nil {
		utils.KillPythonControl(cmd)
		return fmt.Errorf("unigraf plugin didn't connect err=%w", err)
	}

	s.unigraf_control_client = passport.NewUsbTesterServiceClient(conn)
	slog.Info("Unigraf usb tester plugin initialized.")

	return nil
}

// Name returns the plugin's name for logging purposes.
func (s *usbTesterPlugin) Name() string {
	return "unigraf_usb_tester"
}

// This plugin implementation will only pass the request to the actual control application
func (s *usbTesterPlugin) GetTesters(
	ctx context.Context,
	req *passport.GetTestersRequest,
) (*passport.GetTestersReply, error) {
	return s.unigraf_control_client.GetTesters(ctx, req)
}

// This plugin implementation will only pass the request to the actual control application
func (s *usbTesterPlugin) GetTesterCapability(
	ctx context.Context,
	req *passport.GetUsbTesterCapabilityRequest,
) (*passport.GetUsbTesterCapabilityReply, error) {
	return s.unigraf_control_client.GetTesterCapability(ctx, req)
}

// This plugin implementation will only pass the request to the actual control application
func (s *usbTesterPlugin) SetTesterCapability(
	ctx context.Context,
	req *passport.SetUsbTesterCapabilityRequest,
) (*passport.SetUsbTesterCapabilityReply, error) {
	return s.unigraf_control_client.SetTesterCapability(ctx, req)
}

// ReplugCable replugs the cable on the USB tester.
func (s *usbTesterPlugin) ReplugCable(
	ctx context.Context,
	req *passport.DoCableReplugRequest,
) (*passport.DoCableReplugReply, error) {
	// This function simply forwards the request to the unigraf_control_client.
	return s.unigraf_control_client.ReplugCable(ctx, req)
}

// HardResetTester performs a hard reset of the USB tester.
func (s *usbTesterPlugin) HardResetTester(
	ctx context.Context,
	req *passport.HardResetTesterRequest,
) (*passport.HardResetTesterReply, error) {
	// This function simply forwards the request to the unigraf_control_client.
	return s.unigraf_control_client.HardResetTester(ctx, req)
}

// OpenTester opens a connection to the USB tester.
func (s *usbTesterPlugin) OpenTester(
	ctx context.Context,
	req *passport.OpenTesterRequest,
) (*passport.OpenTesterReply, error) {
	// This function simply forwards the request to the unigraf_control_client.
	return s.unigraf_control_client.OpenTester(ctx, req)
}

// CloseTester closes the connection to the USB tester.
func (s *usbTesterPlugin) CloseTester(
	ctx context.Context,
	req *passport.CloseTesterRequest,
) (*passport.CloseTesterReply, error) {
	// This function simply forwards the request to the unigraf_control_client.
	return s.unigraf_control_client.CloseTester(ctx, req)
}

// Get the display port alternate mode information.
func (s *usbTesterPlugin) GetDpInfo(
	ctx context.Context,
	req *passport.GetDpInfoRequest,
) (*passport.GetDpInfoReply, error) {
	// This function simply forwards the request to the unigraf_control_client.
	return s.unigraf_control_client.GetDpInfo(ctx, req)
}

// This method is used to get the active test port on the testing device.
func (s *usbTesterPlugin) GetActivePort(
	ctx context.Context,
	req *passport.GetActivePortRequest,
) (*passport.GetActivePortReply, error) {

	return s.unigraf_control_client.GetActivePort(ctx, req)
}

// This method is used to set the active test port on the testing device.
func (s *usbTesterPlugin) SetActivePort(
	ctx context.Context,
	req *passport.SetActivePortRequest,
) (*passport.SetActivePortReply, error) {

	return s.unigraf_control_client.SetActivePort(ctx, req)
}

// This method is used to load an EDID.
func (s *usbTesterPlugin) LoadEdid(
	ctx context.Context,
	req *passport.LoadEdidRequest,
) (*passport.LoadEdidReply, error) {

	return s.unigraf_control_client.LoadEdid(ctx, req)
}

// This method is used to reset power delivery.
func (s *usbTesterPlugin) ResetPd(
	ctx context.Context,
	req *passport.ResetPdRequest,
) (*passport.ResetPdReply, error) {

	return s.unigraf_control_client.ResetPd(ctx, req)
}

// This method is used get the power delivery objects.
func (s *usbTesterPlugin) GetPdos(
	ctx context.Context,
	req *passport.GetPdosRequest,
) (*passport.GetPdosReply, error) {

	return s.unigraf_control_client.GetPdos(ctx, req)
}

// This method is used send a VDM HPDs
func (s *usbTesterPlugin) SendVdmHpd(
	ctx context.Context,
	req *passport.SendVdmHpdRequest,
) (*passport.SendVdmHpdReply, error) {

	return s.unigraf_control_client.SendVdmHpd(ctx, req)
}

// Simulate a key press. ATM this will simulate the "G" key press.
func (s *usbTesterPlugin) SimulateKeyPress(
	ctx context.Context,
	req *passport.SimulateKeyPressRequest,
) (*passport.SimulateKeyPressReply, error) {

	return s.unigraf_control_client.SimulateKeyPress(ctx, req)
}

// Send a PD alert message to partner.
func (s *usbTesterPlugin) SendPdAlert(
	ctx context.Context,
	req *passport.SendPdAlertRequest,
) (*passport.SendPdAlertReply, error) {
	return s.unigraf_control_client.SendPdAlert(ctx, req)
}

// Get statistics about the PD requests.
func (s *usbTesterPlugin) GetPdStats(
	ctx context.Context,
	req *passport.GetPdStatsRequest,
) (*passport.GetPdStatsReply, error) {
	return s.unigraf_control_client.GetPdStats(ctx, req)
}

// Reset the PD statistics.
func (s *usbTesterPlugin) ResetPdStats(
	ctx context.Context,
	req *passport.ResetPdStatsRequest,
) (*passport.ResetPdStatsReply, error) {
	return s.unigraf_control_client.ResetPdStats(ctx, req)
}
