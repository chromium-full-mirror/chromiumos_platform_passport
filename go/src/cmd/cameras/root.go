// Copyright 2025 The ChromiumOS Authors
// Use of this source code is governed by a BSD-style license that can be
// found in the LICENSE file.

package cameras

import (
	"github.com/spf13/cobra"
)

func RootCmd() *cobra.Command {
	cmd := &cobra.Command{
		Use:   "cameras",
		Short: "Command to interact with PassPort camera service. ",
		Args:  cobra.NoArgs,
	}

	cmd.AddCommand(
		Capture(),
		Detect(),
		Record(),
	)
	return cmd
}
