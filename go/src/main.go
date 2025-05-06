// Copyright 2024 The ChromiumOS Authors
// Use of this source code is governed by a BSD-style license that can be
// found in the LICENSE file.

// Package main includes the main function for running
// passport as an executable.
package main

import (
	"context"
	"fmt"
	"log/slog"
	"os"
	"os/signal"

	"go.chromiumos.org/chromiumos/platform/passport/cmd"
)

func main() {
	// Create context that will cancel when a SIGINT signal is received.
	ctx, cancel := context.WithCancel(context.Background())
	interruptSignalChannel := make(chan os.Signal, 1)
	signal.Notify(interruptSignalChannel, os.Interrupt)
	defer func() {
		signal.Stop(interruptSignalChannel)
		cancel()
	}()
	go func() {
		select {
		case <-interruptSignalChannel:
			slog.Info("received SIGINT, cancelling operations")
			cancel()
		case <-ctx.Done():
		}
	}()

	// Run the command.
	rootCmd, err := cmd.RootCmd()
	if err != nil {
		fmt.Printf("Failed to build root command: %v", err)
		os.Exit(1)
	}
	if err = rootCmd.ExecuteContext(ctx); err != nil {
		fmt.Printf("Execution failed: %v", err)
		os.Exit(1)
	}
}
