// Copyright 2025 The ChromiumOS Authors
// Use of this source code is governed by a BSD-style license that can be
// found in the LICENSE file.

// Package allion provides support for interacting with Allion devices.
package allion

import (
	"bytes"
	"context"
	"fmt"
	"io"
	"log/slog"
	"math"
	"strings"
	"time"

	"github.com/pkg/errors"
	"go.bug.st/serial"

	"go.chromium.org/chromiumos/config/go/test/lab/api/passport"
	"go.chromium.org/infra/cros/servo/testing"
	"go.chromiumos.org/chromiumos/platform/passport/server"
	"go.chromiumos.org/chromiumos/platform/passport/utils"
)

var (
	mode = &serial.Mode{
		BaudRate: 9600,
	}
	checkData = []byte{0x57, 0xAB}
)

func init() {
	// Register the HID plugin with the main passport application.
	server.RegisterHIDPlugin(
		&hidPlugin{
			simulators: map[string]*hidSimulatorInfo{},
		})
}

type hidSimulatorInfo struct {
}

type hidPlugin struct {
	simulators map[string]*hidSimulatorInfo
}

func (h *hidPlugin) Name() string {
	return "allion-hid"
}

// GetHIDDevices probes for all HID Simulators.
func (h *hidPlugin) GetHIDDevices(ctx context.Context, req *passport.GetHIDDevicesRequest) (*passport.GetHIDDevicesResponse, error) {
	slog.Info("Probing for HID devices")

	if err := h.refreshSimulators(ctx); err != nil {
		return nil, fmt.Errorf("failed to probe for HID devices: %w", err)
	}

	var devices []*passport.HIDDevice
	for id := range h.simulators {
		devices = append(devices, &passport.HIDDevice{Id: id})
	}

	return &passport.GetHIDDevicesResponse{
		Devices: devices,
	}, nil
}

// InitHIDDevice initializes the specified HID device.
func (h *hidPlugin) InitHIDDevice(ctx context.Context, req *passport.InitHIDDeviceRequest) (*passport.InitHIDDeviceResponse, error) {
	slog.Info("Init HID device", "device", req.GetDeviceId())

	// Nothing to do here.
	return &passport.InitHIDDeviceResponse{}, nil
}

// CloseHIDDevice releases the specified HID device and releases any resources held open.
func (h *hidPlugin) CloseHIDDevice(ctx context.Context, req *passport.CloseHIDDeviceRequest) (*passport.CloseHIDDeviceResponse, error) {
	slog.Info("Close HID device", "device", req.GetDeviceId())

	hid, err := serial.Open(req.GetDeviceId(), mode)
	if err != nil {
		return nil, fmt.Errorf("failed to open simulator: %w", err)
	}
	defer hid.Close()

	if hid == nil {
		return nil, fmt.Errorf("failed to find simulator: %w", err)
	}
	if err := executeSimulator(hid, MouseRelease); err != nil {
		return nil, fmt.Errorf("failed to release mouse: %w", err)
	}
	if err := executeSimulator(hid, KeyboardRelease); err != nil {
		return nil, fmt.Errorf("failed to release keyboard: %w", err)
	}
	if err := executeSimulator(hid, MediaRelease); err != nil {
		return nil, fmt.Errorf("failed to release media key: %w", err)
	}
	return &passport.CloseHIDDeviceResponse{}, nil
}

// KeyboardAction performs the requested keyboard action.
func (h *hidPlugin) KeyboardAction(ctx context.Context, req *passport.KeyboardActionRequest) (*passport.KeyboardActionResponse, error) {
	slog.Info("KeyboardAction", "device", req.GetDeviceId(), "action", req.GetAction(), "keys", req.GetKeys())

	hid, err := serial.Open(req.GetDeviceId(), mode)
	if err != nil {
		return nil, fmt.Errorf("failed to open simulator: %w", err)
	}
	defer hid.Close()

	switch req.GetAction().(type) {
	case *passport.KeyboardActionRequest_PressAndRelease_:
		press := req.GetPressAndRelease()
		return keyPressAndRelease(ctx, hid, req.GetKeys(), press.GetDuration().AsDuration())
	default:
		return nil, fmt.Errorf("")
	}
}

// MouseAction performs the requested mouse action.
func (h *hidPlugin) MouseAction(ctx context.Context, req *passport.MouseActionRequest) (*passport.MouseActionResponse, error) {
	slog.Info("MouseAction", "device", req.GetDeviceId(), "action", req.GetAction())

	hid, err := serial.Open(req.GetDeviceId(), mode)
	if err != nil {
		return nil, fmt.Errorf("failed to open simulator: %w", err)
	}
	defer hid.Close()

	switch req.GetAction().(type) {
	case *passport.MouseActionRequest_PressAndRelease_:
		press := req.GetPressAndRelease()
		return mousePressAndRelease(ctx, hid, press.GetButton(), press.GetDuration().AsDuration())
	case *passport.MouseActionRequest_Scroll_:
		scroll := req.GetScroll()
		return mouseScroll(ctx, hid, scroll.GetDistance())
	case *passport.MouseActionRequest_Move_:
		move := req.GetMove()
		return mouseMove(ctx, hid, move.GetX(), move.GetY())
	default:
		return nil, fmt.Errorf("")
	}
}

func keyPressAndRelease(ctx context.Context, hid io.ReadWriter, keys []string, duration time.Duration) (*passport.KeyboardActionResponse, error) {
	if len(keys) == 0 {
		return nil, fmt.Errorf("keys to press empty")
	}
	if len(keys) > 6 {
		return nil, fmt.Errorf("HID device only supports a maximum of 6 keys at once, requested: %d", len(keys))
	}

	for _, key := range keys {
		if _, ok := KeyCodes[key]; !ok {
			return nil, fmt.Errorf("unknown key: %q", key)
		}
	}

	var keyCode []byte
	if len(keys) == 1 {
		// If we only have 1 key to press, then use the bytes directly
		keyCode = KeyCodes[keys[0]].KeyCodeBytes
	} else {
		// If we have multiple keys to press then we need to use this magic
		// method of building the bytes to send.
		keyCode = append(keyCode, KeyboardBase...)
		for index, key := range keys {
			keyCode[index+7] = byte(KeyCodes[key].KeyCodeInt)
		}
		keyCode = calculationVerificationCode(keyCode)
	}

	if err := executeSimulator(hid, keyCode); err != nil {
		return nil, fmt.Errorf("failed to press key code: %v: %v", keyCode, err)
	}

	if err := contextSleep(ctx, duration); err != nil {
		return nil, fmt.Errorf("failed to wait for key down sleep: %v", err)
	}

	if err := executeSimulator(hid, KeyboardRelease); err != nil {
		return nil, fmt.Errorf("failed to release all keyboard keys: %w", err)
	}

	// Small wait to prevent confusion pressing multiple keys in quick succession.
	if err := contextSleep(ctx, 200*time.Millisecond); err != nil {
		return nil, fmt.Errorf("failed to wait for sleep after keyboard release: %v", err)
	}

	if err := executeSimulator(hid, MediaRelease); err != nil {
		return nil, fmt.Errorf("failed to release media key: %w", err)
	}

	return &passport.KeyboardActionResponse{}, nil
}

// MousePressAndRelease is used to input mouse key, with the capability to set the duration.
func mousePressAndRelease(ctx context.Context, hid io.ReadWriter, button passport.MouseActionRequest_Button, duration time.Duration) (*passport.MouseActionResponse, error) {
	keyCode, ok := MouseKeyCodes[button]
	if !ok {
		return nil, fmt.Errorf("unknown mouse key: %s", button)
	}
	if err := executeSimulator(hid, keyCode.KeyCodeBytes); err != nil {
		return nil, fmt.Errorf("failed to press mouse key code: %q : %w", keyCode, err)
	}
	// GoBigSleepLint: press time.
	if err := contextSleep(ctx, duration); err != nil {
		return nil, fmt.Errorf("failed to wait for sleep after mouse press: %v", err)
	}
	if err := executeSimulator(hid, MouseRelease); err != nil {
		return nil, errors.Wrap(err, "failed to release mouse key")
	}
	return &passport.MouseActionResponse{}, nil
}

// MouseScroll is used to simulate mouse scrolling.
func mouseScroll(ctx context.Context, hid io.ReadWriter, times int32) (*passport.MouseActionResponse, error) {
	var kc []byte
	kc = append(kc, MouseBase...)
	for times != 0 {
		timesClamped := clampInt32(times, -127, 127)
		times -= timesClamped
		slog.Info("scrolling", "times", timesClamped)
		scrollTimes, err := convertingPositiveAndNegativeValues(timesClamped)
		if err != nil {
			return nil, errors.Wrap(err, "failed to converting times")
		}
		kc[9] = byte(scrollTimes)
		key := calculationVerificationCode(kc)
		if err := executeSimulator(hid, key); err != nil {
			return nil, errors.Wrapf(err, "failed to scroll mouse times:%v", times)
		}
	}
	return &passport.MouseActionResponse{}, nil
}

// mouseMove is used to simulate mouse move, allowing a maximum of 127 movements.
func mouseMove(ctx context.Context, hid io.ReadWriter, x, y int32) (*passport.MouseActionResponse, error) {
	var kc []byte
	kc = append(kc, MouseBase...)
	// Allion HID only allows up to a max of 127 pixels in a single movement.
	// so just do multiple movements.
	for x != 0 || y != 0 {
		xClamped := clampInt32(x, -127, 127)
		yClamped := clampInt32(y, -127, 127)
		x -= xClamped
		y -= yClamped
		slog.Info("mouse moving", "x", xClamped, "y", yClamped)
		xPixel, err := convertingPositiveAndNegativeValues(xClamped)
		if err != nil {
			return nil, errors.Wrap(err, "failed to converting x")
		}
		yPixel, err := convertingPositiveAndNegativeValues(yClamped)
		if err != nil {
			return nil, errors.Wrap(err, "failed to converting y")
		}

		kc[7] = byte(xPixel)
		kc[8] = byte(yPixel)
		key := calculationVerificationCode(kc)
		if err := executeSimulator(hid, key); err != nil {
			return nil, errors.Wrap(err, "failed to mouse move")
		}
	}
	return &passport.MouseActionResponse{}, nil
}

func (h *hidPlugin) refreshSimulators(ctx context.Context) error {
	ports, err := serial.GetPortsList()
	if err != nil {
		return errors.Wrap(err, "failed to get port list")
	}

	// Open the first serial port detected at 9600bps N81.
	// Print the list of detected ports.
	simulators := make(map[string]*hidSimulatorInfo)
	for _, port := range ports {
		// Skip non USB prefixed tty ports to avoid wasting time detecting.
		if !strings.Contains(port, "USB") {
			slog.Debug("Skipping port", "port", port)
			continue
		}

		usbPort, err := serial.Open(port, mode)
		if err != nil {
			slog.Error("Failed to open serial port", "port", port, "error", err)
			continue
		}
		defer usbPort.Close()

		slog.Debug("Checking port", "port", port)
		data, err := utils.ReadWriteSerialPort(ctx, usbPort, 3*time.Second /* timeout */, []byte(MediaRelease), []byte("\n"))
		if err != nil {
			slog.Error("Failed to read from serial port", "port", port, "error", err)
			continue
		}
		if bytes.Contains(data, checkData) {
			simulators[port] = &hidSimulatorInfo{}
			testing.ContextLogf(ctx, "Simulator: %s", port)
		}
	}

	// Log HID devices that we were not able to detect this time.
	for k := range h.simulators {
		if _, ok := simulators[k]; !ok {
			slog.Warn("unable to find previously detected HID", "HID id", k)
		}
	}

	h.simulators = simulators
	return nil

}

func executeSimulator(hid io.ReadWriter, keyCode []byte) error {
	if hid == nil {
		return errors.New("simulator is nil")
	}
	if _, err := hid.Write(keyCode); err != nil {
		return errors.Wrap(err, "failed to write keycode to simulator")
	}
	if _, err := hid.Write([]byte("\n")); err != nil {
		return errors.Wrap(err, "failed to write newline to simulator")
	}
	return nil
}

func convertingPositiveAndNegativeValues(value int32) (int32, error) {
	if value >= 0 && value < 128 {
		return value, nil
	} else if value > -128 && value < 0 {
		return value + 256, nil
	} else {
		return 0, errors.New("the value must range from 0 to 127 or from -1 to -127")
	}
}

func calculationVerificationCode(base []byte) []byte {
	sum := 0
	for _, b := range base {
		sum = sum + int(b)
	}
	sum = sum % 256
	base = append(base, byte(sum))
	return base
}

func clampInt32(val, min, max int32) int32 {
	return int32(math.Max(float64(min), math.Min(float64(max), float64(val))))
}

func contextSleep(ctx context.Context, duration time.Duration) error {
	timer := time.NewTimer(duration)
	defer timer.Stop()
	select {
	case <-ctx.Done():
		return ctx.Err()
	case <-timer.C:
		return nil
	}
}
