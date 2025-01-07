#!/bin/bash
# Copyright 2024 The ChromiumOS Authors
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

docker --version
docker buildx version

DIR="$(dirname "$(realpath -e "${BASH_SOURCE[0]}")")"

# If local build use local checkout, otherwise use checked in files (default).
if [[ -n "${REMOTE_SOURCE}" ]]; then
    API_PATH="https://chromium.googlesource.com/chromiumos/config.git#main"
    PASSPORT_PATH="https://chromium.googlesource.com/chromiumos/platform/passport.git#main"
else
    API_PATH="${DIR}/../../../config/"
    PASSPORT_PATH="${DIR}/.."
fi

# Create in two separate steps allowing a tar of the image to
# be pushed and tested on a remote machine without needing to push
# to a registry first.
docker buildx build \
    --platform=linux/amd64 \
    -t "passport:latest-amd64" \
    --output type=docker \
    --build-context apiconfig="${API_PATH}" \
    --build-context passport="${PASSPORT_PATH}" \
    -f "${DIR}/../dockerfiles/Dockerfile" "${DIR}/."

docker save -o "${DIR}/../passport-amd64.tar" passport:latest-amd64

# Build arm64 for Raspberry Pi.
docker buildx build \
    --platform=linux/arm64 \
    -t "passport:latest-arm64" \
    --output type=docker \
    --build-context apiconfig="${API_PATH}" \
    --build-context passport="${PASSPORT_PATH}" \
    -f "${DIR}/../dockerfiles/Dockerfile" "${DIR}/."

docker save -o "${DIR}/../passport-arm64.tar" passport:latest-arm64
