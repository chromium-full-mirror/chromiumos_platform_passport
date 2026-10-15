// Copyright 2026 The ChromiumOS Authors
// Use of this source code is governed by a BSD-style license that can be
// found in the LICENSE file.

package server

import (
	"context"
	"errors"
	"testing"

	"go.chromium.org/chromiumos/config/go/test/lab/api/passport"
	"google.golang.org/grpc/codes"
	"google.golang.org/grpc/status"
)

type mockVideoTesterPlugin struct {
	passport.UnimplementedVideoTesterServiceServer
	name            string
	initErr         error
	getTesters      func(context.Context, *passport.GetVideoTestersRequest) (*passport.GetVideoTestersResponse, error)
	openTester      func(context.Context, *passport.OpenVideoTesterRequest) (*passport.OpenVideoTesterResponse, error)
	powerCycleCalls int
}

func (m *mockVideoTesterPlugin) Name() string {
	if m.name != "" {
		return m.name
	}
	return "mock_video_tester_plugin"
}

func (m *mockVideoTesterPlugin) Init() error {
	return m.initErr
}

func (m *mockVideoTesterPlugin) GetVideoTesters(
	ctx context.Context,
	req *passport.GetVideoTestersRequest,
) (*passport.GetVideoTestersResponse, error) {
	if m.getTesters != nil {
		return m.getTesters(ctx, req)
	}
	return &passport.GetVideoTestersResponse{}, nil
}

func (m *mockVideoTesterPlugin) OpenVideoTester(
	ctx context.Context,
	req *passport.OpenVideoTesterRequest,
) (*passport.OpenVideoTesterResponse, error) {
	if m.openTester != nil {
		return m.openTester(ctx, req)
	}
	return &passport.OpenVideoTesterResponse{Success: true}, nil
}

func (m *mockVideoTesterPlugin) PowerCycle(
	ctx context.Context,
	req *passport.PowerCycleRequest,
) (*passport.PowerCycleResponse, error) {
	m.powerCycleCalls++
	return &passport.PowerCycleResponse{}, nil
}

func replyWithVideoTesters(ids ...string) func(context.Context, *passport.GetVideoTestersRequest) (*passport.GetVideoTestersResponse, error) {
	return func(context.Context, *passport.GetVideoTestersRequest) (*passport.GetVideoTestersResponse, error) {
		resp := &passport.GetVideoTestersResponse{}
		for _, id := range ids {
			resp.Testers = append(resp.Testers, &passport.VideoTester{
				Id:   id,
				Name: "UCD-500",
			})
		}
		return resp, nil
	}
}

func TestNewVideoTesterServiceServerDoesNotMutateGlobalSlice(t *testing.T) {
	orig := videoTesterPlugins
	defer func() {
		videoTesterPlugins = orig
	}()

	p1 := &mockVideoTesterPlugin{name: "p1", initErr: errors.New("init failed")}
	p2 := &mockVideoTesterPlugin{name: "p2"}
	videoTesterPlugins = []VideoTesterPlugin{p1, p2}

	srvIface, err := newVideoTesterServiceServer(context.Background())
	if err != nil {
		t.Fatalf("newVideoTesterServiceServer returned unexpected error: %v", err)
	}
	if len(videoTesterPlugins) != 2 || videoTesterPlugins[0] != p1 || videoTesterPlugins[1] != p2 {
		t.Fatalf("videoTesterPlugins global slice was mutated: got %v", videoTesterPlugins)
	}

	srv := srvIface.(*videoTesterServiceServer)
	if len(srv.plugins) != 1 || srv.plugins[0] != p2 {
		t.Fatalf("expected only p2 in srv.plugins, got %v", srv.plugins)
	}
}

func TestGetTesterLazyDiscoveryOnCacheMiss(t *testing.T) {
	plugin := &mockVideoTesterPlugin{
		name:       "ucd500",
		getTesters: replyWithVideoTesters("2236C961"),
	}
	service := &videoTesterServiceServer{
		testerMap: make(map[string]VideoTesterPlugin),
		plugins:   []VideoTesterPlugin{plugin},
	}

	// OpenVideoTester before GetVideoTesters was ever called should lazily populate testerMap.
	resp, err := service.OpenVideoTester(
		context.Background(),
		&passport.OpenVideoTesterRequest{Id: "2236C961"},
	)
	if err != nil {
		t.Fatalf("OpenVideoTester on cold cache failed: %v", err)
	}
	if !resp.GetSuccess() {
		t.Fatalf("expected OpenVideoTester response success=true")
	}

	// Unknown ID should return codes.NotFound with well-formed message.
	_, err = service.SetRoleVideoTester(
		context.Background(),
		&passport.SetRoleRequest{Id: "UNKNOWN"},
	)
	if status.Code(err) != codes.NotFound {
		t.Fatalf("expected NotFound for unknown ID, got %v", err)
	}
}

func TestRefreshTestersPreservesKnownMappingsAcrossUSBReenumeration(t *testing.T) {
	visible := []string{"2236C961"}
	plugin := &mockVideoTesterPlugin{
		name: "ucd500",
		getTesters: func(context.Context, *passport.GetVideoTestersRequest) (*passport.GetVideoTestersResponse, error) {
			resp := &passport.GetVideoTestersResponse{}
			for _, id := range visible {
				resp.Testers = append(resp.Testers, &passport.VideoTester{Id: id, Name: "UCD-500"})
			}
			return resp, nil
		},
	}
	service := &videoTesterServiceServer{
		testerMap: make(map[string]VideoTesterPlugin),
		plugins:   []VideoTesterPlugin{plugin},
	}

	if _, err := service.GetVideoTesters(context.Background(), &passport.GetVideoTestersRequest{}); err != nil {
		t.Fatalf("initial GetVideoTesters failed: %v", err)
	}

	// Simulate temporary USB disappearance during re-enumeration.
	visible = nil
	if _, err := service.GetVideoTesters(context.Background(), &passport.GetVideoTestersRequest{}); err != nil {
		t.Fatalf("second GetVideoTesters failed: %v", err)
	}

	if _, err := service.PowerCycle(context.Background(), &passport.PowerCycleRequest{Id: "2236C961"}); err != nil {
		t.Fatalf("PowerCycle after transient disappearance failed: %v", err)
	}
	if plugin.powerCycleCalls != 1 {
		t.Fatalf("expected 1 PowerCycle call, got %d", plugin.powerCycleCalls)
	}
}

func TestGetTesterDeadBridgeDoesNotHideErrorOrBlockHealthyPlugin(t *testing.T) {
	deadUcd422 := &mockVideoTesterPlugin{
		name: "ucd422",
		getTesters: func(context.Context, *passport.GetVideoTestersRequest) (*passport.GetVideoTestersResponse, error) {
			return nil, errors.New("ucd422 bridge connection refused")
		},
	}
	healthyUcd500 := &mockVideoTesterPlugin{
		name:       "ucd500",
		getTesters: replyWithVideoTesters("2541C665"),
	}
	service := &videoTesterServiceServer{
		testerMap: make(map[string]VideoTesterPlugin),
		plugins:   []VideoTesterPlugin{deadUcd422, healthyUcd500},
	}

	// Cold lookup for UCD-500 must succeed even when earlier UCD-422 plugin fails.
	resp, err := service.OpenVideoTester(
		context.Background(),
		&passport.OpenVideoTesterRequest{Id: "2541C665"},
	)
	if err != nil {
		t.Fatalf("OpenVideoTester for healthy UCD-500 failed when UCD-422 bridge was dead: %v", err)
	}
	if !resp.GetSuccess() {
		t.Fatalf("expected OpenVideoTester response success=true")
	}

	// Cold lookup for an unmapped ID when a plugin bridge is dead must return Unavailable, not NotFound.
	_, err = service.OpenVideoTester(
		context.Background(),
		&passport.OpenVideoTesterRequest{Id: "DEAD_422_SERIAL"},
	)
	if status.Code(err) != codes.Unavailable {
		t.Fatalf("expected Unavailable when plugin refresh fails on cold lookup, got %v (code=%v)", err, status.Code(err))
	}
}
