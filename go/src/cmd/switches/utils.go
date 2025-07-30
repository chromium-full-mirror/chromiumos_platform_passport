// Copyright 2025 The ChromiumOS Authors
// Use of this source code is governed by a BSD-style license that can be
// found in the LICENSE file.

package switches

import (
	"context"
	"fmt"
	"log/slog"

	"go.chromium.org/chromiumos/config/go/test/lab/api/passport"
)

func getSwitches(ctx context.Context, client passport.SwitchServiceClient) ([]string, error) {
	resp1, err := client.GetSwitches(ctx, &passport.GetSwitchesRequest{})
	if err != nil {
		return nil, err
	}
	var res []string
	for _, sw := range resp1.GetSwitches() {
		res = append(res, sw.GetId())
	}
	slog.Info("Detected switches", "switches", res)
	return res, nil
}

func configureSwitches(ctx context.Context, client passport.SwitchServiceClient, switches []string, switchPort string, state passport.SwitchPortState) error {
	for _, id := range switches {
		slog.Info("Configuring switch", "switch id", id, "state", state)
		req := &passport.ConfigureSwitchPortRequest{
			SwitchId: id,
			State:    state,
			PortId:   switchPort,
		}
		if _, err := client.ConfigureSwitchPort(ctx, req); err != nil {
			return fmt.Errorf("Failed to configure switch: %q, %v", id, err)
		}
	}
	return nil
}
