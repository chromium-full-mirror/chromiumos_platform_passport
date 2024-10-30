// Copyright 2024 The ChromiumOS Authors
// Use of this source code is governed by a BSD-style license that can be
// found in the LICENSE file.

package allion

import (
	"testing"
)

func TestParseAllionSwitch(t *testing.T) {
	tests := []struct {
		name     string
		text     string
		isAllion bool
		model    string
		id       string
	}{
		{
			name:     "AUS19129",
			text:     "AUS19129_A00_01_2206201400",
			isAllion: true,
			model:    "AUS19129",
			id:       "1912901",
		},
		{
			name:     "AHS20079",
			text:     "AHS20079_A00_01_2206201400",
			isAllion: true,
			model:    "AHS20079",
			id:       "2007901",
		},
		{
			name:     "AUS20019",
			text:     "AUS20019_A00_01_2206201400",
			isAllion: true,
			model:    "AUS20019",
			id:       "2001901",
		},
		{
			name:     "ADT21090",
			text:     "ADT21090_A00_01_2206201400",
			isAllion: true,
			model:    "ADT21090",
			id:       "2109001",
		},
		{
			name:     "XXRJ45SW",
			text:     "XXRJ45SW_A00_01_2206201400",
			isAllion: true,
			model:    "XXRJ45SW",
			id:       "J45SW01",
		},
		{
			name: "XXXXXXXX",
			text: "XXXXXXXX_XXX_XX_XXXXXXXXXX",
		},
		{
			name: "Empty",
			text: "",
		},
	}

	for _, test := range tests {
		t.Run(test.name, func(t *testing.T) {
			isAllion, info := isAllionDevice(test.text)
			if isAllion != test.isAllion {
				t.Errorf("isAllion does not match, got %v, want %v", isAllion, test.isAllion)
			}
			if isAllion && info.model != test.model {
				t.Errorf("model does not match, got %v, want %v", info.model, test.model)
			}
			if isAllion && info.uid != test.id {
				t.Errorf("id does not match, got %v, want %v", info.uid, test.id)
			}
		})
	}
}
