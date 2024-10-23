// Copyright 2024 The ChromiumOS Authors
// Use of this source code is governed by a BSD-style license that can be
// found in the LICENSE file.

// Package allion provides support for interacting with Allion switches.
package allion

import (
	"context"
	"fmt"
	"log/slog"
	"strings"
	"time"

	"go.bug.st/serial"

	"go.chromium.org/chromiumos/config/go/test/lab/api/passport"
	"go.chromiumos.org/chromiumos/platform/passport/server"
)

// Aliases for switch port states.
const (
	SwitchDisabled = passport.SwitchPortState_SWITCH_PORT_DISABLED
	SwitchEnabled  = passport.SwitchPortState_SWITCH_PORT_ENABLED
	SwitchFlip     = passport.SwitchPortState_SWITCH_PORT_FLIP
)

var (
	// switchModels maps switch model IDs to a set of switch states and their corresponding "commands"
	// since each switch model has a specific command needed to apply a state change.
	switchModels = map[string]commandMap{
		"AUS19129": {SwitchDisabled: "0", SwitchEnabled: "1", SwitchFlip: "2"},
		"AHS20079": {SwitchDisabled: "2", SwitchEnabled: "1"},
		"AUS20019": {SwitchDisabled: "2", SwitchEnabled: "1"},
		"ADT21090": {SwitchDisabled: "3", SwitchEnabled: "1"},
		"XXRJ45SW": {SwitchDisabled: "2", SwitchEnabled: "1"},
	}
)

// Maps switch states to commands to be sent to the device.
type commandMap map[passport.SwitchPortState]string

// switchInfo contains cached information about an Allion switch.
type switchInfo struct {
	uid      string
	port     string
	model    string
	commands commandMap
}

// switchPlugin is an allion switch plugin.
type switchPlugin struct {
	// Maps switch UID to switch details.
	switches map[string]*switchInfo
}

func init() {
	// Register the switch plugin with the main passport application.
	server.RegisterSwitchPlugin(
		&switchPlugin{
			switches: make(map[string]*switchInfo),
		})
}

// GetSwitches probes all allion switches connected to the host.
func (s *switchPlugin) GetSwitches(ctx context.Context, req *passport.GetSwitchesRequest) (*passport.GetSwitchesResponse, error) {
	slog.Info("Probing for switches")
	if err := s.refreshSwitches(ctx); err != nil {
		return nil, fmt.Errorf("failed to probe for switches: %w", err)
	}

	var switches []*passport.SwitchFixture
	for id, _ := range s.switches {
		switches = append(switches, &passport.SwitchFixture{Id: id})
	}

	return &passport.GetSwitchesResponse{
		Switches: switches,
	}, nil
}

// ConfigureSwitchPort configures a single port on a switch.
func (s *switchPlugin) ConfigureSwitchPort(ctx context.Context, req *passport.ConfigureSwitchPortRequest) (*passport.ConfigureSwitchPortResponse, error) {
	slog.Info("Configuring switch", "switch", req.GetSwitchId(), "state", req.GetState())
	if err := s.controlSwitch(ctx, req.GetSwitchId(), req.GetState()); err != nil {
		return nil, err
	}

	return &passport.ConfigureSwitchPortResponse{}, nil
}

// ResetAllSwitches re-initializes all found switches and sets them to the "disabled" state.
func (s *switchPlugin) ResetAllSwitches(ctx context.Context, req *passport.ResetAllSwitchesRequest) (*passport.ResetAllSwitchesResponse, error) {
	slog.Info("Resetting switches")
	resp, err := s.GetSwitches(ctx, &passport.GetSwitchesRequest{})
	if err != nil {
	}

	for _, sw := range resp.GetSwitches() {
		slog.Info("Resetting switch", "switch", sw.GetId())
		if err := s.controlSwitch(ctx, sw.GetId(), SwitchDisabled); err != nil {
			return nil, fmt.Errorf("failed to disable switch: %q: %w", sw.GetId(), err)
		}
	}

	return &passport.ResetAllSwitchesResponse{}, nil
}

// Name returns the plugin's name for logging purposes.
func (s *switchPlugin) Name() string {
	return "allion_switch_plugin"
}

func (s *switchPlugin) refreshSwitches(ctx context.Context) error {
	ports, err := serial.GetPortsList()
	if err != nil {
		return fmt.Errorf("failed to get port list: %w", err)
	}

	// Retrieve the switch information from each serial port.
	switches := make(map[string]*switchInfo)
	for _, port := range ports {
		// Only use serial ports containing ACM*, e.g. /dev/ttyACM0.
		if !strings.Contains(port, "ACM") {
			slog.Debug("Skipping port", "port", port)
			continue
		}

		// Sending "i" to an allion serial device should respond with a single
		// line containing the product ID e.g. AHS20079_A00_01_2206201400.
		response, err := sendDataToSerialPort(ctx, port, "i", time.Second/2)
		if err != nil {
			slog.Error("Failed to read serial port", "port", port, "error", err)
			continue
		}

		// Scan the response for the line containing the ID info. It's possible
		// there are extranious lines in the device output that have been buffered
		// but not read yet so we need to check each one for the expected line.
		for _, line := range strings.Split(response, "\n") {
			validDevice, info := isAllionDevice(line)
			if !validDevice {
				slog.Debug("Skipping port info line", "line", line)
				continue
			}

			info.port = port
			slog.Info("Found valid device", "device", line, "port", info.port, "uid", info.uid)
			switches[info.uid] = info
			break
		}
	}

	// Log switches that we were not able to detect this time.
	for k, v := range s.switches {
		if _, ok := switches[k]; !ok {
			slog.Warn("unable to find previously detected switch", "switch id", k, "port", v.port)
		}
	}

	s.switches = switches
	return nil
}

// controlSwitch sets the switch status to on or off.
func (s *switchPlugin) controlSwitch(ctx context.Context, id string, state passport.SwitchPortState) error {
	id = strings.ToUpper(id)
	sw, ok := s.switches[id]
	if !ok {
		return fmt.Errorf("unable to find the serial port of the switch ID: %s", id)
	}

	cmd, ok := sw.commands[state]
	if !ok {
		return fmt.Errorf("unable to find the corresponding command of the switch ID: %q, status: %s", id, state)
	}

	slog.Info("Setting switch state", "id", id, "state", state, "port", sw.port, "cmd", cmd)
	if _, err := sendDataToSerialPort(ctx, sw.port, cmd, 3*time.Second); err != nil {
		return fmt.Errorf("failed to request serial port: %w", err)
	}

	return nil
}

// sendDataToSerialPort returns a response after sends a request to the serial port.
func sendDataToSerialPort(ctx context.Context, port, req string, timeout time.Duration) (string, error) {
	mode := &serial.Mode{
		BaudRate: 9600,
	}
	usbPort, err := serial.Open(port, mode)
	if err != nil {
		return "", fmt.Errorf("failed to open serial port: %w", err)
	}
	defer usbPort.Close()

	if err := usbPort.SetReadTimeout(timeout); err != nil {
		return "", fmt.Errorf("failed to set read timeout: %w", err)
	}

	if _, err := usbPort.Write([]byte(req)); err != nil {
		return "", fmt.Errorf("failed to write serial port: %w", err)
	}

	// Read the response.
	var resp string
	buff := make([]byte, 1000)
	for ctx.Err() == nil {
		n, err := usbPort.Read(buff)
		if err != nil {
			return "", fmt.Errorf("failed to read serial port: %w", err)
		}
		if n == 0 {
			fmt.Println("\nEOF")
			break
		}

		resp = strings.TrimSpace(string(buff[:n]))
	}

	return resp, nil
}

// isAllionDevice checks the usb device's info line to see if it corresponds to
// a known allion device. If yes, it returns the device's control information.
//
// example:
//
//	AHS20079_A00_01_2206201400 -> (true, AHS20079, 2007901)
func isAllionDevice(device string) (bool, *switchInfo) {
	const switchIDLen = 22
	if len(device) < switchIDLen {
		return false, nil
	}

	// For allion devices, serial is first 15 characters.
	// Serials are case insensitive.
	serial := strings.ToUpper(device[0:15])

	// Model number is the first 8 characters of the serial.
	model := serial[0:8]
	if _, ok := switchModels[model]; !ok {
		return false, nil
	}

	// Extract the uid from serial, this is the expected id used by
	// the test.
	return true, &switchInfo{
		uid:      device[3:8] + device[13:15],
		model:    model,
		commands: switchModels[model],
	}
}
