// Copyright 2024 The ChromiumOS Authors
// Use of this source code is governed by a BSD-style license that can be
// found in the LICENSE file.

// Package allion provides support for interacting with Allion switches.
package allion

import (
	"context"
	"fmt"
	"log/slog"
	"strconv"
	"strings"
	"time"

	"go.bug.st/serial"

	"go.chromium.org/chromiumos/config/go/test/lab/api/passport"
	"go.chromiumos.org/chromiumos/platform/passport/port"
	"go.chromiumos.org/chromiumos/platform/passport/server"
	"go.chromiumos.org/chromiumos/platform/passport/utils"
)

// Aliases for switch port states.
const (
	SwitchDisabled = passport.SwitchPortState_SWITCH_PORT_DISABLED
	SwitchEnabled  = passport.SwitchPortState_SWITCH_PORT_ENABLED
	SwitchFlip     = passport.SwitchPortState_SWITCH_PORT_FLIP
)

var (
	// each switch model has a specific command needed to apply a state change
	defaultPort       = "default"
	maxTime     int64 = 9999999999

	// switchCommands maps switch model ID to a command map for disabling and flipping that specific switch
	switchCommands = map[string][]versionedCommand{
		"AUS19129": {newVersionedCommand(maxTime, commandMap{SwitchDisabled: "0", SwitchFlip: "2"})},
		"AHS20079": {newVersionedCommand(maxTime, commandMap{SwitchDisabled: "2"})},
		"AUS20019": {
			newVersionedCommand(2510269999, commandMap{SwitchDisabled: "2"}),
			newVersionedCommand(maxTime, commandMap{SwitchDisabled: "6"}),
		},
		"ADT21090": {newVersionedCommand(maxTime, commandMap{SwitchDisabled: "3"})},
		"XXRJ45SW": {newVersionedCommand(maxTime, commandMap{SwitchDisabled: "2"})},
		"AUS22095": {newVersionedCommand(maxTime, commandMap{SwitchDisabled: "3"})},
		"AHS24067": {newVersionedCommand(maxTime, commandMap{SwitchDisabled: "3"})},
		"ADS24068": {newVersionedCommand(maxTime, commandMap{SwitchDisabled: "3"})},
		"AUS24080": {newVersionedCommand(maxTime, commandMap{SwitchDisabled: "5"})},
	}

	// switchEnabledByPortIdCommands maps switch model ID to a command map for enabling that specific switch by port ID
	switchEnabledByPortIdCommands = map[string]portCommandMap{
		"AUS19129": {defaultPort: "1"},
		"AHS20079": {defaultPort: "1"},
		"AUS20019": {defaultPort: "1", "A": "1", "B": "2"},
		"ADT21090": {defaultPort: "1"},
		"XXRJ45SW": {defaultPort: "1"},
		"AUS22095": {defaultPort: "1", "A": "1", "B": "2"},
		"AHS24067": {defaultPort: "1"},
		"ADS24068": {defaultPort: "1"},
		"AUS24080": {defaultPort: "1", "A": "1", "B": "2", "C": "3", "D": "4"},
	}
)

type versionedCommand struct {
	maxTimestamp int64
	commands     commandMap
}

func newVersionedCommand(timestamp int64, command commandMap) versionedCommand {
	return versionedCommand{timestamp, command}
}

// Maps switch states to commands to be sent to the device.
type commandMap map[passport.SwitchPortState]string

// Maps switch port to commands to be sent to the device.
type portCommandMap map[string]string

// switchInfo contains cached information about an Allion switch.
type switchInfo struct {
	uid                  string
	port                 string
	model                string
	version              int64
	commands             commandMap
	enableByPortCommands portCommandMap
	lastCommand          string
}

// switchPlugin is an allion switch plugin.
type switchPlugin struct {
	// Maps switch UID to switch details.
	switches map[string]*switchInfo
	// inherit port manager implementation
	port.PortManager
}

func init() {
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

// GetSwitches probes all allion switches connected to the host.
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
	slog.Info("Configuring switch", "switch", req.GetSwitchId(), "state", req.GetState(), "port id", req.GetPortId())

	portId := req.GetPortId()
	if len(portId) == 0 {
		portId = defaultPort
	}
	if err := s.controlSwitch(ctx, req.GetSwitchId(), req.GetState(), portId); err != nil {
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
		if err := s.controlSwitch(ctx, sw.GetId(), SwitchDisabled, defaultPort); err != nil {
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
		// Only use serial ports containing ACM*, e.g. /dev/ttyACM0
		// and not used by other plugins.
		if !strings.Contains(port, "ACM") || s.IsIgnored(port) {
			slog.Debug("Skipping port", "port", port)
			continue
		}

		// Sending "i" to an allion serial device should respond with a single
		// line containing the product ID e.g. AHS20079_A00_01_2206201400.
		response, err := sendDataToSerialPort(ctx, port, "i", time.Second/2)
		if err != nil {
			slog.Error("Failed to read serial port", "port", port, "error", err)
			s.ReleasePort(port)
			continue
		}

		// Scan the response for the line containing the ID info. It's possible
		// there are extranious lines in the device output that have been buffered
		// but not read yet so we need to check each one for the expected line.
		for _, line := range strings.Split(response, "\n") {
			validDevice, info := isAllionDevice(line)
			if !validDevice {
				slog.Debug("Skipping port info line", "line", line)
				s.ReleasePort(port)
				continue
			}

			info.port = port
			slog.Info("Found valid device", "device", line, "port", info.port, "uid", info.uid)
			s.UsePort(port)

			if infoOld, ok := s.switches[info.uid]; ok {
				// if we've previously seen this switch, then reuse some info.
				info.lastCommand = infoOld.lastCommand
			}

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
func (s *switchPlugin) controlSwitch(ctx context.Context, id string, state passport.SwitchPortState, portId string) error {
	id = strings.ToUpper(id)
	sw, ok := s.switches[id]
	if !ok {
		return fmt.Errorf("unable to find the serial port of the switch ID: %s", id)
	}

	cmd := ""
	if state == SwitchEnabled {
		if cmd, ok = sw.enableByPortCommands[portId]; !ok {
			return fmt.Errorf("unable to find the corresponding port command of the switch ID: %q, port ID: %s", id, portId)
		}

	} else {
		if cmd, ok = sw.commands[state]; !ok {
			return fmt.Errorf("unable to find the corresponding command of the switch ID: %q, status: %s", id, state)
		}
	}

	slog.Info("previous switch command", "switch", id, "command", sw.lastCommand)
	if sw.lastCommand == cmd {
		slog.Info("requested switch state matches previous, skipping", "switch", id, "command", cmd)
		return nil
	}
	// Clear last command for now so if there's an error anywhere we're not left in an incorrect state.
	sw.lastCommand = ""

	slog.Info("Setting switch state", "switch id", id, "state", state, "port id", portId, "switch port", sw.port, "cmd", cmd)
	if _, err := sendDataToSerialPort(ctx, sw.port, cmd, 3*time.Second); err != nil {
		return fmt.Errorf("failed to request serial port: %w", err)
	}
	sw.lastCommand = cmd

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

	data, err := utils.ReadWriteSerialPort(ctx, usbPort, timeout, []byte(req))
	if err != nil {
		return "", fmt.Errorf("failed to read from serial port: %q: %w", port, err)
	}
	return strings.TrimSpace(string(data)), nil
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
	versionStr := device[16:]
	version, err := strconv.ParseInt(versionStr, 10, 64)
	slog.Warn("Failed to parse version", "version string", versionStr, "error", err)
	if err != nil {
		return false, nil
	}

	// Model number is the first 8 characters of the serial.
	model := serial[0:8]
	commands, ok := getSwitchCommand(model, version)
	if !ok {
		return false, nil
	}

	if _, ok := switchEnabledByPortIdCommands[model]; !ok {
		return false, nil
	}

	// Extract the uid from serial, this is the expected id used by
	// the test.
	return true, &switchInfo{
		uid:                  device[3:8] + device[13:15],
		model:                model,
		version:              version,
		commands:             commands,
		enableByPortCommands: switchEnabledByPortIdCommands[model],
	}
}

func getSwitchCommand(model string, version int64) (commandMap, bool) {
	// Check each version, return the first version that ours is less than or equal to (lexicographically)
	for _, versionedMap := range switchCommands[model] {
		if version <= versionedMap.maxTimestamp {
			return versionedMap.commands, true
		}
	}
	if c, ok := switchCommands[model]; ok {
		return c[0].commands, true
	}
	return nil, false
}
