// Copyright 2025 The ChromiumOS Authors
// Use of this source code is governed by a BSD-style license that can be
// found in the LICENSE file.

package cameras

import (
	"fmt"
	"log/slog"
	"os"
	"strings"
	"time"

	"github.com/spf13/cobra"
	"google.golang.org/grpc"
	"google.golang.org/grpc/credentials/insecure"

	"go.chromium.org/chromiumos/config/go/test/lab/api/passport"
)

func Capture() *cobra.Command {
	cmd := &captureCmd{}
	return cmd.Cmd()
}

type captureCmd struct {
	portArg  int
	cameras  []string
	analyze  bool
	exposure int32
}

func (c *captureCmd) run(cmd *cobra.Command, args []string) error {
	slog.Info("Running Camera capture")

	addr := fmt.Sprintf("0.0.0.0:%d", c.portArg)
	conn, err := grpc.Dial(addr, grpc.WithTransportCredentials(insecure.NewCredentials()))
	if err != nil {
		return fmt.Errorf("failed to connect to service at %q: %w", addr, err)
	}
	defer conn.Close()

	client := passport.NewCameraServiceClient(conn)
	if len(c.cameras) == 0 {
		resp, err := client.GetCameras(cmd.Context(), &passport.GetCamerasRequest{})
		if err != nil {
			return fmt.Errorf("failed to query cameras: %w", err)
		}
		for _, camera := range resp.GetCameras() {
			c.cameras = append(c.cameras, camera.GetId())
		}
	}
	slog.Info("Capturing image for cameras", "cameras", c.cameras)
	for _, camera_id := range c.cameras {
		frame := []byte{}
		if c.analyze {
			req := &passport.AnalyzeHSVRequest{
				DeviceId: camera_id,
				Masks: map[string]*passport.HSVMask{
					"Red":   &passport.HSVMask{Min: &passport.HSV{Hue: 340, Saturation: 0.5, Value: 0.55}, Max: &passport.HSV{Hue: 20, Saturation: 1.0, Value: 1.0}},
					"Green": &passport.HSVMask{Min: &passport.HSV{Hue: 95, Saturation: 0.5, Value: 0.55}, Max: &passport.HSV{Hue: 165, Saturation: 1.0, Value: 1.0}},
					"Blue":  &passport.HSVMask{Min: &passport.HSV{Hue: 220, Saturation: 0.5, Value: 0.55}, Max: &passport.HSV{Hue: 260, Saturation: 1.0, Value: 1.0}},
					"Off":   &passport.HSVMask{Min: &passport.HSV{Hue: 0, Saturation: 0.0, Value: 0.0}, Max: &passport.HSV{Hue: 360, Saturation: 0.4, Value: 0.6}},
				},
				ExposureMicroseconds: c.exposure,
			}
			resp, err := client.AnalyzeImageHSV(cmd.Context(), req)
			if err != nil {
				return fmt.Errorf("failed to capture image for camera: %s: %w", camera_id, err)
			}
			slog.Info("HSV analysis value", "percentage matched", resp.GetPercentageMatched())
			frame = resp.GetFrame()
		} else {
			req := &passport.GetAveragePixelRequest{
				DeviceId:             camera_id,
				ExposureMicroseconds: c.exposure,
			}
			resp, err := client.GetAveragePixel(cmd.Context(), req)
			if err != nil {
				return fmt.Errorf("failed to capture iamge for camera: %s: %w", camera_id, err)
			}
			slog.Info("average pixel value", "pixel", resp.GetPixel())
			frame = resp.GetFrame()
		}
		timestamp := time.Now().Format("20060102_150405")
		outfile := fmt.Sprintf("%s_%s.jpg", strings.ReplaceAll(camera_id, "/", "_"), timestamp)
		err = os.WriteFile(outfile, frame, 0644)
		if err != nil {
			return fmt.Errorf("could not write image to %s: %w", outfile, err)
		}
		slog.Info("wrote iamge for to file", "filename", outfile)
	}
	return nil
}

func (c *captureCmd) Cmd() *cobra.Command {
	cmd := &cobra.Command{
		Use:   "capture",
		Short: "Command to capture cameras found by the PassPort service",
		RunE:  c.run,
		Args:  cobra.NoArgs,
	}

	cmd.Flags().IntVar(
		&c.portArg, "port", 8300, "The port to start the service listening on.")

	cmd.Flags().StringArrayVar(
		&c.cameras, "cameras", []string{}, "A list of cameras to capture iamges from or leave empty to capture on all.")

	cmd.Flags().BoolVar(
		&c.analyze, "analyze", false, "Whether to analyze the image for HSV ranges.")

	cmd.Flags().Int32Var(
		&c.exposure, "exposure", 0, "Exposure time in microseconds.")

	return cmd
}
