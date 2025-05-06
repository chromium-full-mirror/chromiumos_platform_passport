// Copyright 2025 The ChromiumOS Authors
// Use of this source code is governed by a BSD-style license that can be
// found in the LICENSE file.

package switches

import (
	"github.com/spf13/cobra"
)

func RootCmd() *cobra.Command {
	cmd := &cobra.Command{
		Use:   "switches",
		Short: "Command to interact with PassPort switch service. ",
		Args:  cobra.NoArgs,
	}

	cmd.AddCommand(
		Detect(),
		Enable(),
		Disable(),
	)
	return cmd
}
