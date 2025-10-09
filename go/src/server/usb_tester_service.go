// Copyright 2025 The ChromiumOS Authors
// Use of this source code is governed by a BSD-style license that can be
// found in the LICENSE file.

package server

import (
	"context"
	"fmt"
	"log/slog"

	"go.chromium.org/chromiumos/config/go/test/lab/api/passport"
	"google.golang.org/grpc/codes"
	"google.golang.org/grpc/status"
)

// usbTesterServiceServer implements api/passport.UsbTesterServiceServer and wraps individual
// usb tester plugins.
// Let's say we have the following tolopogy:
//
// HOST
// |
// |--PLUGIN_X
// |  |-- DEVICE_2
// |  |-- DEVICE_3
// |
// |--PLUGIN_Y
// |  |-- DEVICE_2
// |  |-- DEVICE_3
// |
// In this service, "plugins" will hold a reference to both plugins, so plugins = [PLUGIN_X, PLUGIN_Y].
// This array is populated by the plugins's init function.
// Once a GetTesters request is issued, testerMap will be populated and will look like:
// HOST.testerMap[S1] = PLUGIN_X
// HOST.testerMap[S2] = PLUGIN_X
// HOST.testerMap[S3] = PLUGIN_Y
// HOST.testerMap[S4] = PLUGIN_Y
// To dispatch requests, we use the ids(serials) in the request message along with
// the testerMap of the service to get the appropriate plugin.
// For example, if we do a OpenTester(id=S2) the OpenTester will check the testerMap
// and will find that PLUGIN_X is responsible for for that tester as "HOST.testerMap[S2] = PLUGIN_X"
// so the service will call PLUGIN_X.OpenTester(...) to do the actual handling.
type usbTesterServiceServer struct {
	// Maps individual usb testers to their controlling testerMap.
	testerMap map[string]UsbTesterPlugin
	// All registered plugins.
	plugins []UsbTesterPlugin
}

func newUsbTesterServiceServer(
	ctx context.Context,
) (passport.UsbTesterServiceServer, error) {
	i := 0
	for _, elem := range usbTesterPlugins {
		if err := elem.Init(); err != nil {
			slog.Error("Failed to initialize usb tester", slog.Any("err", err))
			continue
		}
		usbTesterPlugins[i] = elem
		i++
	}
	usbTesterPlugins = usbTesterPlugins[:i]

	s := &usbTesterServiceServer{
		testerMap: make(map[string]UsbTesterPlugin),
		plugins:   usbTesterPlugins,
	}

	return s, nil
}

// This function will get all of the connected usb testers. It will update the id(serial) to plugin map of the service.
// If we refer to the topology from usbTesterServiceServer:
// HOST.GetTesters will call the refresh function which in turn will call both:
// - PLUGIN_X.GetTesters, it will yield [(S1, "PLUGIN_X_NAME"), (S2, "PLUGIN_X_NAME")]
// - PLUGIN_Y.GetTesters, it will yield [(S3, "PLUGIN_Y_NAME"), (S4, "PLUGIN_Y_NAME")]
// so HOST.refreshTesters will return [(S1, "PLUGIN_X_NAME"), (S2, "PLUGIN_X_NAME"), (S3, "PLUGIN_Y_NAME"), (S4,"PLUGIN_Y_NAME")]
// and so will HOST.GetTesters.
func (s *usbTesterServiceServer) GetTesters(
	ctx context.Context,
	req *passport.GetTestersRequest,
) (*passport.GetTestersReply, error) {
	slog.Info("Received passport.GetTestersRequest", "req", req)

	testers, err := s.refreshTesters(ctx, req)
	if err != nil {
		return nil, fmt.Errorf("failed to refresh testers: %w", err)
	}

	return &passport.GetTestersReply{
		Testers: testers,
	}, nil
}

// This function's behaviour is explained in the description of
// usbTesterServiceServer.GetTesters.
func (s *usbTesterServiceServer) refreshTesters(
	ctx context.Context,
	req *passport.GetTestersRequest,
) ([]*passport.UsbTester, error) {

	testerMap := make(map[string]UsbTesterPlugin)
	var testers []*passport.UsbTester

	for _, plugin := range s.plugins {
		resp, err := plugin.GetTesters(ctx, req)

		if err != nil {
			return nil, fmt.Errorf(
				"failed to get testers for plugin %q: %w",
				plugin.Name(),
				err,
			)
		}

		for _, sw := range resp.GetTesters() {
			id := sw.GetId()
			if id == "" {
				return nil, fmt.Errorf(
					"received empty tester ID, plugin: %q",
					plugin.Name(),
				)
			}

			if pOld, ok := testerMap[id]; ok {
				return nil, fmt.Errorf(
					"received duplicate tester ID: %q, plugin1 %q, plugin2 %q",
					id,
					pOld.Name(),
					plugin.Name(),
				)
			}

			testers = append(testers, sw)
			testerMap[id] = plugin
		}
	}

	slog.Info("Found testers", "testers", testers)
	s.testerMap = testerMap
	return testers, nil
}

// Retrieves the capabilities of a USB tester with the given ID.
// If no tester with the specified ID is found, it returns a NotFound error.
func (s *usbTesterServiceServer) GetTesterCapability(
	ctx context.Context,
	req *passport.GetUsbTesterCapabilityRequest,
) (*passport.GetUsbTesterCapabilityReply, error) {

	tester := s.testerMap[req.Id]
	if tester == nil {
		return nil, status.Errorf(
			codes.NotFound,
			fmt.Sprintf("there is no USB tester with id: %s", req.Id),
		)
	}

	return tester.GetTesterCapability(ctx, req)
}

// Sets the capabilities of a USB tester with the given ID.
// If no tester with the specified ID is found, it returns a NotFound error.
func (s *usbTesterServiceServer) SetTesterCapability(
	ctx context.Context,
	req *passport.SetUsbTesterCapabilityRequest,
) (*passport.SetUsbTesterCapabilityReply, error) {

	tester := s.testerMap[req.Id]
	if tester == nil {
		return nil, status.Errorf(
			codes.NotFound,
			fmt.Sprintf("there is no USB tester with id: %s", req.Id),
		)
	}

	return tester.SetTesterCapability(ctx, req)
}

// Instructs a USB tester to replug the connected cable.
// If no tester with the specified ID is found, it returns a NotFound error.
func (s *usbTesterServiceServer) ReplugCable(
	ctx context.Context,
	req *passport.DoCableReplugRequest,
) (*passport.DoCableReplugReply, error) {

	tester := s.testerMap[req.Id]
	if tester == nil {
		return nil, status.Errorf(
			codes.NotFound,
			fmt.Sprintf("there is no USB tester with id: %s", req.Id),
		)
	}

	return tester.ReplugCable(ctx, req)
}

// Performs a hard reset on a USB tester with the given ID.
// If no tester with the specified ID is found, it returns a NotFound error.
func (s *usbTesterServiceServer) HardResetTester(
	ctx context.Context,
	req *passport.HardResetTesterRequest,
) (*passport.HardResetTesterReply, error) {

	tester := s.testerMap[req.Id]
	if tester == nil {
		return nil, status.Errorf(
			codes.NotFound,
			fmt.Sprintf("there is no USB tester with id: %s", req.Id),
		)
	}

	return tester.HardResetTester(ctx, req)
}

// Opens a connection to a USB tester with the given ID.
// If no tester with the specified ID is found, it returns a NotFound error.
func (s *usbTesterServiceServer) OpenTester(
	ctx context.Context,
	req *passport.OpenTesterRequest,
) (*passport.OpenTesterReply, error) {

	tester := s.testerMap[req.Id]
	if tester == nil {
		return nil, status.Errorf(
			codes.NotFound,
			fmt.Sprintf("there is no USB tester with id: %s", req.Id),
		)
	}

	return tester.OpenTester(ctx, req)
}

// Closes the connection to a USB tester with the given ID.
// If no tester with the specified ID is found, it returns a NotFound error.
func (s *usbTesterServiceServer) CloseTester(
	ctx context.Context,
	req *passport.CloseTesterRequest,
) (*passport.CloseTesterReply, error) {

	tester := s.testerMap[req.Id]
	if tester == nil {
		return nil, status.Errorf(
			codes.NotFound,
			fmt.Sprintf("there is no USB tester with id: %s", req.Id),
		)
	}

	return tester.CloseTester(ctx, req)
}

// Get the display port alternate mode information.
func (s *usbTesterServiceServer) GetDpInfo(
	ctx context.Context,
	req *passport.GetDpInfoRequest,
) (*passport.GetDpInfoReply, error) {

	tester := s.testerMap[req.Id]
	if tester == nil {
		return nil, status.Errorf(
			codes.NotFound,
			fmt.Sprintf("there is no USB tester with id: %s", req.Id),
		)
	}

	return tester.GetDpInfo(ctx, req)
}

// This method is used to get the active test port on the testing device.
func (s *usbTesterServiceServer) GetActivePort(
	ctx context.Context,
	req *passport.GetActivePortRequest,
) (*passport.GetActivePortReply, error) {

	tester := s.testerMap[req.Id]
	if tester == nil {
		return nil, status.Errorf(
			codes.NotFound,
			fmt.Sprintf("there is no USB tester with id: %s", req.Id),
		)
	}

	return tester.GetActivePort(ctx, req)
}

// This method is used to set the active test port on the testing device.
func (s *usbTesterServiceServer) SetActivePort(
	ctx context.Context,
	req *passport.SetActivePortRequest,
) (*passport.SetActivePortReply, error) {

	tester := s.testerMap[req.Id]
	if tester == nil {
		return nil, status.Errorf(
			codes.NotFound,
			fmt.Sprintf("there is no USB tester with id: %s", req.Id),
		)
	}

	return tester.SetActivePort(ctx, req)
}

// This method is used to load an EDID.
func (s *usbTesterServiceServer) LoadEdid(
	ctx context.Context,
	req *passport.LoadEdidRequest,
) (*passport.LoadEdidReply, error) {

	tester := s.testerMap[req.Id]
	if tester == nil {
		return nil, status.Errorf(
			codes.NotFound,
			fmt.Sprintf("there is no USB tester with id: %s", req.Id),
		)
	}

	return tester.LoadEdid(ctx, req)
}

// This method is used to reset the PD communication.
func (s *usbTesterServiceServer) ResetPd(
	ctx context.Context,
	req *passport.ResetPdRequest,
) (*passport.ResetPdReply, error) {

	tester := s.testerMap[req.Id]
	if tester == nil {
		return nil, status.Errorf(
			codes.NotFound,
			fmt.Sprintf("there is no USB tester with id: %s", req.Id),
		)
	}

	return tester.ResetPd(ctx, req)
}

// This method is used get the power delivery objects.
func (s *usbTesterServiceServer) GetPdos(
	ctx context.Context,
	req *passport.GetPdosRequest,
) (*passport.GetPdosReply, error) {

	tester := s.testerMap[req.Id]
	if tester == nil {
		return nil, status.Errorf(
			codes.NotFound,
			fmt.Sprintf("there is no USB tester with id: %s", req.Id),
		)
	}

	return tester.GetPdos(ctx, req)
}

// This method is used send a VDM HPDs
func (s *usbTesterServiceServer) SendVdmHpd(
	ctx context.Context,
	req *passport.SendVdmHpdRequest,
) (*passport.SendVdmHpdReply, error) {

	tester := s.testerMap[req.Id]
	if tester == nil {
		return nil, status.Errorf(
			codes.NotFound,
			fmt.Sprintf("there is no USB tester with id: %s", req.Id),
		)
	}

	return tester.SendVdmHpd(ctx, req)
}

// Simulate a key press. ATM this will simulate the "G" key press.
func (s *usbTesterServiceServer) SimulateKeyPress(
	ctx context.Context,
	req *passport.SimulateKeyPressRequest,
) (*passport.SimulateKeyPressReply, error) {

	tester := s.testerMap[req.Id]
	if tester == nil {
		return nil, status.Errorf(
			codes.NotFound,
			fmt.Sprintf("there is no USB tester with id: %s", req.Id),
		)
	}

	return tester.SimulateKeyPress(ctx, req)
}

// Send a PD alert message to partner.
func (s *usbTesterServiceServer) SendPdAlert(
	ctx context.Context,
	req *passport.SendPdAlertRequest,
) (*passport.SendPdAlertReply, error) {

	tester := s.testerMap[req.Id]
	if tester == nil {
		return nil, status.Errorf(
			codes.NotFound,
			fmt.Sprintf("there is no USB tester with id: %s", req.Id),
		)
	}

	return tester.SendPdAlert(ctx, req)
}

// Get statistics about the PD requests.
func (s *usbTesterServiceServer) GetPdStats(
	ctx context.Context,
	req *passport.GetPdStatsRequest,
) (*passport.GetPdStatsReply, error) {

	tester := s.testerMap[req.Id]
	if tester == nil {
		return nil, status.Errorf(
			codes.NotFound,
			fmt.Sprintf("there is no USB tester with id: %s", req.Id),
		)
	}

	return tester.GetPdStats(ctx, req)
}

// Reset the PD statistics.
func (s *usbTesterServiceServer) ResetPdStats(
	ctx context.Context,
	req *passport.ResetPdStatsRequest,
) (*passport.ResetPdStatsReply, error) {

	tester := s.testerMap[req.Id]
	if tester == nil {
		return nil, status.Errorf(
			codes.NotFound,
			fmt.Sprintf("there is no USB tester with id: %s", req.Id),
		)
	}

	return tester.ResetPdStats(ctx, req)
}
