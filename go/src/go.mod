module go.chromiumos.org/chromiumos/platform/passport

go 1.22

replace (
	go.chromium.org/chromiumos/config/go v0.0.0 => ../../../../config/go/src/go.chromium.org/chromiumos/config/go
	go.chromium.org/chromiumos/test v0.0.0 => ../../../../platform/dev/src/go.chromium.org/chromiumos/test
)

require (
	github.com/blackjack/webcam v0.6.1
	go.bug.st/serial v1.6.2
	go.chromium.org/chromiumos/config/go v0.0.0
	go.chromium.org/chromiumos/test v0.0.0
	google.golang.org/grpc v1.67.1
)

require (
	github.com/creack/goselect v0.1.2 // indirect
	golang.org/x/net v0.30.0 // indirect
	golang.org/x/sys v0.27.0 // indirect
	golang.org/x/text v0.20.0 // indirect
	google.golang.org/genproto/googleapis/rpc v0.0.0-20241104194629-dd2ea8efbc28 // indirect
	google.golang.org/protobuf v1.35.1 // indirect
)
