// Copyright 2025 The ChromiumOS Authors
// Use of this source code is governed by a BSD-style license that can be
// found in the LICENSE file.

package hid

import (
	"fmt"
	"log/slog"

	"github.com/spf13/cobra"
	"google.golang.org/grpc"
	"google.golang.org/grpc/credentials/insecure"

	"go.chromium.org/chromiumos/config/go/test/lab/api/passport"
)

func MouseMove() *cobra.Command {
	cmd := &mouseMoveCmd{}
	return cmd.Cmd()
}

type mouseMoveCmd struct {
	portArg    int
	hidDevices []string
	x          int32
	y          int32
}

func (c *mouseMoveCmd) run(cmd *cobra.Command, args []string) error {
	slog.Info("Running HID MouseMove")

	addr := fmt.Sprintf("0.0.0.0:%d", c.portArg)
	conn, err := grpc.Dial(addr, grpc.WithTransportCredentials(insecure.NewCredentials()))
	if err != nil {
		return fmt.Errorf("failed to connect to service at %q: %w", addr, err)
	}
	defer conn.Close()

	client := passport.NewHIDServiceClient(conn)
	if len(c.hidDevices) == 0 {
		ids, err := getHIDDevices(cmd.Context(), client)
		if err != nil {
			return fmt.Errorf("failed go query HID devices: %v", err)
		}
		c.hidDevices = ids
	}

	for _, hid := range c.hidDevices {
		req := &passport.MouseActionRequest{
			DeviceId: hid,
			Action: &passport.MouseActionRequest_Move_{
				Move: &passport.MouseActionRequest_Move{
					X: c.x,
					Y: c.y,
				},
			},
		}
		if err := wrapHIDAction(cmd.Context(), client, hid, func() error {
			if _, err := client.MouseAction(cmd.Context(), req); err != nil {
				return fmt.Errorf("mouse action failed, req: %v: %w", req, err)
			}
			return nil
		}); err != nil {
			return err
		}
	}
	return nil
}

func (c *mouseMoveCmd) Cmd() *cobra.Command {
	cmd := &cobra.Command{
		Use:   "mouse-move",
		Short: "Command to move mouse button on HID Device",
		RunE:  c.run,
		Args:  cobra.NoArgs,
	}

	cmd.Flags().IntVar(
		&c.portArg, "port", 8300, "The port to start the service listening on.")

	cmd.Flags().StringArrayVar(
		&c.hidDevices, "devices", []string{}, "A list of devices to use or leave empty send to all.")

	cmd.Flags().Int32Var(
		&c.x, "x", 0, "The horizontal distance to move the mouse, +=moving right, -=moving left.")

	cmd.Flags().Int32Var(
		&c.y, "y", 0, "The horizontal distance to move the mouse, +=moving down, -=moving up.")

	return cmd
}
