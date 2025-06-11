// Copyright 2024 The ChromiumOS Authors
// Use of this source code is governed by a BSD-style license that can be
// found in the LICENSE file.

package main

import (
	// Imported packages that register plugins.
	_ "go.chromiumos.org/chromiumos/platform/passport/acroname"
	_ "go.chromiumos.org/chromiumos/platform/passport/allion"
	_ "go.chromiumos.org/chromiumos/platform/passport/generic"
	_ "go.chromiumos.org/chromiumos/platform/passport/mcci"
	_ "go.chromiumos.org/chromiumos/platform/passport/unigraf/ucd422"
	_ "go.chromiumos.org/chromiumos/platform/passport/unigraf/ucd500"
	_ "go.chromiumos.org/chromiumos/platform/passport/unigraf/utc274"
)
