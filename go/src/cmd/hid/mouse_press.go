// Copyright 2025 The ChromiumOS Authors
// Use of this source code is governed by a BSD-style license that can be
// found in the LICENSE file.

package hid

import (
	"fmt"
	"log/slog"
	"strings"
	"time"

	"github.com/spf13/cobra"
	"google.golang.org/grpc"
	"google.golang.org/grpc/credentials/insecure"
	"google.golang.org/protobuf/types/known/durationpb"

	"go.chromium.org/chromiumos/config/go/test/lab/api/passport"
)

func MouseClick() *cobra.Command {
	cmd := &mouseClickCmd{}
	return cmd.Cmd()
}

type mouseClickCmd struct {
	portArg    int
	hidDevices []string
	duration   int32
	button     string
}

func (c *mouseClickCmd) run(cmd *cobra.Command, args []string) error {
	slog.Info("Running HID MouseClick")

	addr := fmt.Sprintf("0.0.0.0:%d", c.portArg)
	conn, err := grpc.Dial(addr, grpc.WithTransportCredentials(insecure.NewCredentials()))
	if err != nil {
		return fmt.Errorf("failed to connect to service at %q: %w", addr, err)
	}
	defer conn.Close()

	c.button = strings.ToUpper(c.button)
	if _, ok := passport.MouseActionRequest_Button_value[c.button]; !ok {
		return fmt.Errorf("unknown mouse button %q", c.button)
	}
	button := passport.MouseActionRequest_Button(passport.MouseActionRequest_Button_value[c.button])

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
			Action: &passport.MouseActionRequest_PressAndRelease_{
				PressAndRelease: &passport.MouseActionRequest_PressAndRelease{
					Button:   button,
					Duration: &durationpb.Duration{Nanos: c.duration},
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

func (c *mouseClickCmd) Cmd() *cobra.Command {
	cmd := &cobra.Command{
		Use:   "mouse-press",
		Short: "Command to press and release mouse button on HID Device",
		RunE:  c.run,
		Args:  cobra.NoArgs,
	}

	cmd.Flags().IntVar(
		&c.portArg, "port", 8300, "The port to start the service listening on.")

	cmd.Flags().StringArrayVar(
		&c.hidDevices, "devices", []string{}, "A list of devices to use or leave empty send to all.")

	cmd.Flags().Int32Var(
		&c.duration, "duration", int32(time.Millisecond*100), "The length of time to press the button for")

	cmd.Flags().StringVar(
		&c.button, "button", "left", "The button to press, oneof: left, right, middle, forward, back")

	return cmd
}
