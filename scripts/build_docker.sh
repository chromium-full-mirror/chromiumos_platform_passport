#!/bin/bash
# Copyright 2024 The ChromiumOS Authors
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

# Exit immediately if a command exits with a non-zero status.
set -euo pipefail

TEMP_DIR="/tmp/passport_docker"
PROJECT=us-docker.pkg.dev/cros-passport/passport
DIR="$(dirname "$(realpath -e "${BASH_SOURCE[0]}")")"
DOCKERFILE="${DIR}/../dockerfiles/Dockerfile"

# Remote Git repositories for build context.
REMOTE_APICONFIG_URL="https://chromium.googlesource.com/chromiumos/config.git#main"
REMOTE_PASSPORT_URL="https://chromium.googlesource.com/chromiumos/platform/passport.git#main"
REMOTE_DEV_URL="https://chromium.googlesource.com/chromiumos/platform/dev-util.git#main:src"

# Consolidate all common build flags into a single variable.
FLAGS="-f ${DOCKERFILE}"
INCLUDE_ARM=false

# parse the cli arguments
while [[ $# -gt 0 ]]; do
  case $1 in
    --include-arm)
      INCLUDE_ARM=true
      shift
      ;;
    *)
      # Ignore other flags
      shift
      ;;
  esac
done

# Variables to hold the commit SHAs.
APICONFIG_COMMIT=""
PASSPORT_COMMIT=""
PASSPORT_BUILD_DATE=$(date -u +"%Y-%m-%dT%H:%M:%SZ")
# Temporarily disable exit-on-error to gracefully handle git failures.
set +e

# If local build use local checkout, otherwise use checked in files (default).
if [[ -n "${REMOTE_SOURCE-}" ]]; then
    echo "Using remote sources for build context..."
    FLAGS+="
        --build-context apiconfig=${REMOTE_APICONFIG_URL}
        --build-context passport=${REMOTE_PASSPORT_URL}
        --build-context dev=${REMOTE_DEV_URL}
        "
    # Strip '#main' from URL, get latest commit, and suppress errors.
    APICONFIG_COMMIT=$(git ls-remote "${REMOTE_APICONFIG_URL%#*}" refs/heads/main 2>/dev/null | cut -f1)
    PASSPORT_COMMIT=$(git ls-remote "${REMOTE_PASSPORT_URL%#*}" refs/heads/main 2>/dev/null | cut -f1)
else
    echo "Using local sources for build context..."
    FLAGS+="
        --build-context apiconfig=${DIR}/../../../config/
        --build-context passport=${DIR}/..
        --build-context dev=${DIR}/../../dev/src
        "
    # Get the current commit SHA from local repos and suppress errors.
    APICONFIG_COMMIT=$( (git -C "${DIR}/../../../config/" rev-parse HEAD) 2>/dev/null )
    PASSPORT_COMMIT=$( (git -C "${DIR}/.." rev-parse HEAD) 2>/dev/null )
fi

# Re-enable exit-on-error for the rest of the script.
set -e

echo "Using apiconfig commit string: APICONFIG_COMMIT:${APICONFIG_COMMIT:-unknown}"
echo "Using passport commit string: PASSPORT_COMMIT:${PASSPORT_COMMIT:-unknown}"

# Add commit messages as build arguments for the Dockerfile.
FLAGS+=" --build-arg APICONFIG_COMMIT=APICONFIG_COMMIT:${APICONFIG_COMMIT:-unknown}"
FLAGS+=" --build-arg PASSPORT_COMMIT=PASSPORT_COMMIT:${PASSPORT_COMMIT:-unknown}"
FLAGS+=" --build-arg PASSPORT_BUILD_DATE=PASSPORT_BUILD_DATE:${PASSPORT_BUILD_DATE:-unknown}"

# Build and push a multi-platform image to the registry.
if [[ -n "${PUSH-}" ]]; then
    echo "Starting multi-platform build and push..."
    docker buildx create --use --name passport-builder

    PLATFORMS="linux/amd64"
    if [[ "${INCLUDE_ARM}" == true ]]; then
        PLATFORMS+=",linux/arm64"
    fi

    docker buildx build \
        --platform="${PLATFORMS}" \
        -t "${PROJECT}/passport:latest" \
        ${FLAGS} \
        --push \
        "${DIR}/."
else
    # If not pushing, build for each platform and save as a local .tar file.
    echo "Starting local build. Images will be saved as .tar archives."

    # Build and save amd64 for standard servers.
    echo "Building for linux/amd64..."
    docker buildx build \
        --platform=linux/amd64 \
        -t "${PROJECT}/passport:latest-amd64" \
        --output type=docker \
        ${FLAGS} \
        "${DIR}/."

    mkdir -p "${TEMP_DIR}"
    docker save -o "${TEMP_DIR}/passport-amd64.tar" \
        "${PROJECT}/passport:latest-amd64"

    if [[ "${INCLUDE_ARM}" == true ]]; then
        # Build and save arm64 for Raspberry Pi or other ARM devices.
        echo "Building for linux/arm64..."
        docker buildx build \
            --platform=linux/arm64 \
            -t "${PROJECT}/passport:latest-arm64" \
            --output type=docker \
            ${FLAGS} \
            "${DIR}/."

        docker save -o "${TEMP_DIR}/passport-arm64.tar" \
            "${PROJECT}/passport:latest-arm64"
    fi
fi
