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
	"io"
	"log/slog"
	"os"
	"os/exec"
	"path/filepath"
	"strings"

	"github.com/blackjack/webcam"

	"go.chromium.org/chromiumos/config/go/test/lab/api/passport"
	"go.chromiumos.org/chromiumos/platform/passport/server"
)

const (
	jpegFormat                     = "Motion-JPEG"
	defaultWhiteBalanceTemperature = 4600
)

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
	slog.Info("Probing cameras using /sys/bus/usb/devices/")
	mapping, err := findCameras("")
	if err != nil {
		slog.Warn("Failed to probe cameras via sysfs, falling back to /dev/video*", "error", err)
		return s.getCamerasFallback(ctx, req)
	}

	var cameras []*passport.Camera
	for serial, info := range mapping {
		slog.Info("Found valid camera", "port", info.devPath, "serial", serial, "name", info.name)
		cameras = append(cameras,
			&passport.Camera{
				Id:   serial,
				Name: info.name,
			})
	}

	// If no cameras found via sysfs, fallback to /dev/video*
	if len(cameras) == 0 {
		slog.Warn("No cameras found via sysfs, falling back to /dev/video*")
		return s.getCamerasFallback(ctx, req)
	}

	slog.Info("Detected cameras", "count", len(cameras))
	return &passport.GetCamerasResponse{
		Cameras: cameras,
	}, nil
}

type cameraInfo struct {
	devPath string
	name    string
}

// findCameras searches for cameras in /sys/bus/usb/devices/ and returns a map of serial -> cameraInfo.
// If targetSerial is provided, it returns as soon as it finds that specific camera.
func findCameras(targetSerial string) (map[string]cameraInfo, error) {
	mapping := make(map[string]cameraInfo)
	devices, err := filepath.Glob("/sys/bus/usb/devices/*")
	if err != nil {
		return nil, fmt.Errorf("failed to glob /sys/bus/usb/devices/*: %w", err)
	}

	for _, devDir := range devices {
		base := filepath.Base(devDir)
		if strings.Contains(base, ":") {
			continue
		}

		serialPath := filepath.Join(devDir, "serial")
		serialBytes, err := os.ReadFile(serialPath)
		if err != nil {
			continue
		}
		serial := strings.TrimSpace(string(serialBytes))
		if serial == "" {
			continue
		}

		if targetSerial != "" && serial != targetSerial {
			continue
		}

		// Find video nodes for this device
		interfaces, err := filepath.Glob(filepath.Join(devDir, base+":*"))
		if err != nil {
			continue
		}
		for _, iface := range interfaces {
			v4lDir := filepath.Join(iface, "video4linux")
			if _, err := os.Stat(v4lDir); err != nil {
				continue
			}
			videoNodes, err := filepath.Glob(filepath.Join(v4lDir, "video*"))
			if err != nil || len(videoNodes) == 0 {
				continue
			}

			for _, node := range videoNodes {
				nodeName := filepath.Base(node)
				devPath := "/dev/" + nodeName

				cam, err := webcam.Open(devPath)
				if err != nil {
					continue
				}

				if !supportsJpeg(cam) {
					cam.Close()
					continue // Skip metadata devices
				}

				// Camera name is optional.
				name, err := cam.GetName()
				if err != nil {
					name = err.Error()
				}

				mapping[serial] = cameraInfo{devPath: devPath, name: name}
				cam.Close()
				if targetSerial != "" {
					return mapping, nil // Found the requested one
				}
				break // Found one valid node for this serial, move to next device
			}
			if _, ok := mapping[serial]; ok && targetSerial == "" {
				break // Move to next device
			}
		}
	}

	return mapping, nil
}

// getCamerasFallback probes cameras using /dev/video* as a fallback.
func (s *cameraPlugin) getCamerasFallback(ctx context.Context, req *passport.GetCamerasRequest) (*passport.GetCamerasResponse, error) {
	slog.Info("Probing cameras using /dev/video* (fallback)")
	ports, err := filepath.Glob("/dev/video*")
	if err != nil {
		return nil, fmt.Errorf("failed to probe for video devices: %w", err)
	}

	retries := 0
	var cameras []*passport.Camera
	for i := 0; i < len(ports); i++ {
		port := ports[i]
		cam, err := webcam.Open(port)
		if err != nil {
			slog.Warn("Failed to open port on device", "port", port)
			continue
		}

		if !supportsJpeg(cam) {
			slog.Warn("Skipping camera, Motion-JPEG format not supported", "port", port)
			cam.Close()
			continue
		}

		err = cam.StartStreaming()
		if err != nil {
			slog.Warn("Failed to start streaming on camera", "port", port, "error", err)
			if strings.Contains(err.Error(), "protocol error") && retries < 3 {
				slog.Warn("Retrying", "port", port)
				retries++
				i--
			}
			cam.Close()
			continue
		}

		name, err := cam.GetName()
		if err != nil {
			name = err.Error()
		}

		slog.Info("Found valid camera", "port", port, "name", name)
		cameras = append(cameras,
			&passport.Camera{
				Id:   port,
				Name: name,
			})
		cam.Close()
	}

	slog.Info("Detected cameras", "count", len(cameras))
	return &passport.GetCamerasResponse{
		Cameras: cameras,
	}, nil
}

// resolveDevicePath resolves a camera ID (serial or path) to a /dev/video* path.
func resolveDevicePath(id string) (string, error) {
	if strings.HasPrefix(id, "/dev/video") {
		return id, nil
	}

	mapping, err := findCameras(id)
	if err != nil {
		return "", err
	}

	if info, ok := mapping[id]; ok {
		return info.devPath, nil
	}

	return "", fmt.Errorf("camera with serial %s not found", id)
}

// GetAveragePixel gets the average pixel color detected by the specified camera.
func (s *cameraPlugin) GetAveragePixel(ctx context.Context, req *passport.GetAveragePixelRequest) (*passport.GetAveragePixelResponse, error) {
	devPort, err := resolveDevicePath(req.GetDeviceId())
	if err != nil {
		return nil, fmt.Errorf("failed to resolve device path: %w", err)
	}
	frame, err := captureFrame(ctx, devPort, req.GetExposureMicroseconds())
	if err != nil {
		return nil, fmt.Errorf("cannot get average pixel, failed to capture frame: %w", err)
	}
	p, err := getAvgPixelColor(frame)
	if err != nil {
		return nil, fmt.Errorf("failed to get pixel from webcam: %q: %w", req.GetDeviceId(), err)
	}

	return &passport.GetAveragePixelResponse{
		Pixel: p,
		Frame: frame,
	}, nil
}

// AnalyzeImageHSV gets the average pixel color detected by the specified camera.
func (s *cameraPlugin) AnalyzeImageHSV(ctx context.Context, req *passport.AnalyzeHSVRequest) (*passport.AnalyzeHSVResponse, error) {
	devPort, err := resolveDevicePath(req.GetDeviceId())
	if err != nil {
		return nil, fmt.Errorf("failed to resolve device path: %w", err)
	}
	frame, err := captureFrame(ctx, devPort, req.GetExposureMicroseconds())
	if err != nil {
		return nil, fmt.Errorf("cannot analyze image HSV, failed to capture frame: %w", err)
	}

	// convert req to a map of hsv ranges
	hsvRanges := make(map[string]HSVRange)
	for color, mask := range req.GetMasks() {
		hsvRanges[color] = HSVRange{
			Min: HSV{
				H: float64(mask.GetMin().GetHue()),
				S: float64(mask.GetMin().GetSaturation()),
				V: float64(mask.GetMin().GetValue()),
			},
			Max: HSV{
				H: float64(mask.GetMax().GetHue()),
				S: float64(mask.GetMax().GetSaturation()),
				V: float64(mask.GetMax().GetValue()),
			},
		}
	}

	percentageMatched, err := GetPercentageInBounds(frame, hsvRanges)
	if err != nil {
		return nil, fmt.Errorf("cannot analyze image HSV, failed to get percentage in bounds: %w", err)
	}

	// convert to float32
	percentageMatchedFloat := make(map[string]float32)
	for color, percentage := range percentageMatched {
		percentageMatchedFloat[color] = float32(percentage)
	}
	// return the response
	return &passport.AnalyzeHSVResponse{
		Frame:             frame,
		PercentageMatched: percentageMatchedFloat,
	}, nil
}

// CaptureVideo captures a tiled video from multiple cameras using ffmpeg directly.
func (s *cameraPlugin) CaptureVideo(req *passport.CaptureVideoRequest, stream passport.CameraService_CaptureVideoServer) error {
	slog.Info("Capturing tiled video using ffmpeg v4l2", "ids", req.GetDeviceIds(), "duration", req.GetDurationSeconds())

	// Resolve all IDs first
	ports := make([]string, 0, len(req.GetDeviceIds()))
	serials := make([]string, 0, len(req.GetDeviceIds()))
	for _, id := range req.GetDeviceIds() {
		devPort, err := resolveDevicePath(id)
		if err != nil {
			slog.Warn("Failed to resolve device path", "id", id, "error", err)
			continue
		}
		ports = append(ports, devPort)
		serials = append(serials, id)
	}

	// Set auto-exposure for all cameras before starting ffmpeg
	for i, port := range ports {
		serial := serials[i]
		cam, err := webcam.Open(port)
		if err != nil {
			slog.Warn("Failed to open camera to set auto-exposure", "port", port, "serial", serial, "error", err)
			continue
		}
		if err := setManualExposure(cam, 0); err != nil {
			slog.Warn("Failed to set auto-exposure", "port", port, "serial", serial, "error", err)
		}
		cam.Close()
	}

	// ffmpeg -f v4l2 -input_format mjpeg -video_size 640x480 -i /dev/video0 ...
	args := []string{}
	filter := ""
	for i, port := range ports {
		serial := serials[i]
		args = append(args, "-f", "v4l2", "-input_format", "mjpeg", "-video_size", "640x480", "-i", port)
		// Label each stream: [v0], [v1], etc.
		filter += fmt.Sprintf("[%d:v]drawtext=text='%s (%s)':fontcolor=white:fontsize=24:box=1:boxcolor=black@0.5:boxborderw=5:x=10:y=10[v%d];", i, serial, port, i)
	}

	num := len(ports)
	if num > 1 {
		var layout string
		switch num {
		case 2:
			layout = "0_0|w0_0"
		case 3:
			layout = "0_0|w0_0|0_h0"
		default: // 4
			layout = "0_0|w0_0|0_h0|w0_h0"
		}
		// Combine labeled streams into xstack
		for i := 0; i < num; i++ {
			filter += fmt.Sprintf("[v%d]", i)
		}
		filter += fmt.Sprintf("xstack=inputs=%d:layout=%s", num, layout)
		args = append(args, "-filter_complex", filter)
	} else if num == 1 {
		// Single camera, still add overlay
		args = append(args, "-vf", fmt.Sprintf("drawtext=text='%s (%s)':fontcolor=white:fontsize=24:box=1:boxcolor=black@0.5:boxborderw=5:x=10:y=10", serials[0], ports[0]))
	}

	args = append(args,
		"-t", fmt.Sprintf("%d", req.GetDurationSeconds()),
		"-c:v", "libx264",
		"-pix_fmt", "yuv420p",
		"-preset", "ultrafast",
		"-f", "mp4",
		"-movflags", "frag_keyframe+empty_moov",
		"pipe:1",
	)

	cmd := exec.CommandContext(stream.Context(), "ffmpeg", args...)
	stdout, err := cmd.StdoutPipe()
	if err != nil {
		return fmt.Errorf("failed to get ffmpeg stdout pipe: %w", err)
	}

	stderr := &bytes.Buffer{}
	cmd.Stderr = stderr

	if err := cmd.Start(); err != nil {
		return fmt.Errorf("failed to start ffmpeg: %w, stderr: %s", err, stderr.String())
	}

	// Read from ffmpeg stdout and stream to gRPC client
	chunk := make([]byte, 1024*1024)
	for {
		n, err := stdout.Read(chunk)
		if n > 0 {
			if sendErr := stream.Send(&passport.CaptureVideoResponse{
				Video:         chunk[:n],
				FileExtension: "mp4",
			}); sendErr != nil {
				return fmt.Errorf("failed to send video chunk: %w", sendErr)
			}
		}
		if err == io.EOF {
			break
		}
		if err != nil {
			return fmt.Errorf("failed to read from ffmpeg stdout: %w", err)
		}
	}

	if err := cmd.Wait(); err != nil {
		return fmt.Errorf("ffmpeg exited with error: %w, stderr: %s", err, stderr.String())
	}

	slog.Info("Tiled video capture complete", "duration", req.GetDurationSeconds(), "cameras", len(req.GetDeviceIds()))
	return nil
}

func captureFrame(ctx context.Context, devPort string, exposureMicroseconds int32) ([]byte, error) {
	const settlingTime = 10

	slog.Info("Capturing frame", "port", devPort, "requested_exposure_us", exposureMicroseconds, "forced_white_balance_temp", defaultWhiteBalanceTemperature)

	cam, err := webcam.Open(devPort)
	if err != nil {
		return nil, fmt.Errorf("failed to connect to camera %q: %w", devPort, err)
	}
	defer cam.Close()
	slog.Info("Opened camera", "port", devPort)

	if err := configureImageSize(ctx, cam); err != nil {
		return nil, fmt.Errorf("failed to configure image format for %q: %w", devPort, err)
	}

	for i := 0; true; i++ {
		err = cam.StartStreaming()
		if err != nil && i > 5 {
			return nil, fmt.Errorf("failed to start camera streaming")
		} else if err == nil {
			break
		}
		slog.Warn("Error starting streaming retrying:", "port", devPort, "error", err)
	}

	err = setManualExposure(cam, exposureMicroseconds)
	if err != nil {
		return nil, fmt.Errorf("failed to set manual exposure: %w", err)
	}

	err = setManualWhiteBalance(cam, defaultWhiteBalanceTemperature)
	if err != nil {
		return nil, fmt.Errorf("failed to set manual white balance: %w", err)
	}

	logAllControls(cam, devPort, "before_settling")

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
			if frameCount == settlingTime-1 {
				logAllControls(cam, devPort, "after_settling")
			}
			continue
		}

		logAllControls(cam, devPort, "after_frame")

		frame, err = addMotionDht(frame)
		if err != nil {
			return nil, fmt.Errorf("failed to add DHT to the frame %w", err)
		}
		return frame, nil
	}
	return nil, fmt.Errorf("failed to capture a frame before context expired")
}

func setManualExposure(cam *webcam.Webcam, exposureMicroseconds int32) error {
	// Set exposure to the requested value in 100uS units (V4L2_CID_EXPOSURE_ABSOLUTE)
	// if the value is 0, we will turn the exposure to auto.
	// Store control IDs we find by name
	controlIDs := make(map[string]webcam.ControlID)
	controls := cam.GetControls()
	for id, ctrl := range controls {
		// Store discovered IDs for easy lookup
		controlIDs[strings.ToLower(ctrl.Name)] = id
	}

	// the value here is setting enum for V4L2_CID_EXPOSURE_AUTO and the value of
	// 0 means V4L2_EXPOSURE_MANUAL (as defined in v4l2-controls.h)
	// 3 means V4L2_EXPOSURE_APERTURE_PRIORITY (as defined in v4l2-controls.h)
	const manualExposureSetting = int32(1)
	const autoExposureSetting = int32(3)

	if exposureMicroseconds == 0 {
		return setControl(cam, controlIDs, controls, "Auto Exposure", autoExposureSetting)
	}
	err := setControl(cam, controlIDs, controls, "Auto Exposure", manualExposureSetting)
	if err != nil {
		return err
	}
	// Exposure Time, Absolute is in 100uS units (V4L2_CID_EXPOSURE_ABSOLUTE)
	return setControl(cam, controlIDs, controls, "Exposure Time, Absolute", exposureMicroseconds/100)
}

func setControl(cam *webcam.Webcam, controlIDs map[string]webcam.ControlID, controls map[webcam.ControlID]webcam.Control, name string, value int32) error {
	id, found := controlIDs[strings.ToLower(name)]
	if !found || id == 0 {
		return fmt.Errorf("Control '%s' not found on this camera.", name)
	}

	// Get current control info to clamp the value
	ctrlInfo, ok := controls[id]
	if !ok {
		return fmt.Errorf("Control info for '%s' (ID %d) not found after discovery.", name, id)
	}
	setVal := value
	if setVal < ctrlInfo.Min {
		setVal = ctrlInfo.Min
	}
	if setVal > ctrlInfo.Max {
		setVal = ctrlInfo.Max
	}
	val, err := cam.GetControl(id)
	if err != nil {
		return fmt.Errorf("Failed to get control %s: %w", name, err)
	}
	slog.Info("Current control", "name", name, "value", val, "id", id)
	slog.Info("Setting control", "name", name, "value", setVal)
	return cam.SetControl(id, setVal)
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
	// Always inject the DHT before the first SOS (Start of Scan) marker.
	// We avoid brittle checks for existing markers or SOI markers as they
	// can have false positives in encoded data.
	start, end, found := bytes.Cut(frame, sosMarker)
	if !found {
		return nil, fmt.Errorf("SOS marker (0xFFDA) not found in frame")
	}

	var buf bytes.Buffer
	buf.Grow(len(frame) + len(dhtMarker) + len(dht))
	// Segments: [Start of image until SOS] + [DHT Marker] + [DHT Data] + [SOS Marker] + [Rest of image]
	buf.Write(start)
	buf.Write(dhtMarker)
	buf.Write(dht)
	buf.Write(sosMarker)
	buf.Write(end)

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
	for y := bounds.Min.Y; y < bounds.Max.Y; y++ {
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

func setManualWhiteBalance(cam *webcam.Webcam, temp int32) error {
	controlIDs := make(map[string]webcam.ControlID)
	controls := cam.GetControls()
	for id, ctrl := range controls {
		controlIDs[strings.ToLower(ctrl.Name)] = id
	}

	const manualWBSetting = int32(0)
	const autoWBSetting = int32(1)

	if temp == 0 {
		err := setControlWithAlternativeNames(cam, controlIDs, controls, []string{"White Balance Temperature, Auto", "White Balance, Automatic"}, autoWBSetting)
		if err != nil {
			return err
		}
		return nil
	}

	err := setControlWithAlternativeNames(cam, controlIDs, controls, []string{"White Balance Temperature, Auto", "White Balance, Automatic"}, manualWBSetting)
	if err != nil {
		return err
	}

	return setControl(cam, controlIDs, controls, "White Balance Temperature", temp)
}

func setControlWithAlternativeNames(cam *webcam.Webcam, controlIDs map[string]webcam.ControlID, controls map[webcam.ControlID]webcam.Control, names []string, value int32) error {
	var err error
	for _, name := range names {
		err = setControl(cam, controlIDs, controls, name, value)
		if err == nil {
			return nil
		}
	}
	return fmt.Errorf("failed to set control with any of the names %v: %w", names, err)
}

func logAllControls(cam *webcam.Webcam, devPort string, phase string) {
	controls := cam.GetControls()
	var args []any
	args = append(args, "port", devPort, "phase", phase)
	for id, ctrl := range controls {
		val, err := cam.GetControl(id)
		if err != nil {
			args = append(args, ctrl.Name, fmt.Sprintf("error: %v", err))
		} else {
			args = append(args, ctrl.Name, val)
		}
	}
	slog.Info("Camera controls state", args...)
}
