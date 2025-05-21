module go.chromiumos.org/chromiumos/platform/passport

go 1.22.0

toolchain go1.22.2

replace (
	go.chromium.org/chromiumos/config/go v0.0.0 => ../../../../config/go/src/go.chromium.org/chromiumos/config/go
	go.chromium.org/chromiumos/test v0.0.0 => ../../../../platform/dev/src/go.chromium.org/chromiumos/test
)

require (
	github.com/blackjack/webcam v0.6.1
	github.com/google/go-cmp v0.7.0
	github.com/spf13/cobra v1.9.1
	go.bug.st/serial v1.6.2
	go.chromium.org/chromiumos/config/go v0.0.0
	go.chromium.org/chromiumos/test v0.0.0
	google.golang.org/grpc v1.71.0
)

require (
	github.com/creack/goselect v0.1.2 // indirect
	github.com/inconshreveable/mousetrap v1.1.0 // indirect
	github.com/spf13/pflag v1.0.6 // indirect
	golang.org/x/net v0.35.0 // indirect
	golang.org/x/sys v0.30.0 // indirect
	golang.org/x/text v0.22.0 // indirect
	google.golang.org/genproto/googleapis/rpc v0.0.0-20250218202821-56aae31c358a // indirect
	google.golang.org/protobuf v1.36.5 // indirect
)
