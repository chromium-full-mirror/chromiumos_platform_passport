module go.chromiumos.org/chromiumos/platform/passport

go 1.24.4

toolchain go1.24.13

replace (
	// use forked copy with fix for b/429248445
	github.com/blackjack/webcam v0.6.1 => github.com/bbrother/webcam v0.0.0-20250721162947-1dd0392aec6d
	go.chromium.org/chromiumos/config/go v0.0.0 => ../../../../config/go/src/go.chromium.org/chromiumos/config/go
	go.chromium.org/chromiumos/test v0.0.0 => ../../../../platform/dev/src/go.chromium.org/chromiumos/test
	go.chromium.org/chromiumos/test/util/portdiscovery => ../../../../platform/dev/src/go.chromium.org/chromiumos/test/util/portdiscovery
)

require (
	github.com/blackjack/webcam v0.6.1
	github.com/google/go-cmp v0.7.0
	github.com/pkg/errors v0.9.1
	github.com/spf13/cobra v1.9.1
	go.bug.st/serial v1.6.2
	go.chromium.org/chromiumos/config/go v0.0.0
	go.chromium.org/chromiumos/test/util/portdiscovery v0.0.0-00010101000000-000000000000
	go.chromium.org/infra v0.0.0-20250530091808-1d369755a219
	google.golang.org/grpc v1.72.2
	google.golang.org/protobuf v1.36.6
)

require (
	github.com/creack/goselect v0.1.2 // indirect
	github.com/inconshreveable/mousetrap v1.1.0 // indirect
	github.com/spf13/pflag v1.0.6 // indirect
	golang.org/x/net v0.39.0 // indirect
	golang.org/x/sys v0.32.0 // indirect
	golang.org/x/text v0.24.0 // indirect
	google.golang.org/genproto/googleapis/rpc v0.0.0-20250425173222-7b384671a197 // indirect
)
