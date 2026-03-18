// Copyright 2025 The ChromiumOS Authors
// Use of this source code is governed by a BSD-style license that can be
// found in the LICENSE file.

// Package server implements the gRPC server for the VideoTester service in Passport.
package server

import (
	"context"
	"fmt"
	"log/slog"

	"go.chromium.org/chromiumos/config/go/test/lab/api/passport"
	"google.golang.org/grpc/codes"
	"google.golang.org/grpc/status"
)

// videoTesterServiceServer implements the passport.VideoTesterServiceServer interface.
// It manages a collection of VideoTesterPlugin implementations.
type videoTesterServiceServer struct {
	// testerMap is a map of video tester IDs to their corresponding VideoTesterPlugin.
	testerMap map[string]VideoTesterPlugin
	// plugins is a slice of registered VideoTesterPlugin implementations.
	plugins []VideoTesterPlugin
}

// newVideoTesterServiceServer creates a new instance of videoTesterServiceServer.
// It initializes the registered VideoTesterPlugins.
func newVideoTesterServiceServer(
	ctx context.Context,
) (passport.VideoTesterServiceServer, error) {
	// Iterate through the globally registered video tester plugins.
	i := 0
	for _, elem := range videoTesterPlugins {
		// Initialize each plugin. If initialization fails, log an error and skip the plugin.
		if err := elem.Init(); err != nil {
			slog.Error("Failed to initialize tester", slog.Any("err", err))
			continue
		}
		// If initialization is successful, keep the plugin in the slice.
		videoTesterPlugins[i] = elem
		i++
	}
	// Trim the slice of plugins to only include the successfully initialized ones.
	videoTesterPlugins = videoTesterPlugins[:i]

	// Create and return a new videoTesterServiceServer instance.
	s := &videoTesterServiceServer{
		testerMap: make(map[string]VideoTesterPlugin),
		plugins:   videoTesterPlugins,
	}

	return s, nil
}

// GetVideoTesters handles the GetVideoTesters gRPC request.
// It retrieves a list of available video testers from all registered plugins.
func (s *videoTesterServiceServer) GetVideoTesters(
	ctx context.Context,
	req *passport.GetVideoTestersRequest,
) (*passport.GetVideoTestersResponse, error) {
	// Log the received request for debugging purposes.
	slog.Info("Received passport.GetTestersRequest", "req", req)

	// Refresh the list of available testers by querying all plugins.
	testers, err := s.refreshTesters(ctx, req)
	if err != nil {
		return nil, fmt.Errorf("failed to refresh testers: %w", err)
	}

	// Return the list of video testers in the gRPC response.
	return &passport.GetVideoTestersResponse{
		Testers: testers,
	}, nil
}

// refreshTesters queries all registered VideoTesterPlugins for their available testers.
// It aggregates the results and checks for duplicate tester IDs.
func (s *videoTesterServiceServer) refreshTesters(
	ctx context.Context,
	req *passport.GetVideoTestersRequest,
) ([]*passport.VideoTester, error) {
	// Create a map to store tester IDs and the plugin they belong to, to detect duplicates.
	testerMap := make(map[string]VideoTesterPlugin)
	// Create a slice to store the aggregated list of video testers.
	var testers []*passport.VideoTester

	// Iterate through all registered video tester plugins.
	for _, plugin := range s.plugins {
		// Call the GetVideoTesters method of the current plugin.
		resp, err := plugin.GetVideoTesters(ctx, req)

		// If there's an error while getting testers from a plugin, log it and return the error.
		if err != nil {
			return nil, fmt.Errorf(
				"failed to get testers for plugin %q: %w",
				plugin.Name(),
				err,
			)
		}

		// Iterate through the testers returned by the current plugin.
		for _, sw := range resp.GetTesters() {
			// Get the unique ID of the tester.
			id := sw.GetId()
			// If a tester ID is empty, return an error.
			if id == "" {
				return nil, fmt.Errorf(
					"received empty tester ID, plugin: %q",
					plugin.Name(),
				)
			}

			// Check if a tester with the same ID has already been encountered.
			if pOld, ok := testerMap[id]; ok {
				return nil, fmt.Errorf(
					"received duplicate tester ID: %q, plugin1 %q, plugin2 %q",
					id,
					pOld.Name(),
					plugin.Name(),
				)
			}

			// Add the current tester to the list and record its plugin in the map.
			testers = append(testers, sw)
			testerMap[id] = plugin
		}
	}

	// Log the number of testers found.
	slog.Info("Found testers", "testers", testers)
	// Update the server's internal map of tester IDs to plugins.
	s.testerMap = testerMap
	return testers, nil
}

// OpenVideoTester handles the OpenVideoTester gRPC request.
// It calls the OpenVideoTester method of the corresponding plugin.
func (s *videoTesterServiceServer) OpenVideoTester(
	ctx context.Context,
	req *passport.OpenVideoTesterRequest,
) (*passport.OpenVideoTesterResponse, error) {
	// Look up the plugin associated with the requested tester ID.
	tester := s.testerMap[req.Id]
	// If no plugin is found for the given ID, return a NotFound error.
	if tester == nil {
		return nil, status.Errorf(
			codes.NotFound,
			fmt.Sprintf("there is no tester with id: %s", req.Id),
		)
	}

	// Call the OpenVideoTester method of the found plugin.
	return tester.OpenVideoTester(ctx, req)
}

// CloseVideoTester handles the CloseVideoTester gRPC request.
// It calls the CloseVideoTester method of the corresponding plugin.
func (s *videoTesterServiceServer) CloseVideoTester(
	ctx context.Context,
	req *passport.CloseVideoTesterRequest,
) (*passport.CloseVideoTesterResponse, error) {
	// Look up the plugin associated with the requested tester ID.
	tester := s.testerMap[req.Id]
	// If no plugin is found for the given ID, return a NotFound error.
	if tester == nil {
		return nil, status.Errorf(
			codes.NotFound,
			fmt.Sprintf("there is no tester with id: %s", req.Id),
		)
	}

	// Call the CloseVideoTester method of the found plugin.
	return tester.CloseVideoTester(ctx, req)
}

// GetRolesVideoTester handles the GetRolesVideoTester gRPC request.
// It calls the GetRolesVideoTester method of the corresponding plugin.
func (s *videoTesterServiceServer) GetRolesVideoTester(
	ctx context.Context,
	req *passport.GetRolesRequest,
) (*passport.GetRolesResponse, error) {
	// Look up the plugin associated with the requested tester ID.
	tester := s.testerMap[req.Id]
	// If no plugin is found for the given ID, return a NotFound error.
	if tester == nil {
		return nil, status.Errorf(
			codes.NotFound,
			fmt.Sprintf("there is no tester with id: %s", req.Id),
		)
	}

	// Call the GetRolesVideoTester method of the found plugin.
	return tester.GetRolesVideoTester(ctx, req)
}

// SetRoleVideoTester handles the SetRoleVideoTester gRPC request.
// It calls the SetRoleVideoTester method of the corresponding plugin.
func (s *videoTesterServiceServer) SetRoleVideoTester(
	ctx context.Context,
	req *passport.SetRoleRequest,
) (*passport.SetRoleResponse, error) {
	// Look up the plugin associated with the requested tester ID.
	tester := s.testerMap[req.Id]
	// If no plugin is found for the given ID, return a NotFound error.
	if tester == nil {
		return nil, status.Errorf(
			codes.NotFound,
			fmt.Sprintf("there is tester with id: %s", req.Id),
		)
	}

	// Call the SetRoleVideoTester method of the found plugin.
	return tester.SetRoleVideoTester(ctx, req)
}

// LoadEdidVideoTester handles the LoadEdidVideoTester gRPC request.
// It calls the LoadEdidVideoTester method of the corresponding plugin.
func (s *videoTesterServiceServer) LoadEdidVideoTester(
	ctx context.Context,
	req *passport.LoadEdidVideoTesterRequest,
) (*passport.LoadEdidVideoTesterResponse, error) {
	// Look up the plugin associated with the requested tester ID.
	tester := s.testerMap[req.Id]
	// If no plugin is found for the given ID, return a NotFound error.
	if tester == nil {
		return nil, status.Errorf(
			codes.NotFound,
			fmt.Sprintf("there is no tester with id: %s", req.Id),
		)
	}

	// Call the LoadEdidVideoTester method of the found plugin.
	return tester.LoadEdidVideoTester(ctx, req)
}

// GetStreamInfoVideoTester handles the GetStreamInfoVideoTester gRPC request.
// It calls the GetStreamInfoVideoTester method of the corresponding plugin.
func (s *videoTesterServiceServer) GetStreamInfoVideoTester(
	ctx context.Context,
	req *passport.GetStreamInfoVideoTesterRequest,
) (*passport.GetStreamInfoVideoTesterResponse, error) {
	// Look up the plugin associated with the requested tester ID.
	tester := s.testerMap[req.Id]
	// If no plugin is found for the given ID, return a NotFound error.
	if tester == nil {
		return nil, status.Errorf(
			codes.NotFound,
			fmt.Sprintf("there is no tester with id: %s", req.Id),
		)
	}

	// Call the GetStreamInfoVideoTester method of the found plugin.
	return tester.GetStreamInfoVideoTester(ctx, req)
}

// ScreenshotVideoTester handles the ScreenshotVideoTester gRPC request.
// It calls the ScreenshotVideoTester method of the corresponding plugin.
func (s *videoTesterServiceServer) ScreenshotVideoTester(
	ctx context.Context,
	req *passport.ScreenshotVideoTesterRequest,
) (*passport.ScreenshotVideoTesterResponse, error) {
	// Look up the plugin associated with the requested tester ID.
	tester := s.testerMap[req.Id]
	// If no plugin is found for the given ID, return a NotFound error.
	if tester == nil {
		return nil, status.Errorf(
			codes.NotFound,
			fmt.Sprintf("there is no tester with id: %s", req.Id),
		)
	}

	// Call the ScreenshotVideoTester method of the found plugin.
	return tester.ScreenshotVideoTester(ctx, req)
}

// SetLinkVideoTester handles the SetLinkVideoTester gRPC request.
// It calls the SetLinkVideoTester method of the corresponding plugin.
func (s *videoTesterServiceServer) SetLinkVideoTester(
	ctx context.Context,
	req *passport.SetLinkVideoTesterRequest,
) (*passport.SetLinkVideoTesterResponse, error) {
	// Look up the plugin associated with the requested tester ID.
	tester := s.testerMap[req.Id]
	// If no plugin is found for the given ID, return a NotFound error.
	if tester == nil {
		return nil, status.Errorf(
			codes.NotFound,
			fmt.Sprintf("there is no tester with id: %s", req.Id),
		)
	}

	// Call the SetLinkVideoTester method of the found plugin.
	return tester.SetLinkVideoTester(ctx, req)
}

// GetLinkVideoTester handles the GetLinkVideoTester gRPC request.
// It calls the GetLinkVideoTester method of the corresponding plugin.
func (s *videoTesterServiceServer) GetLinkVideoTester(
	ctx context.Context,
	req *passport.GetLinkVideoTesterRequest,
) (*passport.GetLinkVideoTesterResponse, error) {
	// Look up the plugin associated with the requested tester ID.
	tester := s.testerMap[req.Id]
	// If no plugin is found for the given ID, return a NotFound error.
	if tester == nil {
		return nil, status.Errorf(
			codes.NotFound,
			fmt.Sprintf("there is no tester with id: %s", req.Id),
		)
	}

	// Call the GetLinkVideoTester method of the found plugin.
	return tester.GetLinkVideoTester(ctx, req)
}

// AttachVideoTester handles the AttachVideoTester gRPC request.
// It calls the AttachVideoTester method of the corresponding plugin.
func (s *videoTesterServiceServer) AttachVideoTester(
	ctx context.Context,
	req *passport.AttachVideoTesterRequest,
) (*passport.AttachVideoTesterResponse, error) {
	// Look up the plugin associated with the requested tester ID.
	tester := s.testerMap[req.Id]
	// If no plugin is found for the given ID, return a NotFound error.
	if tester == nil {
		return nil, status.Errorf(
			codes.NotFound,
			fmt.Sprintf("there is no tester with id: %s", req.Id),
		)
	}

	// Call the AttachVideoTester method of the found plugin.
	return tester.AttachVideoTester(ctx, req)
}

// Sends an HPD (Hot Plug Detect) pulse to a video tester.
// It calls the HpdPulseVideoTester method of the corresponding plugin.
func (s *videoTesterServiceServer) HpdPulseVideoTester(
	ctx context.Context,
	req *passport.HpdPulseVideoTesterRequest,
) (*passport.HpdPulseVideoTesterResponse, error) {
	// Look up the plugin associated with the requested tester ID.
	tester := s.testerMap[req.Id]
	// If no plugin is found for the given ID, return a NotFound error.
	if tester == nil {
		return nil, status.Errorf(
			codes.NotFound,
			fmt.Sprintf("there is no tester with id: %s", req.Id),
		)
	}

	// Call the AttachVideoTester method of the found plugin.
	return tester.HpdPulseVideoTester(ctx, req)
}

// Runs compliance test(s).
func (s *videoTesterServiceServer) RunComplianceTest(
	ctx context.Context,
	req *passport.RunComplianceTestRequest,
) (*passport.RunComplianceTestResponse, error) {
	// Look up the plugin associated with the requested tester ID.
	tester := s.testerMap[req.Id]
	// If no plugin is found for the given ID, return a NotFound error.
	if tester == nil {
		return nil, status.Errorf(
			codes.NotFound,
			fmt.Sprintf("there is no tester with id: %s", req.Id),
		)
	}

	// Call the AttachVideoTester method of the found plugin.
	return tester.RunComplianceTest(ctx, req)
}

// Runs StartEventCapture.
func (s *videoTesterServiceServer) StartEventCapture(
	ctx context.Context,
	req *passport.StartEventCaptureRequest,
) (*passport.StartEventCaptureResponse, error) {

	if tester, ok := s.testerMap[req.Id]; ok {
		// Call the StartEventCapture method of the found plugin.
		return tester.StartEventCapture(ctx, req)
	}

	// If no plugin is found for the given ID, return a NotFound error.
	return nil, status.Errorf(
		codes.NotFound,
		fmt.Sprintf("there is no tester with id: %s", req.Id),
	)
}

// Runs StopEventCapture.
func (s *videoTesterServiceServer) StopEventCapture(
	ctx context.Context,
	req *passport.StopEventCaptureRequest,
) (*passport.StopEventCaptureResponse, error) {

	if tester, ok := s.testerMap[req.Id]; ok {
		// Call the StartEventCapture method of the found plugin.
		return tester.StopEventCapture(ctx, req)
	}

	// If no plugin is found for the given ID, return a NotFound error.
	return nil, status.Errorf(
		codes.NotFound,
		fmt.Sprintf("there is no tester with id: %s", req.Id),
	)
}

// Runs PowerCycle.
func (s *videoTesterServiceServer) PowerCycle(
	ctx context.Context,
	req *passport.PowerCycleRequest,
) (*passport.PowerCycleResponse, error) {

	if tester, ok := s.testerMap[req.Id]; ok {
		// Call the PowerCycle method of the found plugin.
		return tester.PowerCycle(ctx, req)
	}

	// If no plugin is found for the given ID, return a NotFound error.
	return nil, status.Errorf(
		codes.NotFound,
		fmt.Sprintf("there is no tester with id: %s", req.Id),
	)
}
