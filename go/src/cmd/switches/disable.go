// Copyright 2025 The ChromiumOS Authors
// Use of this source code is governed by a BSD-style license that can be
// found in the LICENSE file.

package switches

import (
	"fmt"
	"log/slog"

	"github.com/spf13/cobra"
	"google.golang.org/grpc"
	"google.golang.org/grpc/credentials/insecure"

	"go.chromium.org/chromiumos/config/go/test/lab/api/passport"
)

func Disable() *cobra.Command {
	cmd := &disableCmd{}
	return cmd.Cmd()
}

type disableCmd struct {
	portArg    int
	switches   []string
	switchPort string
}

func (c *disableCmd) run(cmd *cobra.Command, args []string) error {
	slog.Info("Running Switch Disable")

	addr := fmt.Sprintf("0.0.0.0:%d", c.portArg)
	conn, err := grpc.Dial(addr, grpc.WithTransportCredentials(insecure.NewCredentials()))
	if err != nil {
		return fmt.Errorf("failed to connect to service at %q: %w", addr, err)
	}
	defer conn.Close()

	client := passport.NewSwitchServiceClient(conn)
	if len(c.switches) == 0 {
		ids, err := getSwitches(cmd.Context(), client)
		if err != nil {
			return fmt.Errorf("failed go query switches: %v", err)
		}
		c.switches = ids
	}

	return configureSwitches(cmd.Context(), client, c.switches, c.switchPort, passport.SwitchPortState_SWITCH_PORT_DISABLED)
}

func (c *disableCmd) Cmd() *cobra.Command {
	cmd := &cobra.Command{
		Use:   "disable",
		Short: "Command to disable switches found by the PassPort host",
		RunE:  c.run,
		Args:  cobra.NoArgs,
	}

	cmd.Flags().IntVar(
		&c.portArg, "port", 8300, "The port to start the service listening on.")

	cmd.Flags().StringArrayVar(
		&c.switches, "switches", []string{}, "A list of switches to configure or leave empty to disable all.")

	cmd.Flags().StringVar(
		&c.switchPort, "switch-port", "", "The port on the switch to control.")

	return cmd
}
