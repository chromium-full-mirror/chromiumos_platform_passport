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
		version  int64
		commands commandMap
	}{
		{
			name:     "AUS19129",
			text:     "AUS19129_A00_01_2206201400",
			isAllion: true,
			model:    "AUS19129",
			id:       "1912901",
			version:  2206201400,
			commands: commandMap{SwitchDisabled: "0", SwitchFlip: "2"},
		},
		{
			name:     "AHS20079",
			text:     "AHS20079_A00_01_2401231631",
			isAllion: true,
			model:    "AHS20079",
			id:       "2007901",
			version:  2401231631,
			commands: commandMap{SwitchDisabled: "2"},
		},
		{
			name:     "AUS20019_2401291730",
			text:     "AUS20019_D00_01_2401291730",
			isAllion: true,
			model:    "AUS20019",
			id:       "2001901",
			version:  2401291730,
			commands: commandMap{SwitchDisabled: "2"},
		},
		{
			name:     "AUS20019_2510269999",
			text:     "AUS20019_D00_01_2510269999",
			isAllion: true,
			model:    "AUS20019",
			id:       "2001901",
			version:  2510269999,
			commands: commandMap{SwitchDisabled: "2"},
		},
		{
			name:     "AUS20019_2510270000",
			text:     "AUS20019_D00_01_2510270000",
			isAllion: true,
			model:    "AUS20019",
			id:       "2001901",
			version:  2510270000,
			commands: commandMap{SwitchDisabled: "6"},
		},
		{
			name:     "AUS20019_2510271300",
			text:     "AUS20019_D00_01_2510271300",
			isAllion: true,
			model:    "AUS20019",
			id:       "2001901",
			version:  2510271300,
			commands: commandMap{SwitchDisabled: "6"},
		},
		{
			name:     "ADT21090",
			text:     "ADT21090_B00_01_2401231644",
			isAllion: true,
			model:    "ADT21090",
			id:       "2109001",
			version:  2401231644,
			commands: commandMap{SwitchDisabled: "3"},
		},
		{
			name:     "XXRJ45SW",
			text:     "XXRJ45SW_X00_01_2206161303",
			isAllion: true,
			model:    "XXRJ45SW",
			id:       "J45SW01",
			version:  2206161303,
			commands: commandMap{SwitchDisabled: "2"},
		},
		{
			name:     "AUS24080",
			text:     "AUS24080_B00_01_2508281200",
			isAllion: true,
			model:    "AUS24080",
			id:       "2408001",
			version:  2508281200,
			commands: commandMap{SwitchDisabled: "5"},
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
			if !isAllion {
				return
			}
			if info.model != test.model {
				t.Errorf("model does not match, got %v, want %v", info.model, test.model)
			}
			if info.uid != test.id {
				t.Errorf("id does not match, got %v, want %v", info.uid, test.id)
			}
			if info.version != test.version {
				t.Errorf("version does not match, got %v, want %v", info.version, test.version)
			}
			if len(info.commands) != len(test.commands) {
				t.Errorf("command does not match, got %v, want %v", info.commands, test.commands)
			}
			for k, v := range info.commands {
				if v != test.commands[k] {
					t.Errorf("command for %q does not match, got %v, want %v", k, v, test.commands[k])
				}
			}
		})
	}
}
