// Copyright 2024 The ChromiumOS Authors
// Use of this source code is governed by a BSD-style license that can be
// found in the LICENSE file.

package server

import (
	"context"
	"fmt"

	"go.chromium.org/chromiumos/config/go/test/lab/api/passport"
)

// cameraServiceServer implements api/passport.CameraServiceServer and wraps individual
// camera plugins.
type cameraServiceServer struct {
}

func newCameraServiceServer(ctx context.Context) (passport.CameraServiceServer, error) {
	return &cameraServiceServer{}, nil
}

// GetCameras probes all cameras connected to the host device.
func (s *cameraServiceServer) GetCameras(ctx context.Context, req *passport.GetCamerasRequest) (*passport.GetCamerasResponse, error) {
	return nil, fmt.Errorf("not implemented")
}

// GetAveragePixel gets the average pixel color detected by the specified camera.
func (s *cameraServiceServer) GetAveragePixel(ctx context.Context, req *passport.GetAveragePixelRequest) (*passport.GetAveragePixelResponse, error) {
	return nil, fmt.Errorf("not implemented")
}
