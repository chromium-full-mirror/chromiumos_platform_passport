// Copyright 2025 The ChromiumOS Authors
// Use of this source code is governed by a BSD-style license that can be
// found in the LICENSE file.

package allion

import (
	"bytes"
	"context"
	"fmt"
	"reflect"
	"testing"

	"go.chromium.org/chromiumos/config/go/test/lab/api/passport"
)

// Verify that result of multi-keys matches that output by Tast implementation:
//
//	src/platform/tast-tests/src/go.chromium.org/tast-tests/cros/remote/bundles/cros/wwcb/utils/simulator_util.go
func TestMultiKeyPress(t *testing.T) {
	tests := []struct {
		keys     []string
		expected []byte
	}{
		{
			keys:     []string{"LMeta", "F7"},
			expected: []byte{0x57, 0xab, 0x0, 0x2, 0x8, 0x0, 0x0, 0xe3, 0x40, 0x0, 0x0, 0x0, 0x0, 0x2f, 0xa},
		},
		{
			keys:     []string{"LMeta", "F6"},
			expected: []byte{0x57, 0xab, 0x0, 0x2, 0x8, 0x0, 0x0, 0xe3, 0x3f, 0x0, 0x0, 0x0, 0x0, 0x2e, 0xa},
		},
		{
			keys:     []string{"LMeta", "C"},
			expected: []byte{0x57, 0xab, 0x0, 0x2, 0x8, 0x0, 0x0, 0xe3, 0x6, 0x0, 0x0, 0x0, 0x0, 0xf5, 0xa},
		},
		{
			keys:     []string{"LControl", "LMeta", "S"},
			expected: []byte{0x57, 0xab, 0x0, 0x2, 0x8, 0x0, 0x0, 0xe0, 0xe3, 0x16, 0x0, 0x0, 0x0, 0xe5, 0xa},
		},
		{
			keys:     []string{"LControl", "LMeta", "F5"},
			expected: []byte{0x57, 0xab, 0x0, 0x2, 0x8, 0x0, 0x0, 0xe0, 0xe3, 0x3e, 0x0, 0x0, 0x0, 0xd, 0xa},
		},
		{
			keys:     []string{"LControl", "W"},
			expected: []byte{0x57, 0xab, 0x0, 0x2, 0x8, 0x0, 0x0, 0xe0, 0x1a, 0x0, 0x0, 0x0, 0x0, 0x6, 0xa},
		},
		{
			keys:     []string{"LMeta", "ArrowRight"},
			expected: []byte{0x57, 0xab, 0x0, 0x2, 0x8, 0x0, 0x0, 0xe3, 0x4f, 0x0, 0x0, 0x0, 0x0, 0x3e, 0xa},
		},
		{
			keys:     []string{"LMeta", "ArrowLeft"},
			expected: []byte{0x57, 0xab, 0x0, 0x2, 0x8, 0x0, 0x0, 0xe3, 0x50, 0x0, 0x0, 0x0, 0x0, 0x3f, 0xa},
		},
	}

	ctx := context.Background()
	for _, test := range tests {
		t.Run(fmt.Sprintf("%#v", test.keys), func(t *testing.T) {
			var hid bytes.Buffer
			if _, err := keyPressAndRelease(ctx, &hid, test.keys, 0 /*duration*/); err != nil {
				t.Errorf("keyPressAndRelease: failed to press key: %v", err)
			}
			bytesGot, err := hid.ReadBytes('\n')
			if err != nil {
				t.Errorf("keyPressAndRelease: failed to read stream: %v", err)
			}
			if !reflect.DeepEqual(bytesGot, test.expected) {
				t.Errorf("keyPressAndRelease does not match, got %#v, want %#v", bytesGot, test.expected)
			}
		})
	}
}

func TestMouseClick(t *testing.T) {
	tests := []struct {
		button   passport.MouseActionRequest_Button
		expected []byte
	}{
		{
			button:   passport.MouseActionRequest_LEFT,
			expected: []uint8{0x57, 0xab, 0x0, 0x5, 0x5, 0x1, 0x1, 0x0, 0x0, 0x0, 0xe, 0xa},
		},
		{
			button:   passport.MouseActionRequest_RIGHT,
			expected: []uint8{0x57, 0xab, 0x0, 0x5, 0x5, 0x1, 0x2, 0x0, 0x0, 0x0, 0xf, 0xa},
		},
		{
			button:   passport.MouseActionRequest_MIDDLE,
			expected: []uint8{0x57, 0xab, 0x0, 0x5, 0x5, 0x1, 0x4, 0x0, 0x0, 0x0, 0x11, 0xa},
		},
		{
			button:   passport.MouseActionRequest_FORWARD,
			expected: []uint8{0x57, 0xab, 0x0, 0x5, 0x5, 0x1, 0x10, 0x0, 0x0, 0x0, 0x1d, 0xa},
		},
		{
			button:   passport.MouseActionRequest_BACK,
			expected: []uint8{0x57, 0xab, 0x0, 0x5, 0x5, 0x1, 0x8, 0x0, 0x0, 0x0, 0x15, 0xa},
		},
	}

	ctx := context.Background()
	for _, test := range tests {
		t.Run(fmt.Sprintf("%v", test.button), func(t *testing.T) {
			var hid bytes.Buffer
			if _, err := mousePressAndRelease(ctx, &hid, test.button, 0 /*duration*/); err != nil {
				t.Errorf("mousePressAndRelease: failed to press key: %v", err)
			}
			bytesGot, err := hid.ReadBytes('\n')
			if err != nil {
				t.Errorf("mousePressAndRelease: failed to read stream: %v", err)
			}
			if !reflect.DeepEqual(bytesGot, test.expected) {
				t.Errorf("mousePressAndRelease does not match, got %#v, want %#v", bytesGot, test.expected)
			}
		})
	}
}

// func mouseScroll(ctx context.Context, hid io.ReadWriter, times int32) (*passport.MouseActionResponse, error) {
func TestMouseScroll(t *testing.T) {
	tests := []struct {
		distance int32
		expected []byte
	}{
		{
			distance: -50,
			expected: []uint8{0x57, 0xab, 0x0, 0x5, 0x5, 0x1, 0x0, 0x0, 0x0, 0xce, 0xdb, 0xa},
		},
		{
			distance: 0,
			expected: nil,
		},
		{
			distance: 50,
			expected: []uint8{0x57, 0xab, 0x0, 0x5, 0x5, 0x1, 0x0, 0x0, 0x0, 0x32, 0x3f, 0xa},
		},
	}

	ctx := context.Background()
	for _, test := range tests {
		t.Run(fmt.Sprintf("%v", test.distance), func(t *testing.T) {
			var hid bytes.Buffer
			if _, err := mouseScroll(ctx, &hid, test.distance); err != nil {
				t.Errorf("mouseScroll: failed to press key: %v", err)
			}
			// Ignore error since 0 distance will return EOF.
			bytesGot, _ := hid.ReadBytes('\n')
			if !reflect.DeepEqual(bytesGot, test.expected) {
				t.Errorf("mouseScroll does not match, got %#v, want %#v", bytesGot, test.expected)
			}
		})
	}
}

func TestMouseMove(t *testing.T) {
	tests := []struct {
		x        int32
		y        int32
		expected []byte
	}{
		{
			x:        -50,
			y:        -50,
			expected: []uint8{0x57, 0xab, 0x0, 0x5, 0x5, 0x1, 0x0, 0xce, 0xce, 0x0, 0xa9, 0xa},
		},
		{
			x:        0,
			y:        0,
			expected: nil,
		},
		{
			x:        50,
			y:        50,
			expected: []uint8{0x57, 0xab, 0x0, 0x5, 0x5, 0x1, 0x0, 0x32, 0x32, 0x0, 0x71, 0xa},
		},
		{
			x:        500,
			y:        500,
			expected: []uint8{0x57, 0xab, 0x0, 0x5, 0x5, 0x1, 0x0, 0x7f, 0x7f, 0x0, 0xb, 0xa},
		},
		{
			x:        -500,
			y:        -500,
			expected: []uint8{0x57, 0xab, 0x0, 0x5, 0x5, 0x1, 0x0, 0x81, 0x81, 0x0, 0xf, 0xa},
		},
		{
			x:        0,
			y:        -500,
			expected: []uint8{0x57, 0xab, 0x0, 0x5, 0x5, 0x1, 0x0, 0x0, 0x81, 0x0, 0x8e, 0xa},
		},
		{
			x:        500,
			y:        0,
			expected: []uint8{0x57, 0xab, 0x0, 0x5, 0x5, 0x1, 0x0, 0x7f, 0x0, 0x0, 0x8c, 0xa},
		},
	}

	ctx := context.Background()
	for _, test := range tests {
		t.Run(fmt.Sprintf("%v, %v", test.x, test.y), func(t *testing.T) {
			var hid bytes.Buffer
			if _, err := mouseMove(ctx, &hid, test.x, test.y); err != nil {
				t.Errorf("mouseMove: failed to press key: %v", err)
			}
			bytesGot, _ := hid.ReadBytes('\n')
			if !reflect.DeepEqual(bytesGot, test.expected) {
				t.Errorf("mouseMove does not match, got %#v, want %#v", bytesGot, test.expected)
			}
		})
	}
}
