// Copyright 2025 The ChromiumOS Authors
// Use of this source code is governed by a BSD-style license that can be
// found in the LICENSE file.

package usb

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
	slog.Info("Running Switch Detect")

	addr := fmt.Sprintf("0.0.0.0:%d", c.portArg)
	conn, err := grpc.Dial(addr, grpc.WithTransportCredentials(insecure.NewCredentials()))
	if err != nil {
		return fmt.Errorf("failed to connect to service at %q: %w", addr, err)
	}
	defer conn.Close()

	client := passport.NewUsbTesterServiceClient(conn)

	resp1, err := client.GetTesters(cmd.Context(), &passport.GetTestersRequest{})
	if err != nil {
		return err
	}

	var res []string
	for _, sw := range resp1.GetTesters() {
		res = append(res, sw.GetId())
	}
	slog.Info("Detected usb testers", "usb-testers", res)

	return nil
}

func (c *detectCmd) Cmd() *cobra.Command {
	cmd := &cobra.Command{
		Use:   "detect",
		Short: "Command to detect usb testers found by the passport host",
		RunE:  c.run,
		Args:  cobra.NoArgs,
	}

	cmd.Flags().IntVar(
		&c.portArg, "port", 8300, "The port to start the service listening on.")

	return cmd
}
