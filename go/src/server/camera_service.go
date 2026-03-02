// Copyright 2024 The ChromiumOS Authors
// Use of this source code is governed by a BSD-style license that can be
// found in the LICENSE file.

package server

import (
	"context"
	"fmt"
	"log/slog"

	"go.chromium.org/chromiumos/config/go/test/lab/api/passport"
)

// cameraServiceServer implements api/passport.CameraServiceServer and wraps individual
// camera plugins.
type cameraServiceServer struct {
	// Maps individual cameras to their controlling cameraMap.
	cameraMap map[string]CameraPlugin
	// All registered plugins.
	plugins []CameraPlugin
}

func newCameraServiceServer(ctx context.Context) (passport.CameraServiceServer, error) {
	s := &cameraServiceServer{
		cameraMap: make(map[string]CameraPlugin),
		plugins:   cameraPlugins,
	}
	return s, nil
}

// GetCameras probes all cameras connected to the host device.
func (s *cameraServiceServer) GetCameras(ctx context.Context, req *passport.GetCamerasRequest) (*passport.GetCamerasResponse, error) {
	slog.Info("Received passport.GetCamerasRequest", "req", req)

	cameras, err := s.refreshCameras(ctx, req)
	if err != nil {
		return nil, fmt.Errorf("failed to refresh switches: %w", err)
	}

	return &passport.GetCamerasResponse{
		Cameras: cameras,
	}, nil
}

// GetAveragePixel gets the average pixel color detected by the specified camera.
func (s *cameraServiceServer) GetAveragePixel(ctx context.Context, req *passport.GetAveragePixelRequest) (*passport.GetAveragePixelResponse, error) {
	slog.Info("Received passport.GetAveragePixelRequest", "req", req)
	c, err := s.pluginForCamera(ctx, req.GetDeviceId())
	if err != nil {
		return nil, fmt.Errorf("failed to fetch plugin for camera: %w", err)
	}

	resp, err := c.GetAveragePixel(ctx, req)
	if err != nil {
		return nil, fmt.Errorf("failed to get average pixel color for camera: %q: %w", req.GetDeviceId(), err)
	}
	return resp, nil
}

func (s *cameraServiceServer) AnalyzeImageHSV(ctx context.Context, req *passport.AnalyzeHSVRequest) (*passport.AnalyzeHSVResponse, error) {
	slog.Info("Received passport.AnalyzeHSVRequest", "req", req)
	c, err := s.pluginForCamera(ctx, req.GetDeviceId())
	if err != nil {
		return nil, fmt.Errorf("failed to fetch plugin for camera: %w", err)
	}

	resp, err := c.AnalyzeImageHSV(ctx, req)
	if err != nil {
		return nil, fmt.Errorf("failed to analyze image HSV for camera: %q: %w", req.GetDeviceId(), err)
	}
	return resp, nil
}

func (s *cameraServiceServer) CaptureVideo(req *passport.CaptureVideoRequest, stream passport.CameraService_CaptureVideoServer) error {
	slog.Info("Received passport.CaptureVideoRequest", "req", req)
	if len(req.GetDeviceIds()) == 0 {
		return fmt.Errorf("no device_ids provided")
	}
	if len(req.GetDeviceIds()) > 4 {
		return fmt.Errorf("tiling is supported for a maximum of 4 cameras, %d requested", len(req.GetDeviceIds()))
	}

	var p CameraPlugin
	for _, id := range req.GetDeviceIds() {
		c, err := s.pluginForCamera(stream.Context(), id)
		if err != nil {
			return fmt.Errorf("failed to fetch plugin for camera %q: %w", id, err)
		}
		if p == nil {
			p = c
		} else if p != c {
			return fmt.Errorf("cameras %v belong to different plugins, tiling is not supported across plugins", req.GetDeviceIds())
		}
	}

	return p.CaptureVideo(req, stream)
}

// pluginForCamera gets the plugin that controls a specific camera.
func (s *cameraServiceServer) pluginForCamera(ctx context.Context, id string) (CameraPlugin, error) {
	if c, ok := s.cameraMap[id]; ok {
		return c, nil
	}

	if _, err := s.refreshCameras(ctx, &passport.GetCamerasRequest{}); err != nil {
		return nil, fmt.Errorf("failed to refresh switches: %w", err)
	}

	if c, ok := s.cameraMap[id]; ok {
		return c, nil
	}

	return nil, fmt.Errorf("unknown camera with ID: %q", id)
}

// refreshSwitches refreshes the cached switches by probing the plugins.
func (s *cameraServiceServer) refreshCameras(ctx context.Context, req *passport.GetCamerasRequest) ([]*passport.Camera, error) {
	var cameras []*passport.Camera
	cameraMap := make(map[string]CameraPlugin)
	for _, plugin := range s.plugins {
		resp, err := plugin.GetCameras(ctx, req)
		if err != nil {
			return nil, fmt.Errorf("failed to get devices: %w", err)
		}

		for _, camera := range resp.GetCameras() {
			id := camera.GetId()
			if id == "" {
				return nil, fmt.Errorf("received empty camera ID, plugin: %q", plugin.Name())
			}
			if pOld, ok := cameraMap[id]; ok {
				return nil, fmt.Errorf("received duplicate camera ID: %q, plugin1 %q, plugin2 %q", id, pOld.Name(), plugin.Name())
			}
			cameras = append(cameras, camera)
			cameraMap[id] = plugin
		}
	}

	slog.Info("Found cameras", "count", len(cameras), "cameras", cameras)
	s.cameraMap = cameraMap
	return cameras, nil
}
