// Copyright 2024 The ChromiumOS Authors
// Use of this source code is governed by a BSD-style license that can be
// found in the LICENSE file.

package server

import (
	"context"
	"fmt"
	"log/slog"
	"strings"

	"go.chromium.org/chromiumos/config/go/test/lab/api/passport"
)

// switchServiceServer implements api/passport.SwitchServiceServer and wraps individual
// switch plugins.
type switchServiceServer struct {
	// Maps individual switch IDs to their controlling plugin.
	switchMap map[string]SwitchPlugin
	// All registered plugins.
	plugins []SwitchPlugin
}

func newSwitchServiceServer(ctx context.Context) (passport.SwitchServiceServer, error) {
	s := &switchServiceServer{
		switchMap: make(map[string]SwitchPlugin),
		plugins:   switchPlugins,
	}

	for _, plugin := range s.plugins {
		if err := plugin.Init(ctx); err != nil {
			return nil, fmt.Errorf("failed to initialize plugin: %q: %w", plugin.Name(), err)
		}
	}

	return s, nil
}

// GetSwitches probes all connected switches to the host device.
func (s *switchServiceServer) GetSwitches(ctx context.Context, req *passport.GetSwitchesRequest) (*passport.GetSwitchesResponse, error) {
	slog.Info("Received passport.GetSwitchesRequest", "req", req)
	switches, err := s.refreshSwitches(ctx, req)
	if err != nil {
		return nil, fmt.Errorf("failed to refresh switches: %w", err)
	}

	return &passport.GetSwitchesResponse{
		Switches: switches,
	}, nil
}

// ResetAllSwitches re-initializes all found switches and sets them to the "disabled" state.
func (s *switchServiceServer) ResetAllSwitches(ctx context.Context, req *passport.ResetAllSwitchesRequest) (*passport.ResetAllSwitchesResponse, error) {
	slog.Info("Received passport.ResetAllSwitchesRequest", "req", req)
	for _, plugin := range s.plugins {
		slog.Info("Calling reset switches", "plugin", plugin.Name())
		if _, err := plugin.ResetAllSwitches(ctx, req); err != nil {
			return nil, fmt.Errorf("failed to reset switches: %w", err)
		}
	}
	return &passport.ResetAllSwitchesResponse{}, nil
}

// ConfigureSwitchPort configures a single port on a switch.
func (s *switchServiceServer) ConfigureSwitchPort(ctx context.Context, req *passport.ConfigureSwitchPortRequest) (*passport.ConfigureSwitchPortResponse, error) {
	slog.Info("Received passport.ConfigureSwitchPortRequest", "req", req)
	plugin, err := s.pluginForSwitch(ctx, req.GetSwitchId())
	if err != nil {
		plugin, err = s.pluginForSwitch(ctx, strings.ToUpper(req.GetSwitchId()))
		if err != nil {
			return nil, fmt.Errorf("failed to fetch plugin for switch: %w", err)
		}
	}
	slog.Info("Configuring switch", "id", req.GetSwitchId(), "plugin", plugin.Name())

	if _, err := plugin.ConfigureSwitchPort(ctx, req); err != nil {
		return nil, fmt.Errorf("failed to configure switch: %w", err)
	}
	return &passport.ConfigureSwitchPortResponse{}, nil
}

// pluginForSwitch gets the plugin that controls a specific switch.
func (s *switchServiceServer) pluginForSwitch(ctx context.Context, id string) (SwitchPlugin, error) {
	// Check if we've cached the plugin for this switch ID.
	if c, ok := s.switchMap[id]; ok {
		return c, nil
	}

	// Unknown which plugin controls this switch -> refresh.
	// Note we don't really support very dynamic switches e.g. connecting and disconnecting, changing USB ports, etc..
	// We expect that the test will call GetSwitches at the beginning of the test and the switches will be
	// pretty much static throughout the test. Implementing some sort of switch add/remove/change callback
	// could be done but is probably overkill.
	if _, err := s.refreshSwitches(ctx, &passport.GetSwitchesRequest{}); err != nil {
		return nil, fmt.Errorf("failed to refresh switches: %w", err)
	}

	if c, ok := s.switchMap[id]; ok {
		return c, nil
	}

	return nil, fmt.Errorf("unknown switch with ID: %q", id)
}

// refreshSwitches refreshes the cached switches by probing the plugins.
func (s *switchServiceServer) refreshSwitches(ctx context.Context, req *passport.GetSwitchesRequest) ([]*passport.SwitchFixture, error) {
	var switches []*passport.SwitchFixture
	switchMap := make(map[string]SwitchPlugin)
	for _, plugin := range s.plugins {
		// Ignore all ports being used by other plugins this actually sets all
		// ports being used by all plugins but the port manager knows to not
		//  ignore ports that are currently in use.  This optimization mean
		// that if a switch is unplugged and a new one of different type is
		// plugged in and ends up with port as the previously it could
		// take 2 rounds of refresh to detect it.  This is unlikely in a
		// real world situation so not accounting for this corner case.
		ignoreList := []string{}
		for _, plugin := range s.plugins {
			ignoreList = append(ignoreList, plugin.GetUsedPorts()...)
		}
		plugin.UpdateIgnoredPorts(ignoreList)
		resp, err := plugin.GetSwitches(ctx, req)
		if err != nil {
			return nil, fmt.Errorf("failed to get switches for plugin %q: %w", plugin.Name(), err)
		}

		for _, sw := range resp.GetSwitches() {
			id := sw.GetId()
			if id == "" {
				return nil, fmt.Errorf("received empty switch ID, plugin: %q", plugin.Name())
			}
			if pOld, ok := switchMap[id]; ok {
				return nil, fmt.Errorf("received duplicate switch ID: %q, plugin1 %q, plugin2 %q", id, pOld.Name(), plugin.Name())
			}
			switches = append(switches, sw)
			switchMap[id] = plugin
		}
	}

	slog.Info("Found switches", "switches", switches)
	s.switchMap = switchMap
	return switches, nil
}
