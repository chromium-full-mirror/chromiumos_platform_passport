#!/bin/bash

# Copyright 2024 The ChromiumOS Authors
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

# This downloads the needed golang version, downloads dependencies, runs unit
# tests, and builds passport.

set -e

GO_VERSION="go1.22.2"
SCRIPT_DIR="$(dirname "$(realpath -e "${BASH_SOURCE[0]}")")"
PROJECT_DIR="$(realpath -e "${SCRIPT_DIR}/..")"
PROJECT_GOPATH="${PROJECT_DIR}/go"
PROJECT_EXE_NAME="passport"
PROJECT_EXE_PATH="${PROJECT_DIR}/go/bin/${PROJECT_EXE_NAME}"
GOBIN="${GOBIN:-"/tmp/passport_go/bin"}"
GO_CMD="${GOBIN}/${GO_VERSION}"
export GOMODCACHE="/tmp/passport_go/cache"

mkdir -p "${GOBIN}"
mkdir -p "${GOMODCACHE}"

set -x

# Configure project go version.
if ! command -v "${GO_CMD}"; then
  export GOBIN
  go install "golang.org/dl/${GO_VERSION}@latest"
  "${GO_CMD}" download
fi

# Configure project go environment
export GOPATH="${PROJECT_GOPATH}"
export GO111MODULE=on

# Get packages, format files, run tests, and build executable.
cd "${PROJECT_GOPATH}/src" && "${GO_CMD}" mod tidy
cd "${PROJECT_GOPATH}/src" && "${GO_CMD}" fmt ./...
cd "${PROJECT_GOPATH}/src" && "${GO_CMD}" test ./...
cd "${PROJECT_GOPATH}/src" && "${GO_CMD}" build -o "${PROJECT_EXE_PATH}"
