// Copyright 2025 The ChromiumOS Authors
// Use of this source code is governed by a BSD-style license that can be
// found in the LICENSE file.

package hid

import (
	"fmt"
	"log/slog"
	"time"

	"github.com/spf13/cobra"
	"google.golang.org/grpc"
	"google.golang.org/grpc/credentials/insecure"
	"google.golang.org/protobuf/types/known/durationpb"

	"go.chromium.org/chromiumos/config/go/test/lab/api/passport"
)

func KeyPress() *cobra.Command {
	cmd := &keyPressCmd{}
	return cmd.Cmd()
}

type keyPressCmd struct {
	portArg    int
	hidDevices []string
	duration   int32
	keys       []string
}

func (c *keyPressCmd) run(cmd *cobra.Command, args []string) error {
	slog.Info("Running HID KeyPress")

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
		req := &passport.KeyboardActionRequest{
			DeviceId: hid,
			Keys:     c.keys,
			Action: &passport.KeyboardActionRequest_PressAndRelease_{
				PressAndRelease: &passport.KeyboardActionRequest_PressAndRelease{
					Duration: &durationpb.Duration{Nanos: c.duration},
				},
			},
		}
		if err := wrapHIDAction(cmd.Context(), client, hid, func() error {
			if _, err := client.KeyboardAction(cmd.Context(), req); err != nil {
				return fmt.Errorf("failed to press key, req: %v: %w", req, err)
			}
			return nil
		}); err != nil {
			return err
		}
	}
	return nil
}

func (c *keyPressCmd) Cmd() *cobra.Command {
	cmd := &cobra.Command{
		Use:   "key-press",
		Short: "Command to press and release keyboard button on HID Device",
		RunE:  c.run,
		Args:  cobra.NoArgs,
	}

	cmd.Flags().IntVar(
		&c.portArg, "port", 8300, "The port to start the service listening on.")

	cmd.Flags().StringArrayVar(
		&c.hidDevices, "devices", []string{}, "A list of devices to use or leave empty send to all.")

	cmd.Flags().Int32Var(
		&c.duration, "duration", int32(time.Millisecond*100), "The length of time to press the key for")

	cmd.Flags().StringArrayVar(
		&c.keys, "keys", []string{}, "A list of keys to type.")

	return cmd
}
