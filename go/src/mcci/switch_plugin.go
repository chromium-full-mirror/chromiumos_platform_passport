// Copyright 2025 The ChromiumOS Authors
// Use of this source code is governed by a BSD-style license that can be
// found in the LICENSE file.

// Package mcci provides support for interacting with mcci switches.
package mcci

import (
	"context"
	"fmt"
	"log/slog"
	"strings"
	"time"

	"go.bug.st/serial"

	"go.chromium.org/chromiumos/config/go/test/lab/api/passport"
	"go.chromiumos.org/chromiumos/platform/passport/port"
	"go.chromiumos.org/chromiumos/platform/passport/server"
)

// Aliases for switch port states.
const (
	SwitchDisabled = passport.SwitchPortState_SWITCH_PORT_DISABLED
	SwitchEnabled  = passport.SwitchPortState_SWITCH_PORT_ENABLED
	// The MCCI switches don't have a power reset API, disable the switch instead.
	SwitchResetCmd  = "\rport 0\r"
	SwitchStatusCmd = "\rstatus\r"
	SwitchSelectCmd = "\rport %s\r"
)

var (
	// SwitchModels is an array of supported mcci models.
	SwitchModels = [...]string{"Model 3142"}
)

// switchInfo contains cached information about an mcci switch.
type switchInfo struct {
	uid   string
	port  string
	model string
}

// switchPlugin is an mcci switch plugin.
type switchPlugin struct {
	// Maps switch UID to switch details.
	switches map[string]*switchInfo
	// inherit port manager implementation
	port.PortManager
}

func init() {
	slog.Info("Probing for mcci")
	// Register the switch plugin with the main passport application.
	server.RegisterSwitchPlugin(
		&switchPlugin{
			switches: make(map[string]*switchInfo),
		})
}

// Init initializes the plugin.
func (s *switchPlugin) Init(ctx context.Context) error {
	// Nothing to do here.
	return nil
}

// GetSwitches probes all mcci switches connected to the host.
func (s *switchPlugin) GetSwitches(ctx context.Context, req *passport.GetSwitchesRequest) (*passport.GetSwitchesResponse, error) {
	slog.Info("Probing for switches")
	if err := s.refreshSwitches(ctx); err != nil {
		return nil, fmt.Errorf("failed to probe for switches: %w", err)
	}

	var switches []*passport.SwitchFixture
	for id := range s.switches {
		switches = append(switches, &passport.SwitchFixture{Id: id})
	}

	return &passport.GetSwitchesResponse{
		Switches: switches,
	}, nil
}

// ConfigureSwitchPort configures a single port on a switch.
func (s *switchPlugin) ConfigureSwitchPort(ctx context.Context, req *passport.ConfigureSwitchPortRequest) (*passport.ConfigureSwitchPortResponse, error) {
	slog.Info("Configuring switch", "switch", req.GetSwitchId(), "state", req.GetState())
	if err := s.controlSwitch(ctx, req.GetSwitchId(), req.GetState(), req.GetPortId()); err != nil {
		return nil, err
	}

	return &passport.ConfigureSwitchPortResponse{}, nil
}

// ResetAllSwitches re-initializes all found switches and sets them to the "disabled" state.
func (s *switchPlugin) ResetAllSwitches(ctx context.Context, req *passport.ResetAllSwitchesRequest) (*passport.ResetAllSwitchesResponse, error) {
	slog.Info("Resetting switches")
	resp, err := s.GetSwitches(ctx, &passport.GetSwitchesRequest{})
	if err != nil {
		return nil, fmt.Errorf("failed to get MCCI switches")
	}

	for _, sw := range resp.GetSwitches() {
		slog.Info("Resetting switch", "switch", sw.GetId())
		id := strings.ToUpper(sw.GetId())

		if _, err := sendDataToSerialPort(ctx, s.switches[id].port, SwitchResetCmd); err != nil {
			return nil, fmt.Errorf("failed to request serial port: %w", err)
		}
	}

	return &passport.ResetAllSwitchesResponse{}, nil
}

// Name returns the plugin's name for logging purposes.
func (s *switchPlugin) Name() string {
	return "mcci_switch_plugin"
}

func (s *switchPlugin) refreshSwitches(ctx context.Context) error {
	ports, err := serial.GetPortsList()
	if err != nil {
		return fmt.Errorf("failed to get port list: %w", err)
	}

	// Retrieve the switch information from each serial port.
	switches := make(map[string]*switchInfo)
	for _, port := range ports {
		// Only use serial ports containing ACM*, e.g. /dev/ttyACM0
		// and not used by other plugins.
		if !strings.Contains(port, "ACM") || s.IsIgnored(port) {
			slog.Debug("Skipping port", "port", port)
			continue
		}

		// Sending "status" to an MCCI serial device should respond with a bunch
		// of lines containing the device info.
		response, err := sendDataToSerialPort(ctx, port, SwitchStatusCmd)
		if err != nil {
			slog.Error("Failed to read serial port", "port", port, "error", err)
			continue
		}

		// Scan the response for the line containing the ID info. It's possible
		// there are extranious lines in the device output that have been buffered
		// but not read yet so we need to check each one for the expected line.
		validDevice := isMcciDevice(response)
		if !validDevice {
			slog.Debug("Skipping port info", "info", response)
			s.ReleasePort(port)
			continue
		}

		deviceData, err := sendDataToSerialPort(ctx, port, SwitchStatusCmd)
		if err != nil {
			slog.Error("Failed to read serial port", "port", port, "error", err)
			s.ReleasePort(port)
			continue
		}

		info := parseDevice(deviceData)

		info.port = port
		slog.Info("Found valid device", "model", info.model, "port", info.port, "uid", info.uid)
		s.UsePort(port)
		switches[info.uid] = info
		break
	}

	s.switches = switches
	return nil
}

// controlSwitch sets the switch status to on or off.
func (s *switchPlugin) controlSwitch(ctx context.Context, id string, state passport.SwitchPortState, port_id string) error {
	id = strings.ToUpper(id)
	sw, ok := s.switches[id]
	if !ok {
		return fmt.Errorf("unable to find the serial port of the switch ID: %s", id)
	}

	switch state {
	case SwitchDisabled:
		{
			cmd := fmt.Sprintf(SwitchSelectCmd, "0")
			if _, err := sendDataToSerialPort(ctx, sw.port, cmd); err != nil {
				return fmt.Errorf("failed to request serial port: %w", err)
			}
		}
	case SwitchEnabled:
		{
			cmd := fmt.Sprintf(SwitchSelectCmd, port_id)
			if _, err := sendDataToSerialPort(ctx, sw.port, cmd); err != nil {
				return fmt.Errorf("failed to request serial port: %w", err)
			}
		}
	default:
		return fmt.Errorf("operation not supported: %s", state.String())
	}

	return nil
}

// sendDataToSerialPort returns a response after sends a request to the serial port.
func sendDataToSerialPort(ctx context.Context, port, req string) (string, error) {
	mode := &serial.Mode{
		BaudRate: 9600,
		DataBits: 8,
		Parity:   serial.NoParity,
		StopBits: serial.OneStopBit,
	}
	usbPort, err := serial.Open(port, mode)

	if err != nil {
		return "", fmt.Errorf("failed to open serial port: %w", err)
	}
	defer usbPort.Close()

	if _, err := usbPort.Write([]byte(req)); err != nil {
		return "", fmt.Errorf("failed to write serial port: %w", err)
	}

	if err := usbPort.SetReadTimeout(time.Second); err != nil {
		return "", fmt.Errorf("failed to set read timeout: %w", err)
	}

	// Read the response.
	var result = ""
	for {
		buff := make([]byte, 1000)
		n, err := usbPort.Read(buff)

		if err != nil {
			return result, fmt.Errorf("serial read error: %w", err)
		}

		if n == 0 {
			break
		}

		result = result + string(buff[:n])
	}

	return result, nil
}

// isMcciDevice checks the usb device's info to see if it corresponds to
// a known mcci device. If yes, it returns the device's control information.
//
// example:
//
// Model 3142
// Serial number: xxxxxxxxxxxx
// FW Version: 01
// HW Version: 01
// Tag:
// Accelerometer enable voltage: 21.000 V
// Accelerometer trip value: 5
// Changed: OVT:0 ACT:0
// Accelerometer: Good
// ADC: Good
// PORTC: 0x0  PORTD: 0x1B  PORTF: 0x70
// CC1 detect:    0x00
// CC1 led:       0
// J3 power:      0
// J4 power:      0
// Select:        0
// Output enable: 0
// Select not:    1
// SS Enable not: 1
// HS Enable not: 1
// --> (Model 3142, xxxxxxxxxxxx, ...)
func isMcciDevice(device string) bool {
	for _, mcci_model := range SwitchModels {
		if strings.Contains(device, mcci_model) {
			return true
		}
	}

	return false
}

func parseDevice(device string) *switchInfo {
	lines := strings.Split(device, "\n")

	// For mcci devices, the serial is character 15 to character 26
	// on the second line.
	serial := strings.ToUpper(lines[1][15:27])

	// Model number is the first 10 characters in the device string.
	model := device[0:10]

	// Extract the uid from serial, this is the expected id used by
	// the test.
	return &switchInfo{
		uid:   serial,
		model: model,
	}
}
