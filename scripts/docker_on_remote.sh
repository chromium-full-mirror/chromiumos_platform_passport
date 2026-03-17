#!/bin/bash

# Copyright 2024 The ChromiumOS Authors
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

# This is a script for testing the passit service inside a docker image on a
# remote host.
#
# The script
# 1. Builds the docker image from local source
# 2. Pushes it to the remote host
# 3. Starts the docker container on the remote host
#
# Usage:
#
# ./docker_on_remote.sh [--build_from_local] <host_1> [...<host_2>]
#
# Example start using prebuilt docker image from docker registry:
#
# ./docker_on_remote.sh 100.71.235.12
#
# Example Build from local source including any changes in the current workspace:
#
# ./docker_on_remote.sh --build_from_local 100.71.235.12
#
set -e

TEMP_DIR="/tmp/passport_docker"
SCRIPT_DIR="$(dirname "$(realpath -e "${BASH_SOURCE[0]}")")"
PROJECT_DIR="$(realpath -e "${SCRIPT_DIR}/..")"
SSH_CMD="ssh -q -o StrictHostKeyChecking=no"
SATLAB_KEY_FILE="/home/satlab/keys/pubsub-key-do-not-delete.json"
PASSPORT_DOCKER_IMAGE="us-docker.pkg.dev/cros-passport/passport/passport"
LOG_DIVIDER="=================================================================="
HOSTS=()

# parse the cli arguments
while [[ $# -gt 0 ]]; do
  case $1 in
    --build_from_local)
      BUILD_FROM_LOCAL=true
      shift
      ;;
    --include-arm)
      INCLUDE_ARM=true
      shift
      ;;
    *)
      # append to the hosts list
      HOSTS+=("$1")
      shift
      ;;
  esac
done

function set_docker_cmd_path() {
  echo "Searching for docker command"
  DOCKER_CMD=$(${SSH_CMD} "${HOST}" which docker) || true
  if [[ -z "${DOCKER_CMD//}" ]]; then
    # Docker may not be available in the default PATH (e.g. satlab),
    # check other locations, that would otherwise only be added to PATH
    # during interactive login.
    DOCKER_CMD=$(${SSH_CMD} "${HOST}" ls /usr/local/bin/docker)
  fi
  if [[ -z "${DOCKER_CMD//}" ]]; then
    echo "ERROR: failed to find docker executable for host"
    exit 1
  fi
}

function stop_passport_service() {
  echo "Stopping existing containers"
  if ! ${SSH_CMD} "${HOST}" "${DOCKER_CMD}" rm -f passport-dev;
  then
    echo "WARN: failed to stop existing passport container"
  fi
}

function start_passport_service() {
  echo "Starting passport service"
  ${SSH_CMD} "${HOST}" "${DOCKER_CMD}" run \
      -d \
      --cap-add=NET_RAW \
      --rm \
      -p 8300:8300 --privileged \
      --name "passport-dev" \
      "$1" cros-passport --log-level DEBUG

  # Get the IP address of the container and echo forwarding command for testing.
  IP=$(${SSH_CMD} "${HOST}" \
      "${DOCKER_CMD}" inspect \
      -f '{{range.NetworkSettings.Networks}}{{.IPAddress}}{{end}}' \
      passport-dev)
  echo -e "\n${LOG_DIVIDER}"
  echo "Successfully updated passport on host ${HOST}"
  echo "SSH COMMAND: ssh -L 8300:${IP}:8300 ${HOST}"
  echo -e "${LOG_DIVIDER}"
}

if [[ -z "${HOSTS[*]}" ]]; then
  echo "No hosts specified, exiting"
  exit 1
fi

if [[ -z "${BUILD_FROM_LOCAL}" ]]; then
  echo "Defaulting to passport prebuilt from docker registry"
  echo "To build from local source, run with --build_from_local"
  # only run if one host is specified
  if [[ "${#HOSTS[@]}" -gt 1 ]]; then
    echo "ERROR: using prebuilt docker image is not supported with multiple hosts"
    exit 1
  fi
  HOST="${HOSTS[0]}"
  set_docker_cmd_path

  # Try to login using remote keyfile.
  if ${SSH_CMD} "${HOST}" "${DOCKER_CMD} exec -i compose sh -c 'cat \"${SATLAB_KEY_FILE}\" | /usr/local/bin/docker login -u _json_key --password-stdin us-docker.pkg.dev/cros-passport'"; then
    echo "Pulling docker image using remote credentials"
    if ${SSH_CMD} "${HOST}" "${DOCKER_CMD} exec -i compose sh -c '/usr/local/bin/docker pull ${PASSPORT_DOCKER_IMAGE}'"; then
      echo "Pulled docker using remote docker"
    fi
  # Use local docker credentials by specifying DOCKER_HOST
  elif ! DOCKER_HOST=ssh://${HOST} docker pull "${PASSPORT_DOCKER_IMAGE}"; then
    echo "ERROR: failed to pull latest passport docker image"
    exit 1
  fi

  stop_passport_service
  start_passport_service ${PASSPORT_DOCKER_IMAGE}
  exit 0
fi

# else build from local source then push to remote host(s)
echo "Building docker image"
BUILD_FLAGS="--tag=dev"
if [[ "${INCLUDE_ARM}" == true ]]; then
  BUILD_FLAGS="--platforms=linux/amd64,linux/arm64 --tag=dev"
fi
"${SCRIPT_DIR}/build_docker.sh" ${BUILD_FLAGS}

for HOST in "${HOSTS[@]}"; do
  echo -e "\n${LOG_DIVIDER}"
  echo "Updating passport on host '${HOST}'"

  # Check which architecture to use, not comprehensive since we only support
  # arm64 and amd64.
  case $(${SSH_CMD} "${HOST}" uname -m) in
    aarch64)
      ARCH="-arm64" ;;
    x86_64)
      ARCH="-amd64" ;;
    *)
      echo "Unknown architecture for: $(${SSH_CMD} "${HOST}" uname -m)"
      exit 1
  esac

  set_docker_cmd_path

  stop_passport_service

  echo "Copying image to host"
  scp -o StrictHostKeyChecking=no \
      "${TEMP_DIR}/passport-linux${ARCH}.tar" \
      "${HOST}:/tmp/passport.tar"

  echo "Starting container"
  ${SSH_CMD} "${HOST}" "${DOCKER_CMD}" load -i /tmp/passport.tar

  start_passport_service ${PASSPORT_DOCKER_IMAGE}:dev-local-linux${ARCH}
done
