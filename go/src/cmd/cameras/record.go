// Copyright 2026 The ChromiumOS Authors
// Use of this source code is governed by a BSD-style license that can be
// found in the LICENSE file.

package cameras

import (
	"fmt"
	"io"
	"log/slog"
	"os"
	"time"

	"github.com/spf13/cobra"
	"google.golang.org/grpc"
	"google.golang.org/grpc/credentials/insecure"

	"go.chromium.org/chromiumos/config/go/test/lab/api/passport"
)

func Record() *cobra.Command {
	cmd := &recordCmd{}
	return cmd.Cmd()
}

type recordCmd struct {
	portArg  int
	cameras  []string
	duration int32
}

func (c *recordCmd) run(cmd *cobra.Command, args []string) error {
	slog.Info("Running Camera record")

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

	if len(c.cameras) > 4 {
		slog.Warn("More than 4 cameras detected, limiting to first 4 for tiling.", "count", len(c.cameras))
		c.cameras = c.cameras[:4]
	}

	slog.Info("Recording video for cameras", "cameras", c.cameras, "duration", c.duration)
	req := &passport.CaptureVideoRequest{
		DeviceIds:       c.cameras,
		DurationSeconds: c.duration,
	}
	stream, err := client.CaptureVideo(cmd.Context(), req)
	if err != nil {
		return fmt.Errorf("failed to start video recording: %w", err)
	}

	var f *os.File
	var outfile string
	fileExtension := "mp4" // default

	for {
		resp, err := stream.Recv()
		if err == io.EOF {
			break
		}
		if err != nil {
			return fmt.Errorf("error receiving video data: %w", err)
		}

		if f == nil {
			if resp.GetFileExtension() != "" {
				fileExtension = resp.GetFileExtension()
			}
			timestamp := time.Now().Format("20060102_150405")
			outfile = fmt.Sprintf("cameras_%s.%s", timestamp, fileExtension)
			f, err = os.Create(outfile)
			if err != nil {
				return fmt.Errorf("failed to create output file %q: %w", outfile, err)
			}
			defer f.Close()
		}

		if _, err := f.Write(resp.GetVideo()); err != nil {
			return fmt.Errorf("failed to write to file %q: %w", outfile, err)
		}
	}

	if f != nil {
		slog.Info("wrote video to file", "filename", outfile)
	} else {
		slog.Warn("received no video data from service")
	}

	return nil
}

func (c *recordCmd) Cmd() *cobra.Command {
	cmd := &cobra.Command{
		Use:   "record",
		Short: "Command to record video from cameras found by the PassPort service",
		RunE:  c.run,
		Args:  cobra.NoArgs,
	}

	cmd.Flags().IntVar(
		&c.portArg, "port", 8300, "The port to start the service listening on.")

	cmd.Flags().StringArrayVar(
		&c.cameras, "cameras", []string{}, "A list of cameras to record video from or leave empty to record on all.")

	cmd.Flags().Int32Var(
		&c.duration, "duration", 5, "Duration of the video in seconds.")

	return cmd
}
