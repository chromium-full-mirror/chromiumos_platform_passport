// Copyright 2024 The ChromiumOS Authors
// Use of this source code is governed by a BSD-style license that can be
// found in the LICENSE file.

package server

import (
	"context"
	"fmt"
	"testing"

	"go.chromium.org/chromiumos/config/go/test/lab/api/passport"
	"go.chromiumos.org/chromiumos/platform/passport/port"
)

type getSwitchFunc func(context.Context, *passport.GetSwitchesRequest) (*passport.GetSwitchesResponse, error)
type configureSwitchFunc func(context.Context, *passport.ConfigureSwitchPortRequest) (*passport.ConfigureSwitchPortResponse, error)
type resetAllSwitchesFunc func(context.Context, *passport.ResetAllSwitchesRequest) (*passport.ResetAllSwitchesResponse, error)

// mockSwitchPlugin is mock switch plugin.
type mockSwitchPlugin struct {
	port.PortManager
	getSwitches         getSwitchFunc
	configureSwitchPort configureSwitchFunc
	resetAllSwitches    resetAllSwitchesFunc
}

func (s *mockSwitchPlugin) Init(ctx context.Context) error {
	return nil
}

func (s *mockSwitchPlugin) GetSwitches(ctx context.Context, req *passport.GetSwitchesRequest) (*passport.GetSwitchesResponse, error) {
	if s.getSwitches != nil {
		return s.getSwitches(ctx, req)
	}
	return &passport.GetSwitchesResponse{}, nil
}

func (s *mockSwitchPlugin) ConfigureSwitchPort(ctx context.Context, req *passport.ConfigureSwitchPortRequest) (*passport.ConfigureSwitchPortResponse, error) {
	if s.configureSwitchPort != nil {
		return s.configureSwitchPort(ctx, req)
	}
	return &passport.ConfigureSwitchPortResponse{}, nil
}

func (s *mockSwitchPlugin) ResetAllSwitches(ctx context.Context, req *passport.ResetAllSwitchesRequest) (*passport.ResetAllSwitchesResponse, error) {
	if s.resetAllSwitches != nil {
		return s.resetAllSwitches(ctx, req)
	}
	return &passport.ResetAllSwitchesResponse{}, nil
}

func (s *mockSwitchPlugin) Name() string {
	return "mock_switch_plugin"
}

func replyWithSwitches(switches ...string) getSwitchFunc {
	resp := &passport.GetSwitchesResponse{}
	for _, sw := range switches {
		resp.Switches = append(resp.Switches, &passport.SwitchFixture{Id: sw})
	}

	return func(context.Context, *passport.GetSwitchesRequest) (*passport.GetSwitchesResponse, error) {
		return resp, nil
	}
}

// TestGetSwitches tests GetSwitches API on switchServiceServicer.
func TestGetSwitches(t *testing.T) {
	tests := []struct {
		name     string
		plugins  []SwitchPlugin
		expected []string
		wantErr  bool
	}{
		{
			name: "Empty",
		},
		{
			name: "HappyPath",
			plugins: []SwitchPlugin{
				&mockSwitchPlugin{
					getSwitches: replyWithSwitches("switch1", "switch2", "switch3"),
				},
				&mockSwitchPlugin{
					getSwitches: replyWithSwitches("switch4"),
				},
				&mockSwitchPlugin{
					getSwitches: replyWithSwitches("switch5"),
				},
				&mockSwitchPlugin{},
			},
			expected: []string{"switch1", "switch2", "switch3", "switch4", "switch5"},
		},
		{
			name: "NoSwitches",
			plugins: []SwitchPlugin{
				&mockSwitchPlugin{},
				&mockSwitchPlugin{},
			},
			expected: nil,
		},
		{
			name: "DuplicateName",
			plugins: []SwitchPlugin{
				&mockSwitchPlugin{
					getSwitches: replyWithSwitches("switch1"),
				},
				&mockSwitchPlugin{
					getSwitches: replyWithSwitches("switch1"),
				},
			},
			wantErr: true,
		},
		{
			name: "EmptyName",
			plugins: []SwitchPlugin{
				&mockSwitchPlugin{
					getSwitches: replyWithSwitches("switch1", ""),
				},
			},
			wantErr: true,
		},
		{
			name: "PluginError",
			plugins: []SwitchPlugin{
				&mockSwitchPlugin{
					getSwitches: replyWithSwitches("switch1"),
				},
				&mockSwitchPlugin{
					getSwitches: func(context.Context, *passport.GetSwitchesRequest) (*passport.GetSwitchesResponse, error) {
						return nil, fmt.Errorf("Test Error")
					},
				},
			},
			wantErr: true,
		},
	}

	for _, test := range tests {
		t.Run(test.name, func(t *testing.T) {
			expectedSwitches := make(map[string]bool)
			service := &switchServiceServer{
				switchMap: make(map[string]SwitchPlugin),
				plugins:   test.plugins,
			}
			for _, sw := range test.expected {
				expectedSwitches[sw] = true
			}

			resp, err := service.GetSwitches(context.Background(), &passport.GetSwitchesRequest{})
			for _, sw := range resp.GetSwitches() {
				if !expectedSwitches[sw.GetId()] {
					t.Errorf("unexpected switch: %q, want %v, got %v", sw.GetId(), test.expected, resp.GetSwitches())
				}
				delete(expectedSwitches, sw.GetId())
			}
			if (err != nil) != test.wantErr {
				t.Errorf("error = %v, wantErr %v", err, test.wantErr)
			}
		})
	}
}

// TestConfigureSwitch tests ConfigureSwitchPort API on switchServiceServicer.
func TestConfigureSwitch(t *testing.T) {
	tests := []struct {
		name    string
		plugins []SwitchPlugin
		request *passport.ConfigureSwitchPortRequest
		wantErr bool
	}{
		{
			name: "Empty",
			request: &passport.ConfigureSwitchPortRequest{
				SwitchId: "switch4",
				State:    passport.SwitchPortState_SWITCH_PORT_DISABLED,
			},
			wantErr: true,
		},
		{
			name: "HappyPath",
			plugins: []SwitchPlugin{
				&mockSwitchPlugin{
					getSwitches: replyWithSwitches("switch1", "switch2", "switch3"),
				},
				&mockSwitchPlugin{
					getSwitches: replyWithSwitches("switch4"),
				},
				&mockSwitchPlugin{
					getSwitches: replyWithSwitches("switch5"),
				},
				&mockSwitchPlugin{},
			},
			request: &passport.ConfigureSwitchPortRequest{
				SwitchId: "switch4",
				State:    passport.SwitchPortState_SWITCH_PORT_DISABLED,
			},
		},
		{
			name: "UnknownSwitch",
			plugins: []SwitchPlugin{
				&mockSwitchPlugin{
					getSwitches: replyWithSwitches("switch1", "switch2", "switch3"),
				},
			},
			request: &passport.ConfigureSwitchPortRequest{
				SwitchId: "switch4",
				State:    passport.SwitchPortState_SWITCH_PORT_DISABLED,
			},
			wantErr: true,
		},
		{
			name: "PluginError",
			plugins: []SwitchPlugin{
				&mockSwitchPlugin{
					getSwitches: replyWithSwitches("switch1"),
				},
				&mockSwitchPlugin{
					configureSwitchPort: func(context.Context, *passport.ConfigureSwitchPortRequest) (*passport.ConfigureSwitchPortResponse, error) {
						return nil, fmt.Errorf("Test Error")
					},
				},
			},
			wantErr: true,
		},
	}
	for _, test := range tests {
		t.Run(test.name, func(t *testing.T) {
			service := &switchServiceServer{
				switchMap: make(map[string]SwitchPlugin),
				plugins:   test.plugins,
			}
			_, err := service.ConfigureSwitchPort(context.Background(), test.request)
			if (err != nil) != test.wantErr {
				t.Errorf("error = %v, wantErr %v", err, test.wantErr)
			}
		})
	}
}

// TestResetAllSwitches tests ResetAllSwitches API on switchServiceServicer.
func TestResetAllSwitches(t *testing.T) {
	tests := []struct {
		name    string
		plugins []SwitchPlugin
		wantErr bool
	}{
		{
			name: "Empty",
		},
		{
			name: "HappyPath",
			plugins: []SwitchPlugin{
				&mockSwitchPlugin{},
			},
		},
		{
			name: "PluginError",
			plugins: []SwitchPlugin{
				&mockSwitchPlugin{},
				&mockSwitchPlugin{
					resetAllSwitches: func(context.Context, *passport.ResetAllSwitchesRequest) (*passport.ResetAllSwitchesResponse, error) {
						return nil, fmt.Errorf("Test Error")
					},
				},
			},
			wantErr: true,
		},
	}
	for _, test := range tests {
		t.Run(test.name, func(t *testing.T) {
			service := &switchServiceServer{
				switchMap: make(map[string]SwitchPlugin),
				plugins:   test.plugins,
			}
			_, err := service.ResetAllSwitches(context.Background(), &passport.ResetAllSwitchesRequest{})
			if (err != nil) != test.wantErr {
				t.Errorf("error = %v, wantErr %v", err, test.wantErr)
			}
		})
	}
}
