# syntax=docker/dockerfile:1

# Copyright 2024 The ChromiumOS Authors
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

FROM --platform=$BUILDPLATFORM golang:alpine AS build

# Pass apiconfig as an argument to docker buildx
COPY --from=apiconfig . ./source/config
COPY --from=passport . ./source/platform/passport/
COPY --from=dev . ./source/platform/dev/src/

# Use golang cross-compile support to build for target arch.
ARG TARGETOS TARGETARCH
RUN GOOS=$TARGETOS GOARCH=$TARGETARCH CGO_ENABLED=0 \
    go build -C ./source/platform/passport/go/src -o /bin/cros-passport

FROM --platform=$BUILDPLATFORM debian:bookworm-slim AS unigrafctl_build

# Prepare python the enviroment.
RUN apt-get update \
    && apt-get install -y python3-venv libusb-1.0-0-dev wget \
    && mkdir -p /usr/local/bin/unigraf \
    && mkdir -p /usr/local/bin/unigraf/chromiumos_apis \
    && python3 -m venv /usr/local/bin/unigraf/venv \
    && apt-get install -y binutils python3-dev

# CD into the unigraf dir.
WORKDIR "/usr/local/bin/unigraf"

# Copy dependencies and sources.
COPY --from=apiconfig python/ chromiumos_apis
COPY --from=passport python/ .

ARG UNIGRAF_SDK_VERSION=1.1.3.652

# Install the unigraf control dependencies and the chromiumos APIs.
RUN wget https://storage.googleapis.com/chromeos-localmirror/distfiles/UTCLibrary-${UNIGRAF_SDK_VERSION}.tar.gz \
    && venv/bin/pip install --require-hashes -r unigraf/requirements.txt \
    && venv/bin/pip install --no-deps --no-index chromiumos_apis/ \
    && venv/bin/pyinstaller \
      --collect-all UTCLibrary \
      --name unigrafctl \
      --onefile unigraf/__main__.py

# Final assembly.
FROM --platform=$BUILDPLATFORM debian:bookworm-slim

RUN apt-get update && apt-get install -y usbutils

COPY --from=unigrafctl_build /usr/local/bin/unigraf/dist/unigrafctl /bin/unigrafctl
COPY --from=build /bin/cros-passport /bin/cros-passport

CMD ["/bin/cros-passport"]
