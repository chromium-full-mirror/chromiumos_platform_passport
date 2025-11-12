// Copyright 2024 The ChromiumOS Authors
// Use of this source code is governed by a BSD-style license that can be
// found in the LICENSE file.

package server

import (
	"context"
	"fmt"
	"log"
	"log/slog"
	"net"

	"go.chromium.org/chromiumos/config/go/test/lab/api/passport"
	"go.chromium.org/chromiumos/test/util/portdiscovery"
	"google.golang.org/grpc"
	"google.golang.org/grpc/reflection"
)

// InitializeGRPCServer sets up the passport service and registers services with it.
func InitializeGRPCServer(ctx context.Context) (*grpc.Server, error) {
	// Configure server.
	var serverOpts []grpc.ServerOption
	serverOpts = append(serverOpts, grpc.MaxRecvMsgSize(256*1024*1024))
	serverOpts = append(serverOpts, grpc.MaxSendMsgSize(256*1024*1024))
	server := grpc.NewServer(serverOpts...)

	// Register reflection service to help query/debug services.
	reflection.Register(server)

	switchServcice, err := newSwitchServiceServer(ctx)
	if err != nil {
		return nil, fmt.Errorf("failed to start switch server: %w", err)
	}

	cameraService, err := newCameraServiceServer(ctx)
	if err != nil {
		return nil, fmt.Errorf("failed to start camera server: %w", err)
	}

	hidService, err := newHIDServiceServer(ctx)
	if err != nil {
		return nil, fmt.Errorf("failed to start hid server: %w", err)
	}

	usbTesterService, err := newUsbTesterServiceServer(ctx)
	if err != nil {
		return nil, fmt.Errorf("failed to start usb tester server: %w", err)
	}

	videoTesterService, err := newVideoTesterServiceServer(ctx)
	if err != nil {
		return nil, fmt.Errorf("failed to start video tester server: %w", err)
	}

	passport.RegisterSwitchServiceServer(server, switchServcice)
	passport.RegisterCameraServiceServer(server, cameraService)
	passport.RegisterHIDServiceServer(server, hidService)
	passport.RegisterUsbTesterServiceServer(server, usbTesterService)
	passport.RegisterVideoTesterServiceServer(server, videoTesterService)

	return server, nil
}

// Serve starts the gRPC server on the specified port and waits for completion.
// The server is stopped if the context expires. Will only return if the server
// has stopped. Returns a non-nil error if the server stopped on its own.
func Serve(ctx context.Context, server *grpc.Server, port int) error {
	// Start server, stopping it if ctx expires.
	addr := fmt.Sprintf("0.0.0.0:%d", port)
	slog.Info("Starting gRPC server", "addr", addr)
	lis, err := net.Listen("tcp", addr)
	if err != nil {
		return fmt.Errorf("failed to listen on tcp port %d: %w", port, err)
	}

	err = portdiscovery.WriteServiceMetadata("cros-passport", lis.Addr().String(), log.Default())
	if err != nil {
		slog.Warn("error when writing to metadata file", "error", err)
	}

	slog.Debug("gRPC service info", "serviceInfo", server.GetServiceInfo())
	serverChannel := make(chan error, 1)
	go func() {
		serverChannel <- server.Serve(lis)
	}()
	select {
	case err := <-serverChannel:
		return fmt.Errorf("grpc server error: %w", err)
	case <-ctx.Done():
		slog.Info("Stopping gRPC server gracefully")
		server.GracefulStop()
		return nil
	}
}
