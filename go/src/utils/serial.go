// Copyright 2026 The ChromiumOS Authors
// Use of this source code is governed by a BSD-style license that can be
// found in the LICENSE file.

package utils

import (
	"bytes"
	"context"
	"fmt"
	"log/slog"
	"time"

	"go.bug.st/serial"
)

// ReadWriteSerialPort writes the request to a serial port and returns the result.
func ReadWriteSerialPort(ctx context.Context, port serial.Port, timeout time.Duration, data ...[]byte) ([]byte, error) {
	const interCharTimeout = 200 * time.Millisecond

	if err := port.SetReadTimeout(timeout); err != nil {
		return nil, fmt.Errorf("failed to set read timeout: %w", err)
	}

	// Make sure there is no old data in the buffer.
	if err := port.ResetInputBuffer(); err != nil {
		return nil, fmt.Errorf("failed to reset input buffer on port: %w", err)
	}
	if err := port.ResetOutputBuffer(); err != nil {
		return nil, fmt.Errorf("failed to reset output buffer on port: %w", err)
	}

	// Make sure we don't leave the go-routine running in the background on another error.
	ctx, cancel := context.WithCancel(ctx)
	defer cancel()

	// Start background go routine to read from the port.
	resCh := make(chan []byte, 1)
	errCh := make(chan error, 1)
	go func() {
		var respBuffer bytes.Buffer
		buff := make([]byte, 1024)

		for ctx.Err() == nil {
			slog.Debug("Reading from port")
			n, err := port.Read(buff)
			if err != nil {
				slog.Error("Port read error", "error", err)
				errCh <- fmt.Errorf("failed to read serial port: %w", err)
				return
			} else if n == 0 {
				// No data and no error means read timeout.
				resCh <- respBuffer.Bytes()
				slog.Debug("No data or errors received from port, exiting...")
				return
			}

			// Buffer is empty so this is the first successful read, shorten timeout for subsequent reads.
			slog.Debug("Received bytes from port", "byte count", n, "data", string(buff[:n]))
			if respBuffer.Len() == 0 {
				slog.Debug("Received first burst of data from port, shortening timeout")
				if err := port.SetReadTimeout(interCharTimeout); err != nil {
					errCh <- fmt.Errorf("failed to reduce timeout after frist read: %w", err)
				}
			}
			respBuffer.Write(buff[:n])
		}
	}()

	for _, b := range data {
		slog.Debug("Writing to port", "request", string(b))
		if _, err := port.Write(b); err != nil {
			return nil, fmt.Errorf("failed to write serial port: %w", err)
		}
	}

	// Wait for the goroutine to finish or for the overall context to be done.
	slog.Debug("Write complete, waiting for response")
	select {
	case <-ctx.Done():
		return nil, ctx.Err()
	case err := <-errCh:
		return nil, err
	case res := <-resCh:
		return res, nil
	}
}
