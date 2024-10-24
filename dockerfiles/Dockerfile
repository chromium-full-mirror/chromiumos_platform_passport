# Copyright 2024 The ChromiumOS Authors
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.
FROM --platform=$BUILDPLATFORM golang:alpine AS build

# Pass apiconfig as an argument to docker buildx
COPY --from=apiconfig . ./source/config
COPY --from=passport . ./source/platform/passport/

# Use golang cross-compile support to build for target arch.
ARG TARGETOS TARGETARCH
RUN GOOS=$TARGETOS GOARCH=$TARGETARCH CGO_ENABLED=0 \
    go build -C ./source/platform/passport/go/src -o /bin/passport

FROM scratch
COPY --from=build /bin/passport /bin/passport

CMD ["/bin/passport"]
