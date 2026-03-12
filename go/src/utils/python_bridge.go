// Copyright 2025 The ChromiumOS Authors
// Use of this source code is governed by a BSD-style license that can be
// found in the LICENSE file.

// Package utils implements utils function used across multiple modules.
package utils

import (
	"bufio"
	"errors"
	"fmt"
	"io"
	"log/slog"
	"os"
	"os/exec"
	"regexp"
	"strconv"
	"time"
)

const (
	// This pattern is used to scan the python server for the port it's running on.
	PORT_SCAN_PATTERN = "PORT_BOUND"
)

// LaunchPythonBridgefAndGetPort starts the external python process, pipes its output to stdout,
// and waits for a specific handshake string (PORT_BOUND:X) to determine the dynamic port.
// It returns the port, the command object (for cleanup), or an error.
func LaunchPythonBridgefAndGetPort(binPath string, portArg int64, deviceType string) (int64, *exec.Cmd, error) {
	args := []string{"--port", strconv.FormatInt(portArg, 10), "--port-scan-pattern", PORT_SCAN_PATTERN}
	if deviceType != "" {
		args = append(args, "--device", deviceType)
	}

	cmd := exec.Command(binPath, args...)

	// Force python unbuffered output
	cmd.Env = append(os.Environ(), "PYTHONUNBUFFERED=1")

	// Create a pipe manually so we can merge Stdout and Stderr
	// pipeReader is for us (Go) to read.
	// pipeWriter is for the child (Python) to write.
	pipeReader, pipeWriter, err := os.Pipe()
	if err != nil {
		return 0, nil, fmt.Errorf("failed to create OS pipe: %w", err)
	}

	// Redirect BOTH stdout and stderr to the same pipe
	// This ensures we catch the PORT_BOUND message even if it's logged to stderr.
	cmd.Stdout = pipeWriter
	cmd.Stderr = pipeWriter

	if err := cmd.Start(); err != nil {
		pipeWriter.Close()
		pipeReader.Close()
		return 0, nil, fmt.Errorf("failed to start process: %w", err)
	}
	pipeWriter.Close()

	// Buffered channels to prevent goroutine leaks on timeout
	portChan := make(chan int64, 1)
	errChan := make(chan error, 1)

	go func() {
		// Use bufio.Reader to read line by line without line length limits.
		reader := bufio.NewReader(pipeReader)
		found := false
		re := regexp.MustCompile(fmt.Sprintf("%s:(\\d+)", PORT_SCAN_PATTERN))

		for {
			line, err := reader.ReadString('\n')

			// ReadString can return both data AND an error simultaneously
			// if the stream ends without a newline.
			if len(line) > 0 {
				fmt.Fprint(os.Stdout, line)

				if !found {
					matches := re.FindStringSubmatch(line)
					if len(matches) >= 2 {
						if p, err := strconv.Atoi(matches[1]); err == nil {
							found = true
							// Use non-blocking send in case receiver is gone
							select {
							case portChan <- int64(p):
							default:
							}
						}
					}
				}
			}

			if err != nil {
				if err != io.EOF && !found {
					select {
					case errChan <- fmt.Errorf("error reading python output: %w", err):
					default:
					}
				}
				break // Exit the loop
			}
		}

		if !found {
			select {
			case errChan <- fmt.Errorf("process stream ended without printing PORT_BOUND"):
			default:
			}
		}
	}()

	select {
	case p := <-portChan:
		return p, cmd, nil
	case err := <-errChan:
		pipeReader.Close()
		return 0, nil, err
	case <-time.After(45 * time.Second):
		KillPythonControl(cmd)
		pipeReader.Close()
		return 0, nil, fmt.Errorf("timed out waiting for app to start")
	}
}

// KillPythonControl safely kills the given command process, handling nil pointers and preventing
// zombie processes by always calling Wait(). It logs errors during termination but ignores
// os.ErrProcessDone if the process has already exited.
func KillPythonControl(cmd *exec.Cmd) {
	if cmd == nil {
		return
	}

	if cmd.ProcessState != nil && cmd.ProcessState.Exited() {
		return
	}

	if cmd.Process != nil {
		if err := cmd.Process.Kill(); err != nil {
			if !errors.Is(err, os.ErrProcessDone) {
				slog.Error("Failed to kill process", "error", err)
				return
			}
		}

		// Ignore output as wait will always return an error after kill.
		cmd.Wait()
	}
}
