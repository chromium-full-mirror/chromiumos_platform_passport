// Copyright 2024 The ChromiumOS Authors
// Use of this source code is governed by a BSD-style license that can be
// found in the LICENSE file.

// Package main includes the main function for running
// passport as an executable.
package main

import (
	"context"
	"flag"
	"fmt"
	"io"
	"log/slog"
	"os"
	"os/signal"
	"path/filepath"
	"time"

	"go.chromium.org/chromiumos/config/go/test/lab/api/passport"
	"go.chromiumos.org/chromiumos/platform/passport/server"
	"google.golang.org/grpc"
	"google.golang.org/grpc/credentials/insecure"
)

var (
	portArg     int
	logLevelArg string
	modeArg     string
	logPathArg  string
)

// runMode represents the mode to start the service in.
type runMode int

const (
	// Start the executable as a passport API server
	runModeServer runMode = iota
	// Start a server in the backgound and test it all within the same process.
	runModeTest
	// Connect to an existing server (as a client) on the same machine and query
	// the devices connected to it. This can be used to verify functionality on a host
	// that already has a service running.
	runModeDetect
)

// runArgs are runtime arguments that can be set with positional arguments in
// the format <key>=<value> and is case-insensitive.
type runArgs struct {
	// ListenPort is the port the gRPC server shall listen on.
	ListenPort int

	// LogLevel is the level for the logger.
	LogLevel slog.Level

	// The path to the directory to create logs in.
	LogPath string

	// Mode is how the executable should be run.
	Mode runMode
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

func main() {
	parsedArgs, err := parseRunArgs()
	if err != nil {
		fmt.Printf("Failed to parse run args: %v\n", err)
		os.Exit(1)
	}

	logFile, err := createLogFile(parsedArgs.LogPath)
	if err != nil {
		fmt.Printf("Failed to create log file: %v", err)
		os.Exit(1)
	}
	writers := []io.Writer{os.Stderr, logFile}
	out := io.MultiWriter(writers...)
	defer logFile.Close()

	// Set logging based on args.
	handler := slog.NewTextHandler(out, &slog.HandlerOptions{
		Level:     parsedArgs.LogLevel,
		AddSource: true,
	})
	slog.SetDefault(slog.New(handler))

	slog.Info("Starting passport", "args", parsedArgs)

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
			slog.Warn("Received SIGINT, shutting down server")
			cancel()
		case <-ctx.Done():
		}
	}()

	// If mode is server, then just serve in foreground and return when done.
	if parsedArgs.Mode == runModeServer {
		s, err := server.InitializeGRPCServer(ctx)
		if err != nil {
			fmt.Printf("Failed to initialize gRPC server: %v", err)
			os.Exit(1)
		}

		if err := server.Serve(ctx, s, parsedArgs.ListenPort); err != nil {
			fmt.Printf("Failed to serve gRPC server: %v", err)
			os.Exit(1)
		}
		return
	}

	// If mode is test, then start serving in background.
	if parsedArgs.Mode == runModeTest {
		s, err := server.InitializeGRPCServer(ctx)
		if err != nil {
			fmt.Printf("Failed to initialize gRPC server: %v", err)
			os.Exit(1)
		}

		go func() {
			if err := server.Serve(ctx, s, parsedArgs.ListenPort); err != nil {
				fmt.Printf("Failed to serve gRPC server: %v", err)
				os.Exit(1)
			}
		}()
		// Wait a few seconds to make sure the service is established before moving on.
		time.Sleep(5 * time.Second)
	}

	// If in detect or test mode, then query service.
	addr := fmt.Sprintf("0.0.0.0:%d", parsedArgs.ListenPort)
	if err := detectDevices(ctx, addr); err != nil {
		fmt.Printf("Failed to detect devices on host: %v", err)
		os.Exit(1)
	}
}

// parseRunArgs parses simple CLI run arguments in the format <key>=<value>.
func parseRunArgs() (*runArgs, error) {
	flag.IntVar(&portArg, "port", 8300, "The port to start the service listening on.")
	flag.StringVar(&logLevelArg, "log-level", "INFO", "The level to use while logging.")
	flag.StringVar(&modeArg, "mode", "SERVER", "The mode to run passport executable in.")
	flag.StringVar(&logPathArg, "log-path", "/tmp/cros-passport", "The path to use when logging.")
	flag.Parse()

	parsedArgs := &runArgs{
		ListenPort: portArg,
		LogPath:    logPathArg,
	}

	switch logLevelArg {
	case "DEBUG":
		parsedArgs.LogLevel = slog.LevelDebug
	case "INFO":
		parsedArgs.LogLevel = slog.LevelInfo
	case "WARN":
		parsedArgs.LogLevel = slog.LevelWarn
	case "ERROR":
		parsedArgs.LogLevel = slog.LevelError
	default:
		return nil, fmt.Errorf("invalid argument log-level: value %q, is not one of: DEBUG, INFO, WARN, or ERROR", logLevelArg)
	}

	switch modeArg {
	case "SERVER":
		parsedArgs.Mode = runModeServer
	case "TEST":
		parsedArgs.Mode = runModeTest
	case "DETECT":
		parsedArgs.Mode = runModeDetect
	default:
		return nil, fmt.Errorf("invalid argument mode: value %q, is not one of: SERVER, TEST, DETECT", modeArg)
	}
	return parsedArgs, nil
}

// detectDevices sends a client request to a server at the specified address and
// logs the devices found.
func detectDevices(ctx context.Context, addr string) error {
	conn, err := grpc.Dial(addr, grpc.WithTransportCredentials(insecure.NewCredentials()))
	if err != nil {
		return fmt.Errorf("failed to connect to service at %q: %w", addr, err)
	}
	defer conn.Close()

	switchClient := passport.NewSwitchServiceClient(conn)
	resp1, err := switchClient.GetSwitches(ctx, &passport.GetSwitchesRequest{})
	if err != nil {
		return fmt.Errorf("failed to query switches: %w", err)
	}
	slog.Info("Detected switches", "switches", resp1.GetSwitches())

	cameraClient := passport.NewCameraServiceClient(conn)
	resp2, err := cameraClient.GetCameras(ctx, &passport.GetCamerasRequest{})
	if err != nil {
		return fmt.Errorf("failed to query switches: %w", err)
	}
	slog.Info("Detected cameras", "cameras", resp2.GetCameras())
	return nil
}
