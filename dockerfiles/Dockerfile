# syntax=docker/dockerfile:1

# Copyright 2024 The ChromiumOS Authors
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

FROM --platform=$BUILDPLATFORM debian:bookworm-slim AS usb_build

RUN apt update
RUN apt install -y build-essential devscripts debhelper
RUN git clone https://github.com/libusb/libusb.git
WORKDIR "/libusb/"
RUN git checkout v1.0.28
RUN ./autogen.sh --disable-udev
RUN make

FROM --platform=$BUILDPLATFORM golang:alpine AS build

# Pass sources as an argument to docker buildx
COPY --from=apiconfig . ./source/config
COPY --from=passport . ./source/platform/passport/
COPY --from=dev . ./source/platform/dev/src/

# Use golang cross-compile support to build for target arch.
ARG TARGETOS TARGETARCH
RUN GOOS=$TARGETOS GOARCH=$TARGETARCH CGO_ENABLED=0 \
    go build -C ./source/platform/passport/go/src -o /bin/cros-passport

FROM --platform=$BUILDPLATFORM debian:bookworm-slim AS acronamectl

# Prepare python the environment.
RUN apt-get update \
    && apt-get install -y python3-venv \
    && mkdir -p /usr/local/bin/python \
    && mkdir -p /usr/local/bin/python/chromiumos_apis \
    && python3 -m venv /usr/local/bin/python/venv \
    && apt-get install -y binutils python3-dev

# CD into the python dir.
WORKDIR "/usr/local/bin/python"

# Copy dependencies and sources.
COPY --from=apiconfig python/ chromiumos_apis
COPY --from=passport python/ .

RUN venv/bin/pip install --require-hashes -r acroname_requirements.txt \
    && venv/bin/pip install --no-deps --no-index chromiumos_apis/

RUN venv/bin/pyinstaller \
      --name acronamectl \
      --collect-all brainstem \
      --onefile acronamectl.py

FROM --platform=$BUILDPLATFORM debian:bookworm-slim AS unigrafctl_build

# Prepare python the enviroment.
RUN apt-get update \
    && apt-get install -y python3-venv wget libusb-1.0-0-dev \
    && mkdir -p /usr/local/bin/unigraf \
    && mkdir -p /usr/local/bin/unigraf/chromiumos_apis \
    && python3 -m venv /usr/local/bin/unigraf/venv \
    && apt-get install -y binutils python3-dev

# CD into the unigraf dir.
WORKDIR "/usr/local/bin/unigraf"

# Copy dependencies and sources.
COPY --from=apiconfig python/ chromiumos_apis
COPY --from=passport python/ .

ARG UTC274_SDK_VERSION=1.1.57.809
ARG UCD500_SDK_VERSION=3.6.398.13810

# Install the unigraf control dependencies and the chromiumos APIs.
RUN wget https://storage.googleapis.com/chromeos-localmirror/distfiles/UTCLibrary-${UTC274_SDK_VERSION}.tar.gz \
    && wget https://storage.googleapis.com/chromeos-localmirror/distfiles/UniTAP-${UCD500_SDK_VERSION}.tar.gz \
    && venv/bin/pip install --require-hashes -r unigraf_requirements.txt \
    && venv/bin/pip install --no-deps --no-index chromiumos_apis/

RUN venv/bin/pyinstaller \
    --collect-all UniTAP \
    --name testervideoctl \
    --onefile unigraf/__main__.py

# Libusb is bundled and loaded by pyinstaller, the SDK load call is irrelevant.
COPY --from=usb_build /libusb/libusb/.libs/libusb-1.0.so.0 \
  /usr/lib/x86_64-linux-gnu/libusb-1.0.so.0

RUN venv/bin/pyinstaller \
      --collect-all UTCLibrary \
      --name testerusbctl \
      --onefile unigraf/__main__.py

FROM build AS go_licenses

# Collect licenses using go-licenses.
WORKDIR "./source/platform/passport/go/src"
COPY --from=passport ./LICENSE .

RUN go install github.com/google/go-licenses@latest \
    && go-licenses save . \
      --save_path=/third_party/go \
      --ignore go.chromiumos.org \
      --ignore go.chromium.org/chromiumos/ \
    && go-licenses csv . \
      --ignore go.chromiumos.org \
      --ignore go.chromium.org/chromiumos/ | tee /third_party/go/list.csv

# Collect licenses for python using pip-licenses
FROM unigrafctl_build AS python_licenses

WORKDIR "/usr/local/bin/unigraf"

# Install other packages
RUN venv/bin/pip install --require-hashes -r acroname_requirements.txt

# Collect licenses
RUN venv/bin/pip install -U pip-licenses \
    && mkdir -p /third_party/python \
    && venv/bin/pip-licenses \
      --format=plain-vertical -u \
      --with-license-file \
      --no-license-path \
      --output-file=/third_party/python/LICENSE \
    && venv/bin/pip-licenses \
      --format=csv -u \
      --output-file=/third_party/python/list.csv

# Final assembly.
FROM --platform=$BUILDPLATFORM debian:bookworm-slim

RUN apt-get update \
  && apt-get install -y usbutils libpcap-dev ca-certificates ffmpeg \
  && update-ca-certificates \
  && mkdir -p /opt/unigraf/

COPY --from=unigrafctl_build /usr/local/bin/unigraf/dist/testervideoctl \
  /bin/testervideoctl

COPY --from=unigrafctl_build /usr/local/bin/unigraf/dist/testerusbctl \
  /bin/testerusbctl

COPY --from=acronamectl /usr/local/bin/python/dist/acronamectl \
  /bin/acronamectl

COPY --from=build /bin/cros-passport /bin/cros-passport

# Copy licenses
COPY --from=go_licenses /third_party/ /third_party/
COPY --from=python_licenses /third_party/ /third_party/

ARG APICONFIG_COMMIT="APICONFIG_COMMIT:unknown"
ARG PASSPORT_COMMIT="PASSPORT_COMMIT:unknown"
ARG PASSPORT_BUILD_DATE="PASSPORT_BUILD_DATE:unknown"

RUN echo "${APICONFIG_COMMIT}" > /build_info.txt && \
    echo "${PASSPORT_COMMIT}" >> /build_info.txt && \
    echo "${PASSPORT_BUILD_DATE}" >> /build_info.txt


CMD ["/bin/cros-passport"]
