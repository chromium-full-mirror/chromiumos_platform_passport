#!/bin/bash
# Copyright 2024 The ChromiumOS Authors
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.


PROJECT=us-docker.pkg.dev/cros-passport/passport
DIR="$(dirname "$(realpath -e "${BASH_SOURCE[0]}")")"

# If local build use local checkout, otherwise use checked in files (default).
if [[ -n "${REMOTE_SOURCE}" ]]; then
    FLAGS="
        --build-context apiconfig=https://chromium.googlesource.com/chromiumos/config.git#main
        --build-context passport=https://chromium.googlesource.com/chromiumos/platform/passport.git#main
        --build-context dev=https://chromium.googlesource.com/chromiumos/platform/dev-util.git#main:src
        -f ${DIR}/../dockerfiles/Dockerfile
        "
else
    FLAGS="
        --build-context apiconfig=${DIR}/../../../config/
        --build-context passport=${DIR}/..
        --build-context dev=${DIR}/../../dev/src
        -f ${DIR}/../dockerfiles/Dockerfile
        "
fi

# to a registry first.
if [[ -n "${PUSH}" ]]; then
    docker buildx create --use --name passport-builder

    docker buildx build \
        --platform=linux/arm64,linux/amd64 \
        -t "${PROJECT}/passport:latest" \
        ${FLAGS} \
        --push \
        -f "${DIR}/../dockerfiles/Dockerfile" "${DIR}/."
else
    # If not pushing, then create in two separate steps
    docker buildx build \
        --platform=linux/amd64 \
        -t "${PROJECT}/passport:latest-amd64" \
        --output type=docker \
        ${FLAGS} \
        -f "${DIR}/../dockerfiles/Dockerfile" "${DIR}/."

    docker save -o "${DIR}/../passport-amd64.tar" \
        "${PROJECT}/passport:latest-amd64"

    # Build arm64 for Raspberry Pi.
    docker buildx build \
        --platform=linux/arm64 \
        -t "${PROJECT}/passport:latest-arm64" \
        --output type=docker \
        ${FLAGS} \
        -f "${DIR}/../dockerfiles/Dockerfile" "${DIR}/."

    docker save -o "${DIR}/../passport-arm64.tar" \
        "${PROJECT}/passport:latest-arm64"
fi
