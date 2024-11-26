// Copyright 2025 The ChromiumOS Authors
// Use of this source code is governed by a BSD-style license that can be
// found in the LICENSE file.

// Package unigraf provides support for interacting with unigraf usb testers.
package unigraf

import (
	"context"
	"log"

	"google.golang.org/grpc"
	"google.golang.org/grpc/credentials/insecure"

	"go.chromium.org/chromiumos/config/go/test/lab/api/passport"
	"go.chromiumos.org/chromiumos/platform/passport/server"
)

// usbTesterPlugin is an unigraf usb tester plugin.
type usbTesterPlugin struct {
	unigraf_control_client passport.UsbTesterServiceClient
}

func init() {
	plugin := usbTesterPlugin{}

	conn, err := grpc.Dial("localhost:8081", grpc.WithTransportCredentials(insecure.NewCredentials()))
	if err != nil {
		log.Fatalf("Unigraf plugin didn't connect: %v", err)
	}

	plugin.unigraf_control_client = passport.NewUsbTesterServiceClient(conn)

	// Register the unigraf tester plugin with the main passport application.
	server.RegisterUsbTesterPlugin(&plugin)
}

// Name returns the plugin's name for logging purposes.
func (s *usbTesterPlugin) Name() string {
	return "unigraf_usb_tester"
}

// This plugin implementation will only pass the request to the actual control application
func (s *usbTesterPlugin) GetTesters(ctx context.Context, req *passport.GetTestersRequest) (*passport.GetTestersReply, error) {
	return s.unigraf_control_client.GetTesters(ctx, req)
}

// This plugin implementation will only pass the request to the actual control application
func (s *usbTesterPlugin) GetTesterCapability(ctx context.Context, req *passport.GetUsbTesterCapabilityRequest) (*passport.GetUsbTesterCapabilityReply, error) {
	return s.unigraf_control_client.GetTesterCapability(ctx, req)
}

// This plugin implementation will only pass the request to the actual control application
func (s *usbTesterPlugin) SetTesterCapability(ctx context.Context, req *passport.SetUsbTesterCapabilityRequest) (*passport.SetUsbTesterCapabilityReply, error) {
	return s.unigraf_control_client.SetTesterCapability(ctx, req)
}

// ReplugCable replugs the cable on the USB tester.
func (s *usbTesterPlugin) ReplugCable(ctx context.Context, req *passport.DoCableReplugRequest) (*passport.DoCableReplugReply, error) {
	// This function simply forwards the request to the unigraf_control_client.
	return s.unigraf_control_client.ReplugCable(ctx, req)
}

// HardResetTester performs a hard reset of the USB tester.
func (s *usbTesterPlugin) HardResetTester(ctx context.Context, req *passport.HardResetTesterRequest) (*passport.HardResetTesterReply, error) {
	// This function simply forwards the request to the unigraf_control_client.
	return s.unigraf_control_client.HardResetTester(ctx, req)
}

// OpenTester opens a connection to the USB tester.
func (s *usbTesterPlugin) OpenTester(ctx context.Context, req *passport.OpenTesterRequest) (*passport.OpenTesterReply, error) {
	// This function simply forwards the request to the unigraf_control_client.
	return s.unigraf_control_client.OpenTester(ctx, req)
}

// CloseTester closes the connection to the USB tester.
func (s *usbTesterPlugin) CloseTester(ctx context.Context, req *passport.CloseTesterRequest) (*passport.CloseTesterReply, error) {
	// This function simply forwards the request to the unigraf_control_client.
	return s.unigraf_control_client.CloseTester(ctx, req)
}
