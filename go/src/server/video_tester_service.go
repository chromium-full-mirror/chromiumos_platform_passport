// Copyright 2025 The ChromiumOS Authors
// Use of this source code is governed by a BSD-style license that can be
// found in the LICENSE file.

// Package server implements the gRPC server for the VideoTester service in Passport.
package server

import (
	"context"
	"errors"
	"fmt"
	"log/slog"
	"sync"

	"go.chromium.org/chromiumos/config/go/test/lab/api/passport"
	"google.golang.org/grpc/codes"
	"google.golang.org/grpc/status"
)

// videoTesterServiceServer implements the passport.VideoTesterServiceServer interface.
// It manages a collection of VideoTesterPlugin implementations.
type videoTesterServiceServer struct {
	mu sync.RWMutex
	// testerMap is a map of video tester IDs to their corresponding VideoTesterPlugin.
	testerMap map[string]VideoTesterPlugin
	// plugins is a slice of initialized VideoTesterPlugin implementations.
	plugins []VideoTesterPlugin
}

// newVideoTesterServiceServer creates a new instance of videoTesterServiceServer.
// It initializes the registered VideoTesterPlugins without mutating the package-global slice.
func newVideoTesterServiceServer(
	ctx context.Context,
) (passport.VideoTesterServiceServer, error) {
	plugins := make([]VideoTesterPlugin, 0, len(videoTesterPlugins))
	for _, elem := range videoTesterPlugins {
		if err := elem.Init(); err != nil {
			slog.Error("Failed to initialize tester", slog.Any("err", err))
			continue
		}
		plugins = append(plugins, elem)
	}

	s := &videoTesterServiceServer{
		testerMap: make(map[string]VideoTesterPlugin),
		plugins:   plugins,
	}

	return s, nil
}

// GetVideoTesters handles the GetVideoTesters gRPC request.
// It retrieves a list of available video testers from all registered plugins.
func (s *videoTesterServiceServer) GetVideoTesters(
	ctx context.Context,
	req *passport.GetVideoTestersRequest,
) (*passport.GetVideoTestersResponse, error) {
	slog.Info("Received passport.GetTestersRequest", "req", req)

	testers, err := s.refreshTesters(ctx, req)
	if err != nil {
		return nil, fmt.Errorf("failed to refresh testers: %w", err)
	}

	return &passport.GetVideoTestersResponse{
		Testers: testers,
	}, nil
}

// refreshTesters queries all registered VideoTesterPlugins for their available testers.
// It aggregates the results, checks for duplicate tester IDs, and merges discovered
// testers from all healthy plugins into s.testerMap even if another plugin fails.
func (s *videoTesterServiceServer) refreshTesters(
	ctx context.Context,
	req *passport.GetVideoTestersRequest,
) ([]*passport.VideoTester, error) {
	testerMap := make(map[string]VideoTesterPlugin)
	duplicateIDs := make(map[string]VideoTesterPlugin)
	var testers []*passport.VideoTester
	var errs []error

	for _, plugin := range s.plugins {
		resp, err := plugin.GetVideoTesters(ctx, req)
		if err != nil {
			slog.Error(
				"Failed to get testers for plugin",
				"plugin", plugin.Name(),
				slog.Any("err", err),
			)
			errs = append(
				errs,
				fmt.Errorf(
					"failed to get testers for plugin %q: %w",
					plugin.Name(),
					err,
				),
			)
			continue
		}

		for _, sw := range resp.GetTesters() {
			id := sw.GetId()
			if id == "" {
				errs = append(
					errs,
					fmt.Errorf(
						"received empty tester ID, plugin: %q",
						plugin.Name(),
					),
				)
				continue
			}

			if pFirst, dup := duplicateIDs[id]; dup {
				errs = append(
					errs,
					fmt.Errorf(
						"received duplicate tester ID: %q, plugin1 %q, plugin2 %q",
						id,
						pFirst.Name(),
						plugin.Name(),
					),
				)
				continue
			}

			if pOld, ok := testerMap[id]; ok {
				duplicateIDs[id] = pOld
				delete(testerMap, id)
				errs = append(
					errs,
					fmt.Errorf(
						"received duplicate tester ID: %q, plugin1 %q, plugin2 %q",
						id,
						pOld.Name(),
						plugin.Name(),
					),
				)
				continue
			}

			testers = append(testers, sw)
			testerMap[id] = plugin
		}
	}

	slog.Info("Found testers", "testers", testers)
	// Merge discovered tester IDs into the server's internal map under write lock
	// so concurrent RPCs, partial plugin failures, and temporary USB
	// re-enumerations do not lose mappings from healthy plugins.
	s.mu.Lock()
	if s.testerMap == nil {
		s.testerMap = make(map[string]VideoTesterPlugin, len(testerMap))
	}
	for id := range duplicateIDs {
		delete(s.testerMap, id)
	}
	for id, plugin := range testerMap {
		s.testerMap[id] = plugin
	}
	s.mu.Unlock()
	if len(errs) > 0 {
		return testers, errors.Join(errs...)
	}
	return testers, nil
}

// getTester looks up the VideoTesterPlugin for a given tester ID, performing
// a lazy refreshTesters pass on cache miss before returning NotFound or
// Unavailable if a plugin refresh failed.
func (s *videoTesterServiceServer) getTester(
	ctx context.Context,
	id string,
) (VideoTesterPlugin, error) {
	s.mu.RLock()
	tester := s.testerMap[id]
	s.mu.RUnlock()
	if tester != nil {
		return tester, nil
	}

	_, refreshErr := s.refreshTesters(ctx, &passport.GetVideoTestersRequest{})

	s.mu.RLock()
	tester = s.testerMap[id]
	s.mu.RUnlock()
	if tester != nil {
		return tester, nil
	}
	if refreshErr != nil {
		return nil, status.Errorf(
			codes.Unavailable,
			"failed to refresh testers while looking up id %s: %v",
			id,
			refreshErr,
		)
	}
	return nil, status.Errorf(
		codes.NotFound,
		"there is no tester with id: %s",
		id,
	)
}

// OpenVideoTester handles the OpenVideoTester gRPC request.
func (s *videoTesterServiceServer) OpenVideoTester(
	ctx context.Context,
	req *passport.OpenVideoTesterRequest,
) (*passport.OpenVideoTesterResponse, error) {
	tester, err := s.getTester(ctx, req.Id)
	if err != nil {
		return nil, err
	}
	return tester.OpenVideoTester(ctx, req)
}

// CloseVideoTester handles the CloseVideoTester gRPC request.
func (s *videoTesterServiceServer) CloseVideoTester(
	ctx context.Context,
	req *passport.CloseVideoTesterRequest,
) (*passport.CloseVideoTesterResponse, error) {
	tester, err := s.getTester(ctx, req.Id)
	if err != nil {
		return nil, err
	}
	return tester.CloseVideoTester(ctx, req)
}

// GetRolesVideoTester handles the GetRolesVideoTester gRPC request.
func (s *videoTesterServiceServer) GetRolesVideoTester(
	ctx context.Context,
	req *passport.GetRolesRequest,
) (*passport.GetRolesResponse, error) {
	tester, err := s.getTester(ctx, req.Id)
	if err != nil {
		return nil, err
	}
	return tester.GetRolesVideoTester(ctx, req)
}

// SetRoleVideoTester handles the SetRoleVideoTester gRPC request.
func (s *videoTesterServiceServer) SetRoleVideoTester(
	ctx context.Context,
	req *passport.SetRoleRequest,
) (*passport.SetRoleResponse, error) {
	tester, err := s.getTester(ctx, req.Id)
	if err != nil {
		return nil, err
	}
	return tester.SetRoleVideoTester(ctx, req)
}

// LoadEdidVideoTester handles the LoadEdidVideoTester gRPC request.
func (s *videoTesterServiceServer) LoadEdidVideoTester(
	ctx context.Context,
	req *passport.LoadEdidVideoTesterRequest,
) (*passport.LoadEdidVideoTesterResponse, error) {
	tester, err := s.getTester(ctx, req.Id)
	if err != nil {
		return nil, err
	}
	return tester.LoadEdidVideoTester(ctx, req)
}

// GetStreamInfoVideoTester handles the GetStreamInfoVideoTester gRPC request.
func (s *videoTesterServiceServer) GetStreamInfoVideoTester(
	ctx context.Context,
	req *passport.GetStreamInfoVideoTesterRequest,
) (*passport.GetStreamInfoVideoTesterResponse, error) {
	tester, err := s.getTester(ctx, req.Id)
	if err != nil {
		return nil, err
	}
	return tester.GetStreamInfoVideoTester(ctx, req)
}

// ScreenshotVideoTester handles the ScreenshotVideoTester gRPC request.
func (s *videoTesterServiceServer) ScreenshotVideoTester(
	ctx context.Context,
	req *passport.ScreenshotVideoTesterRequest,
) (*passport.ScreenshotVideoTesterResponse, error) {
	tester, err := s.getTester(ctx, req.Id)
	if err != nil {
		return nil, err
	}
	return tester.ScreenshotVideoTester(ctx, req)
}

// SetLinkVideoTester handles the SetLinkVideoTester gRPC request.
func (s *videoTesterServiceServer) SetLinkVideoTester(
	ctx context.Context,
	req *passport.SetLinkVideoTesterRequest,
) (*passport.SetLinkVideoTesterResponse, error) {
	tester, err := s.getTester(ctx, req.Id)
	if err != nil {
		return nil, err
	}
	return tester.SetLinkVideoTester(ctx, req)
}

// GetLinkVideoTester handles the GetLinkVideoTester gRPC request.
func (s *videoTesterServiceServer) GetLinkVideoTester(
	ctx context.Context,
	req *passport.GetLinkVideoTesterRequest,
) (*passport.GetLinkVideoTesterResponse, error) {
	tester, err := s.getTester(ctx, req.Id)
	if err != nil {
		return nil, err
	}
	return tester.GetLinkVideoTester(ctx, req)
}

// AttachVideoTester handles the AttachVideoTester gRPC request.
func (s *videoTesterServiceServer) AttachVideoTester(
	ctx context.Context,
	req *passport.AttachVideoTesterRequest,
) (*passport.AttachVideoTesterResponse, error) {
	tester, err := s.getTester(ctx, req.Id)
	if err != nil {
		return nil, err
	}
	return tester.AttachVideoTester(ctx, req)
}

// HpdPulseVideoTester sends an HPD (Hot Plug Detect) pulse to a video tester.
func (s *videoTesterServiceServer) HpdPulseVideoTester(
	ctx context.Context,
	req *passport.HpdPulseVideoTesterRequest,
) (*passport.HpdPulseVideoTesterResponse, error) {
	tester, err := s.getTester(ctx, req.Id)
	if err != nil {
		return nil, err
	}
	return tester.HpdPulseVideoTester(ctx, req)
}

// RunComplianceTest runs compliance test(s) on the requested video tester.
func (s *videoTesterServiceServer) RunComplianceTest(
	ctx context.Context,
	req *passport.RunComplianceTestRequest,
) (*passport.RunComplianceTestResponse, error) {
	tester, err := s.getTester(ctx, req.Id)
	if err != nil {
		return nil, err
	}
	return tester.RunComplianceTest(ctx, req)
}

// StartEventCapture starts event capture on the requested video tester.
func (s *videoTesterServiceServer) StartEventCapture(
	ctx context.Context,
	req *passport.StartEventCaptureRequest,
) (*passport.StartEventCaptureResponse, error) {
	tester, err := s.getTester(ctx, req.Id)
	if err != nil {
		return nil, err
	}
	return tester.StartEventCapture(ctx, req)
}

// StopEventCapture stops event capture on the requested video tester.
func (s *videoTesterServiceServer) StopEventCapture(
	ctx context.Context,
	req *passport.StopEventCaptureRequest,
) (*passport.StopEventCaptureResponse, error) {
	tester, err := s.getTester(ctx, req.Id)
	if err != nil {
		return nil, err
	}
	return tester.StopEventCapture(ctx, req)
}

// PowerCycle power cycles the requested video tester.
func (s *videoTesterServiceServer) PowerCycle(
	ctx context.Context,
	req *passport.PowerCycleRequest,
) (*passport.PowerCycleResponse, error) {
	tester, err := s.getTester(ctx, req.Id)
	if err != nil {
		return nil, err
	}
	return tester.PowerCycle(ctx, req)
}
