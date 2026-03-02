// Copyright 2024 The ChromiumOS Authors
// Use of this source code is governed by a BSD-style license that can be
// found in the LICENSE file.

package server

import (
	"context"
	"fmt"
	"testing"

	"go.chromium.org/chromiumos/config/go/test/lab/api/passport"
	"google.golang.org/grpc"
	"google.golang.org/grpc/metadata"
)

type mockCaptureVideoServer struct {
	grpc.ServerStream
	ctx context.Context
}

func (m *mockCaptureVideoServer) Send(*passport.CaptureVideoResponse) error {
	return nil
}

func (m *mockCaptureVideoServer) Context() context.Context {
	if m.ctx != nil {
		return m.ctx
	}
	return context.Background()
}

func (m *mockCaptureVideoServer) SetHeader(metadata.MD) error {
	return nil
}

func (m *mockCaptureVideoServer) SendHeader(metadata.MD) error {
	return nil
}

func (m *mockCaptureVideoServer) SetTrailer(metadata.MD) {
}

func (m *mockCaptureVideoServer) SendMsg(interface{}) error {
	return nil
}

func (m *mockCaptureVideoServer) RecvMsg(interface{}) error {
	return nil
}

type getCamerasFunc func(ctx context.Context, req *passport.GetCamerasRequest) (*passport.GetCamerasResponse, error)
type getAvgPixelFunc func(ctx context.Context, req *passport.GetAveragePixelRequest) (*passport.GetAveragePixelResponse, error)
type analyzeImageHSVFunc func(ctx context.Context, req *passport.AnalyzeHSVRequest) (*passport.AnalyzeHSVResponse, error)
type captureVideoFunc func(req *passport.CaptureVideoRequest, stream passport.CameraService_CaptureVideoServer) error

// mockCameraPlugin is mock camera plugin.
type mockCameraPlugin struct {
	getCameras      getCamerasFunc
	getAvgPixel     getAvgPixelFunc
	analyzeImageHSV analyzeImageHSVFunc
	captureVideo    captureVideoFunc
}

func (m *mockCameraPlugin) GetCameras(ctx context.Context, req *passport.GetCamerasRequest) (*passport.GetCamerasResponse, error) {
	if m.getCameras != nil {
		return m.getCameras(ctx, req)
	}
	return &passport.GetCamerasResponse{}, nil
}

func (m *mockCameraPlugin) GetAveragePixel(ctx context.Context, req *passport.GetAveragePixelRequest) (*passport.GetAveragePixelResponse, error) {
	if m.getAvgPixel != nil {
		return m.getAvgPixel(ctx, req)
	}
	return &passport.GetAveragePixelResponse{}, nil
}

func (m *mockCameraPlugin) AnalyzeImageHSV(ctx context.Context, req *passport.AnalyzeHSVRequest) (*passport.AnalyzeHSVResponse, error) {
	if m.analyzeImageHSV != nil {
		return m.analyzeImageHSV(ctx, req)
	}
	return &passport.AnalyzeHSVResponse{}, nil
}

func (m *mockCameraPlugin) CaptureVideo(req *passport.CaptureVideoRequest, stream passport.CameraService_CaptureVideoServer) error {
	if m.captureVideo != nil {
		return m.captureVideo(req, stream)
	}
	return nil
}

func (m *mockCameraPlugin) Name() string {
	return "mock_camera_plugin"
}

func replyWithCameras(cameras ...string) getCamerasFunc {
	resp := &passport.GetCamerasResponse{}
	for _, c := range cameras {
		resp.Cameras = append(resp.Cameras, &passport.Camera{Id: c})
	}

	return func(context.Context, *passport.GetCamerasRequest) (*passport.GetCamerasResponse, error) {
		return resp, nil
	}
}

// TestGetCameras tests GetCameras API on cameraServiceServicer.
func TestGetCamera(t *testing.T) {
	tests := []struct {
		name     string
		plugins  []CameraPlugin
		expected []string
		wantErr  bool
	}{
		{
			name: "Empty",
		},
		{
			name: "HappyPath",
			plugins: []CameraPlugin{
				&mockCameraPlugin{
					getCameras: replyWithCameras("camera1", "camera2", "camera3"),
				},
				&mockCameraPlugin{
					getCameras: replyWithCameras("camera4"),
				},
				&mockCameraPlugin{
					getCameras: replyWithCameras("camera5"),
				},
				&mockCameraPlugin{},
			},
			expected: []string{"camera1", "camera2", "camera3", "camera4", "camera5"},
		},
		{
			name: "NoCameras",
			plugins: []CameraPlugin{
				&mockCameraPlugin{},
				&mockCameraPlugin{},
			},
			expected: nil,
		},
		{
			name: "DuplicateName",
			plugins: []CameraPlugin{
				&mockCameraPlugin{
					getCameras: replyWithCameras("camera1"),
				},
				&mockCameraPlugin{
					getCameras: replyWithCameras("camera1"),
				},
			},
			wantErr: true,
		},
		{
			name: "EmptyName",
			plugins: []CameraPlugin{
				&mockCameraPlugin{
					getCameras: replyWithCameras("camera1", ""),
				},
			},
			wantErr: true,
		},
		{
			name: "PluginError",
			plugins: []CameraPlugin{
				&mockCameraPlugin{
					getCameras: replyWithCameras("camera1"),
				},
				&mockCameraPlugin{
					getCameras: func(context.Context, *passport.GetCamerasRequest) (*passport.GetCamerasResponse, error) {
						return nil, fmt.Errorf("Test Error")
					},
				},
			},
			wantErr: true,
		},
	}

	for _, test := range tests {
		t.Run(test.name, func(t *testing.T) {
			expectedCameras := make(map[string]bool)
			service := &cameraServiceServer{
				cameraMap: make(map[string]CameraPlugin),
				plugins:   test.plugins,
			}
			for _, c := range test.expected {
				expectedCameras[c] = true
			}

			resp, err := service.GetCameras(context.Background(), &passport.GetCamerasRequest{})
			for _, c := range resp.GetCameras() {
				if !expectedCameras[c.GetId()] {
					t.Errorf("unexpected camera: %q, want %v, got %v", c.GetId(), test.expected, resp.GetCameras())
				}
				delete(expectedCameras, c.GetId())
			}
			if (err != nil) != test.wantErr {
				t.Errorf("error = %v, wantErr %v", err, test.wantErr)
			}
		})
	}
}

// TestGetAveragePixel tests GetAveragePixel API on cameraServiceServicer.
func TestGetAveragePixel(t *testing.T) {
	tests := []struct {
		name    string
		plugins []CameraPlugin
		request *passport.GetAveragePixelRequest
		wantErr bool
	}{
		{
			name: "Empty",
			request: &passport.GetAveragePixelRequest{
				DeviceId: "camera4",
			},
			wantErr: true,
		},
		{
			name: "HappyPath",
			plugins: []CameraPlugin{
				&mockCameraPlugin{
					getCameras: replyWithCameras("camera1", "camera2", "camera3"),
				},
				&mockCameraPlugin{
					getCameras: replyWithCameras("camera4"),
				},
				&mockCameraPlugin{
					getCameras: replyWithCameras("camera5"),
				},
				&mockCameraPlugin{},
			},
			request: &passport.GetAveragePixelRequest{
				DeviceId: "camera4",
			},
		},
		{
			name: "UnknownCamera",
			plugins: []CameraPlugin{
				&mockCameraPlugin{
					getCameras: replyWithCameras("camera1", "camera2", "camera3"),
				},
			},
			request: &passport.GetAveragePixelRequest{
				DeviceId: "camera4",
			},
			wantErr: true,
		},
		{
			name: "PluginError",
			plugins: []CameraPlugin{
				&mockCameraPlugin{
					getCameras: replyWithCameras("camera1"),
				},
				&mockCameraPlugin{
					getAvgPixel: func(context.Context, *passport.GetAveragePixelRequest) (*passport.GetAveragePixelResponse, error) {
						return nil, fmt.Errorf("Test Error")
					},
				},
			},
			wantErr: true,
		},
	}
	for _, test := range tests {
		t.Run(test.name, func(t *testing.T) {
			service := &cameraServiceServer{
				cameraMap: make(map[string]CameraPlugin),
				plugins:   test.plugins,
			}
			_, err := service.GetAveragePixel(context.Background(), test.request)
			if (err != nil) != test.wantErr {
				t.Errorf("error = %v, wantErr %v", err, test.wantErr)
			}
		})
	}
}

func TestAnalyzeImageHSV(t *testing.T) {
	tests := []struct {
		name    string
		plugins []CameraPlugin
		request *passport.AnalyzeHSVRequest
		wantErr bool
	}{
		{
			name: "Empty",
			request: &passport.AnalyzeHSVRequest{
				DeviceId: "camera4",
			},
			wantErr: true,
		},
		{
			name: "HappyPath",
			plugins: []CameraPlugin{
				&mockCameraPlugin{
					getCameras: replyWithCameras("camera1", "camera2", "camera3"),
				},
				&mockCameraPlugin{
					getCameras: replyWithCameras("camera4"),
				},
				&mockCameraPlugin{
					getCameras: replyWithCameras("camera5"),
				},
				&mockCameraPlugin{},
			},
			request: &passport.AnalyzeHSVRequest{
				DeviceId: "camera4",
			},
		},
		{
			name: "UnknownCamera",
			plugins: []CameraPlugin{
				&mockCameraPlugin{
					getCameras: replyWithCameras("camera1", "camera2", "camera3"),
				},
			},
			request: &passport.AnalyzeHSVRequest{
				DeviceId: "camera4",
			},
			wantErr: true,
		},
		{
			name: "PluginError",
			plugins: []CameraPlugin{
				&mockCameraPlugin{
					getCameras: replyWithCameras("camera1"),
				},
				&mockCameraPlugin{
					analyzeImageHSV: func(context.Context, *passport.AnalyzeHSVRequest) (*passport.AnalyzeHSVResponse, error) {
						return nil, fmt.Errorf("Test Error")
					},
				},
			},
			wantErr: true,
		},
	}
	for _, test := range tests {
		t.Run(test.name, func(t *testing.T) {
			service := &cameraServiceServer{
				cameraMap: make(map[string]CameraPlugin),
				plugins:   test.plugins,
			}
			_, err := service.AnalyzeImageHSV(context.Background(), test.request)
			if (err != nil) != test.wantErr {
				t.Errorf("error = %v, wantErr %v", err, test.wantErr)
			}
		})
	}
}

func TestCaptureVideo(t *testing.T) {
	tests := []struct {
		name    string
		plugins []CameraPlugin
		request *passport.CaptureVideoRequest
		wantErr bool
	}{
		{
			name: "NoDeviceIds",
			request: &passport.CaptureVideoRequest{
				DeviceIds: []string{},
			},
			wantErr: true,
		},
		{
			name: "Empty",
			request: &passport.CaptureVideoRequest{
				DeviceIds: []string{"camera4"},
			},
			wantErr: true,
		},
		{
			name: "HappyPath",
			plugins: []CameraPlugin{
				&mockCameraPlugin{
					getCameras: replyWithCameras("camera1", "camera2", "camera3"),
				},
				&mockCameraPlugin{
					getCameras: replyWithCameras("camera4"),
				},
			},
			request: &passport.CaptureVideoRequest{
				DeviceIds:       []string{"camera4"},
				DurationSeconds: 2,
			},
		},
		{
			name: "UnknownCamera",
			plugins: []CameraPlugin{
				&mockCameraPlugin{
					getCameras: replyWithCameras("camera1"),
				},
			},
			request: &passport.CaptureVideoRequest{
				DeviceIds: []string{"camera4"},
			},
			wantErr: true,
		},
		{
			name: "PluginError",
			plugins: []CameraPlugin{
				&mockCameraPlugin{
					getCameras: replyWithCameras("camera1"),
					captureVideo: func(req *passport.CaptureVideoRequest, stream passport.CameraService_CaptureVideoServer) error {
						return fmt.Errorf("Test Error")
					},
				},
			},
			request: &passport.CaptureVideoRequest{
				DeviceIds: []string{"camera1"},
			},
			wantErr: true,
		},
		{
			name: "MismatchedPlugins",
			plugins: []CameraPlugin{
				&mockCameraPlugin{
					getCameras: replyWithCameras("camera1"),
				},
				&mockCameraPlugin{
					getCameras: replyWithCameras("camera2"),
				},
			},
			request: &passport.CaptureVideoRequest{
				DeviceIds: []string{"camera1", "camera2"},
			},
			wantErr: true,
		},
		{
			name: "TooManyCameras",
			plugins: []CameraPlugin{
				&mockCameraPlugin{
					getCameras: replyWithCameras("c1", "c2", "c3", "c4", "c5"),
				},
			},
			request: &passport.CaptureVideoRequest{
				DeviceIds: []string{"c1", "c2", "c3", "c4", "c5"},
			},
			wantErr: true,
		},
	}
	for _, test := range tests {
		t.Run(test.name, func(t *testing.T) {
			service := &cameraServiceServer{
				cameraMap: make(map[string]CameraPlugin),
				plugins:   test.plugins,
			}
			err := service.CaptureVideo(test.request, &mockCaptureVideoServer{})
			if (err != nil) != test.wantErr {
				t.Errorf("error = %v, wantErr %v", err, test.wantErr)
			}
		})
	}
}
