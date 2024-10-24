// Copyright 2024 The ChromiumOS Authors
// Use of this source code is governed by a BSD-style license that can be
// found in the LICENSE file.

// Package generic provides plugins for controlling generic devices (not vendor specific).
package generic

import (
	"bytes"
	"context"
	"fmt"
	"image"
	"image/color"
	"image/jpeg"
	"log/slog"
	"path/filepath"

	"github.com/blackjack/webcam"

	"go.chromium.org/chromiumos/config/go/test/lab/api/passport"
	"go.chromiumos.org/chromiumos/platform/passport/server"
)

const jpegFormat = "Motion-JPEG"

var (
	// Compression table information that needs to be added to the raw frame to make it usable as a .jpeg file.
	dhtMarker = []byte{255, 196}
	dht       = []byte{1, 162, 0, 0, 1, 5, 1, 1, 1, 1, 1, 1, 0, 0, 0, 0, 0, 0, 0, 0, 1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 11,
		1, 0, 3, 1, 1, 1, 1, 1, 1, 1, 1, 1, 0, 0, 0, 0, 0, 0, 1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 11, 16, 0, 2, 1, 3, 3, 2,
		4, 3, 5, 5, 4, 4, 0, 0, 1, 125, 1, 2, 3, 0, 4, 17, 5, 18, 33, 49, 65, 6, 19, 81, 97, 7, 34, 113, 20, 50, 129,
		145, 161, 8, 35, 66, 177, 193, 21, 82, 209, 240, 36, 51, 98, 114, 130, 9, 10, 22, 23, 24, 25, 26, 37, 38, 39,
		40, 41, 42, 52, 53, 54, 55, 56, 57, 58, 67, 68, 69, 70, 71, 72, 73, 74, 83, 84, 85, 86, 87, 88, 89, 90, 99,
		100, 101, 102, 103, 104, 105, 106, 115, 116, 117, 118, 119, 120, 121, 122, 131, 132, 133, 134, 135, 136,
		137, 138, 146, 147, 148, 149, 150, 151, 152, 153, 154, 162, 163, 164, 165, 166, 167, 168, 169, 170, 178,
		179, 180, 181, 182, 183, 184, 185, 186, 194, 195, 196, 197, 198, 199, 200, 201, 202, 210, 211, 212, 213,
		214, 215, 216, 217, 218, 225, 226, 227, 228, 229, 230, 231, 232, 233, 234, 241, 242, 243, 244, 245, 246,
		247, 248, 249, 250, 17, 0, 2, 1, 2, 4, 4, 3, 4, 7, 5, 4, 4, 0, 1, 2, 119, 0, 1, 2, 3, 17, 4, 5, 33, 49,
		6, 18, 65, 81, 7, 97, 113, 19, 34, 50, 129, 8, 20, 66, 145, 161, 177, 193, 9, 35, 51, 82, 240, 21, 98,
		114, 209, 10, 22, 36, 52, 225, 37, 241, 23, 24, 25, 26, 38, 39, 40, 41, 42, 53, 54, 55, 56, 57, 58, 67,
		68, 69, 70, 71, 72, 73, 74, 83, 84, 85, 86, 87, 88, 89, 90, 99, 100, 101, 102, 103, 104, 105, 106, 115,
		116, 117, 118, 119, 120, 121, 122, 130, 131, 132, 133, 134, 135, 136, 137, 138, 146, 147, 148, 149, 150,
		151, 152, 153, 154, 162, 163, 164, 165, 166, 167, 168, 169, 170, 178, 179, 180, 181, 182, 183, 184, 185,
		186, 194, 195, 196, 197, 198, 199, 200, 201, 202, 210, 211, 212, 213, 214, 215, 216, 217, 218, 226, 227,
		228, 229, 230, 231, 232, 233, 234, 242, 243, 244, 245, 246, 247, 248, 249, 250}
	sosMarker = []byte{255, 218}
)

func init() {
	server.RegisterCameraPlugin(&cameraPlugin{})
}

// cameraPlugin implements a generic camera controller.
type cameraPlugin struct{}

// GetCameras probes all cameras connected to the host device.
func (s *cameraPlugin) GetCameras(ctx context.Context, req *passport.GetCamerasRequest) (*passport.GetCamerasResponse, error) {
	slog.Info("Probing cameras")
	ports, err := filepath.Glob("/dev/video*")
	if err != nil {
		return nil, fmt.Errorf("failed to probe for video devices: %w", err)
	}

	var cameras []*passport.Camera
	for _, port := range ports {
		cam, err := webcam.Open(port)
		if err != nil {
			slog.Warn("Failed to open port on device", "port", port)
			continue
		}
		defer cam.Close()

		err = cam.StartStreaming()
		if err != nil {
			slog.Warn("Failed to start streaming on camera", "port", port, "error", err)
			continue
		}

		if !supportsJpeg(cam) {
			slog.Warn("Skipping camera, Motion-JPEG format not supported", "port", port)
			continue
		}

		// Camera name is optional.
		name, err := cam.GetName()
		if err != nil {
			name = err.Error()
		}

		// Cameras use their /dev/video* device path as ID, getting the device
		// serial is more involved for little benefit.
		slog.Info("Found valid camera", "port", port, "name", name)
		cameras = append(cameras,
			&passport.Camera{
				Id:   port,
				Name: name,
			})
	}

	slog.Info("Detected cameras", "count", len(cameras))
	return &passport.GetCamerasResponse{
		Cameras: cameras,
	}, nil
}

// GetAveragePixel gets the average pixel color detected by the specified camera.
func (s *cameraPlugin) GetAveragePixel(ctx context.Context, req *passport.GetAveragePixelRequest) (*passport.GetAveragePixelResponse, error) {
	const settlingTime = 10

	devPort := req.GetDeviceId()
	slog.Info("Getting average pixel", "port", devPort)

	cam, err := webcam.Open(devPort)
	if err != nil {
		return nil, fmt.Errorf("failed to connect to camera %q: %w", devPort, err)
	}
	defer cam.Close()
	slog.Info("Opened camera", "port", devPort)

	if err := configureImageSize(ctx, cam); err != nil {
		return nil, fmt.Errorf("failed to configure image format for %q: %w", devPort, err)
	}

	err = cam.StartStreaming()
	if err != nil {
		return nil, fmt.Errorf("failed to start camera streaming")
	}

	frameCount := 0
	for ctx.Err() == nil {
		err = cam.WaitForFrame(uint32(5) /*timeout*/)
		switch err.(type) {
		case nil:
		case *webcam.Timeout:
			slog.Error("webcam timeout", "error", err)
			continue
		default:
			return nil, fmt.Errorf("failed to wait for webcam frame: %w", err)
		}

		frame, err := cam.ReadFrame()
		if err != nil {
			return nil, fmt.Errorf("failed to get frame from camera: %w", err)
		}

		frameCount++
		// Discard the first 10 frames to give the camera a chance to "warm up".
		if (frameCount < settlingTime) || len(frame) == 0 {
			continue
		}

		frame, err = addMotionDht(frame)
		if err != nil {
			return nil, fmt.Errorf("failed to add DHT to the frame %w", err)
		}
		p, err := getAvgPixelColor(frame)
		if err != nil {
			return nil, fmt.Errorf("failed to get pixel from webcam: %q: %w", devPort, err)
		}

		return &passport.GetAveragePixelResponse{
			Pixel: p,
			Frame: frame,
		}, nil
	}
	return nil, fmt.Errorf("failed to capture a frame before context expired")
}

// Name returns the plugin's name.
func (s *cameraPlugin) Name() string {
	return "generic-camera-plugin"
}

// Checks if the camera supports jpeg.
func supportsJpeg(cam *webcam.Webcam) bool {
	for _, format := range cam.GetSupportedFormats() {
		if format == jpegFormat {
			return true
		}
	}
	return false
}

// Configures the requested image size when taking jpeg images.
func configureImageSize(ctx context.Context, cam *webcam.Webcam) error {
	for f, format := range cam.GetSupportedFormats() {
		if format == "Motion-JPEG" {
			if _, _, _, err := cam.SetImageFormat(f, uint32(600), uint32(600)); err != nil {
				return fmt.Errorf("failed to set image format: %w", err)
			}
			return nil

		}
	}
	return fmt.Errorf("camera does not support 'Motion-JPEG' format")
}

// addMotionDht adds header to JPEG file.
func addMotionDht(frame []byte) ([]byte, error) {
	// Append each segment to the image after splitting.
	start, end, _ := bytes.Cut(frame, sosMarker)
	var buf bytes.Buffer
	for _, segment := range [][]byte{start, dhtMarker, dht, sosMarker, end} {
		if _, err := buf.Write(segment); err != nil {
			return nil, fmt.Errorf("failed to write to buffer: %w", err)
		}
	}
	return buf.Bytes(), nil
}

// getAvgPixelColor is for get the bi-dimensional pixel array.
func getAvgPixelColor(frame []byte) (*passport.Pixel, error) {
	// Register .jpeg format with decoder.
	image.RegisterFormat("jpeg", "jpeg", jpeg.Decode, jpeg.DecodeConfig)

	img, _, err := image.Decode(bytes.NewReader(frame))
	if err != nil {
		fmt.Println(err.Error())
		return nil, err
	}

	var pixelsCount = 0
	var redSum float64
	var greenSum float64
	var blueSum float64
	bounds := img.Bounds()
	for y := bounds.Min.Y; y < bounds.Max.X; y++ {
		for x := bounds.Min.X; x < bounds.Max.X; x++ {
			pixelXY := color.RGBAModel.Convert(img.At(x, y)).(color.RGBA)
			redSum += float64(pixelXY.R)
			greenSum += float64(pixelXY.G)
			blueSum += float64(pixelXY.B)
			pixelsCount++
		}
	}

	return &passport.Pixel{
		R: int32(redSum / float64(pixelsCount)),
		G: int32(greenSum / float64(pixelsCount)),
		B: int32(blueSum / float64(pixelsCount)),
		A: 255}, nil
}
