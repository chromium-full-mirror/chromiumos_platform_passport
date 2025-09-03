// Copyright 2025 The ChromiumOS Authors
// Use of this source code is governed by a BSD-style license that can be
// found in the LICENSE file.

package cmd

import (
	"bufio"
	"fmt"
	"io"
	"log/slog"
	"os"
	"path/filepath"

	"github.com/spf13/cobra"

	"go.chromiumos.org/chromiumos/platform/passport/cmd/cameras"
	"go.chromiumos.org/chromiumos/platform/passport/cmd/hid"
	"go.chromiumos.org/chromiumos/platform/passport/cmd/switches"
	"go.chromiumos.org/chromiumos/platform/passport/cmd/usb"
	"go.chromiumos.org/chromiumos/platform/passport/server"
)

const BUILD_INFO_PATH string = "/build_info.txt"

// runMode represents the mode to start the service in.
type runMode int

type rootCmd struct {
	portArg     int
	logLevelArg string
	logPathArg  string
	logFile     *os.File
}

func RootCmd() (*cobra.Command, error) {
	cmd := &rootCmd{}
	return cmd.Cmd()
}

func (r *rootCmd) Cmd() (*cobra.Command, error) {
	cmd := &cobra.Command{
		Use:                "cros-passport",
		Short:              "Utility for launching/managing PassPort service",
		PersistentPreRunE:  r.persistentPreRun,
		RunE:               r.run,
		PersistentPostRunE: r.persistentPostRun,
	}

	cmd.Flags().IntVar(
		&r.portArg, "port", 8300, "The port to start the service listening on.")

	cmd.PersistentFlags().StringVar(&r.logLevelArg, "log-level", "INFO", "The level to use while logging.")
	cmd.PersistentFlags().StringVar(&r.logPathArg, "log-path", "/tmp/cros-passport", "The path to use when logging.")

	cmd.AddCommand(
		switches.RootCmd(),
		cameras.RootCmd(),
		hid.RootCmd(),
		usb.RootCmd(),
	)

	return cmd, nil
}

func (r *rootCmd) persistentPreRun(cmd *cobra.Command, args []string) error {
	logFile, err := createLogFile(r.logPathArg)
	if err != nil {
		return fmt.Errorf("Failed to create log file: %v", err)
	}
	r.logFile = logFile

	writers := []io.Writer{os.Stderr, logFile}
	out := io.MultiWriter(writers...)

	// Set logging based on args.
	handler := slog.NewTextHandler(out, &slog.HandlerOptions{
		Level:     r.LogLevel(),
		AddSource: true,
	})
	slog.SetDefault(slog.New(handler))
	return nil
}

func (r *rootCmd) run(cmd *cobra.Command, args []string) error {
	slog.Info("Starting passport", "args", cmd.Flags())

	file, err := os.Open(BUILD_INFO_PATH)

	// Don't fail server start if build info is missing.
	if err == nil {
		defer file.Close()

		scanner := bufio.NewScanner(file)
		for scanner.Scan() {
			slog.Info("Build info: " + scanner.Text())
		}
	}

	// If mode is server, then just serve in foreground and return when done.
	s, err := server.InitializeGRPCServer(cmd.Context())
	if err != nil {
		return fmt.Errorf("Failed to initialize gRPC server: %v", err)
	}

	if err := server.Serve(cmd.Context(), s, r.portArg); err != nil {
		return fmt.Errorf("Failed to serve gRPC server: %v", err)
	}
	return nil
}

func (r *rootCmd) persistentPostRun(cmd *cobra.Command, args []string) error {
	if r.logFile != nil {
		r.logFile.Close()
	}
	return nil
}

// createLogFile creates a file and its parent directory for logging purpose.
func createLogFile(fullPath string) (*os.File, error) {
	if err := os.MkdirAll(fullPath, 0755); err != nil {
		return nil, fmt.Errorf("failed to create directory %v: %w", fullPath, err)
	}

	logFullPathName := filepath.Join(fullPath, "log.txt")

	// Log the full output of the command to disk.
	logFile, err := os.Create(logFullPathName)
	if err != nil {
		return nil, fmt.Errorf("failed to create file %v: %w", fullPath, err)
	}
	return logFile, nil
}

func (r *rootCmd) LogLevel() slog.Level {
	switch r.logLevelArg {
	case "DEBUG":
		return slog.LevelDebug
	case "INFO":
		return slog.LevelInfo
	case "WARN":
		return slog.LevelWarn
	case "ERROR":
		return slog.LevelError
	default:
		return slog.LevelInfo
	}
}
