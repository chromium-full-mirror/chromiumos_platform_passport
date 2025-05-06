// Copyright 2025 The ChromiumOS Authors
// Use of this source code is governed by a BSD-style license that can be
// found in the LICENSE file.

package cameras

import (
	"fmt"
	"log/slog"

	"github.com/spf13/cobra"
	"google.golang.org/grpc"
	"google.golang.org/grpc/credentials/insecure"

	"go.chromium.org/chromiumos/config/go/test/lab/api/passport"
)

func Detect() *cobra.Command {
	cmd := &detectCmd{}
	return cmd.Cmd()
}

type detectCmd struct {
	portArg int
}

func (c *detectCmd) run(cmd *cobra.Command, args []string) error {
	slog.Info("Running Camera Detect")

	addr := fmt.Sprintf("0.0.0.0:%d", c.portArg)
	conn, err := grpc.Dial(addr, grpc.WithTransportCredentials(insecure.NewCredentials()))
	if err != nil {
		return fmt.Errorf("failed to connect to service at %q: %w", addr, err)
	}
	defer conn.Close()

	client := passport.NewCameraServiceClient(conn)
	resp, err := client.GetCameras(cmd.Context(), &passport.GetCamerasRequest{})
	if err != nil {
		return fmt.Errorf("failed to query cameras: %w", err)
	}
	slog.Info("Detected cameras", "cameras", resp.GetCameras())
	return nil
}

func (c *detectCmd) Cmd() *cobra.Command {
	cmd := &cobra.Command{
		Use:   "detect",
		Short: "Command to detect cameras found by the PassPort service",
		RunE:  c.run,
		Args:  cobra.NoArgs,
	}

	cmd.Flags().IntVar(
		&c.portArg, "port", 8300, "The port to start the service listening on.")

	return cmd
}
