// Copyright 2025 The ChromiumOS Authors
// Use of this source code is governed by a BSD-style license that can be
// found in the LICENSE file.

package usb

import (
	"github.com/spf13/cobra"
)

func RootCmd() *cobra.Command {
	cmd := &cobra.Command{
		Use:   "usb-tester",
		Short: "Command to interact with PassPort usb-tester service. ",
		Args:  cobra.NoArgs,
	}

	cmd.AddCommand(
		Detect(),
	)
	return cmd
}
