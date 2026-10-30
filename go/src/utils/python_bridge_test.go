// Copyright 2026 The ChromiumOS Authors
// Use of this source code is governed by a BSD-style license that can be
// found in the LICENSE file.

package utils

import (
	"os"
	"path/filepath"
	"strings"
	"testing"
	"time"
)

// TestBridgeRelaunchedOnSamePort checks that a bridge that keeps dying is relaunched on its
// original port until the restart limit is hit.
func TestBridgeRelaunchedOnSamePort(t *testing.T) {
	dir := t.TempDir()
	launches := filepath.Join(dir, "launches")
	bridge := filepath.Join(dir, "bridge.sh")
	// Bind "port" 0 as 45678, record the requested port, then die immediately.
	script := `#!/bin/sh
port=$2; [ "$port" = 0 ] && port=45678
echo "$2" >> ` + launches + `
echo PORT_BOUND:$port
exit 1
`
	if err := os.WriteFile(bridge, []byte(script), 0o755); err != nil {
		t.Fatal(err)
	}

	port, _, err := LaunchPythonBridgefAndGetPort(bridge, 0, "")
	if err != nil || port != 45678 {
		t.Fatalf("LaunchPythonBridgefAndGetPort() = %d, %v; want 45678, nil", port, err)
	}

	want := "0\n" + strings.Repeat("45678\n", maxBridgeRestarts)
	var got string
	for deadline := time.Now().Add(10 * time.Second); time.Now().Before(deadline); time.Sleep(50 * time.Millisecond) {
		b, _ := os.ReadFile(launches)
		if got = string(b); got == want {
			time.Sleep(200 * time.Millisecond) // Make sure it stops at the limit.
			if b, _ = os.ReadFile(launches); string(b) == want {
				return
			}
		}
	}
	t.Fatalf("launch ports = %q; want %q", got, want)
}
