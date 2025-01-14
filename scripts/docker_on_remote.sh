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
# ./docker_on_remote.sh <host_1> [...<host_2>]
set -e

SCRIPT_DIR="$(dirname "$(realpath -e "${BASH_SOURCE[0]}")")"
PROJECT_DIR="$(realpath -e "${SCRIPT_DIR}/..")"
SSH_CMD="ssh -q -o StrictHostKeyChecking=no"
DOCKER_DRONE_CMD=""
LOG_DIVIDER="=================================================================="

echo "Building docker image"
"${SCRIPT_DIR}/build_docker.sh"

for HOST in "$@"; do
  echo -e "\n${LOG_DIVIDER}"
  echo "Updating passport on host '${HOST}'"

  # Chech which architecture to use, not comprehensive since we only support
  # arm64 and amd64.
  case $(${SSH_CMD} "${HOST}" uname -m) in
    aarch64)
      ARCH="arm64" ;;
    x86_64)
      ARCH="amd64" ;;
    *)
      echo "Unknown architecture for: $(${SSH_CMD} "${HOST}" uname -m)"
      exit 1
  esac

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

  if [[ -n "${RUN_IN_DRONE}" ]]; then
    DOCKER_DRONE_CMD="exec drone docker"
    echo "Running docker in drone container"
  fi

  echo "Stopping existing containers"
  if ! ${SSH_CMD} "${HOST}" "${DOCKER_CMD}" ${DOCKER_DRONE_CMD} rm -f passport-dev;
  then
    echo "WARN: failed to stop existing passport container"
  fi

  echo "Copying image to host"
  scp -o StrictHostKeyChecking=no \
      "${PROJECT_DIR}/passport-${ARCH}.tar" \
      "${HOST}:/tmp/passport.tar"
  if [[ -n "${DOCKER_DRONE_CMD}" ]]; then
      ${SSH_CMD} "${HOST}" "${DOCKER_CMD}" cp /tmp/passport.tar drone:/tmp/passport.tar
  fi

  echo "Starting container"
  ${SSH_CMD} "${HOST}" "${DOCKER_CMD}" ${DOCKER_DRONE_CMD} load -i /tmp/passport.tar

  if [[ -n "${DOCKER_DRONE_CMD}" ]]; then
    EXEC_TYPE_SPECIFIC_ARGS="--network=adb-network"
  else
    EXEC_TYPE_SPECIFIC_ARGS="-p 8300:8300"
  fi
  ${SSH_CMD} "${HOST}" "${DOCKER_CMD}" ${DOCKER_DRONE_CMD} run \
      -d \
      --cap-add=NET_RAW \
      --rm \
      ${EXEC_TYPE_SPECIFIC_ARGS} \
      --name "passport-dev" \
      --volume=/dev:/dev \
      "passport:latest-${ARCH}"

  # Get the IP address of the container and echo forwarding command for testing.
  IP=$(${SSH_CMD} "${HOST}" \
      "${DOCKER_CMD}" ${DOCKER_DRONE_CMD} inspect \
      -f '{{range.NetworkSettings.Networks}}{{.IPAddress}}{{end}}' \
      passport-dev)
  echo -e "\n${LOG_DIVIDER}"
  echo "Successfully updated passport on host ${HOST}"
  if [[ -n "${DOCKER_DRONE_CMD}" ]]; then
    echo "Passport service running in drone container ${IP}:8300"
  else
    echo "SSH COMMAND: ssh -L 8300:${IP}:8300 ${HOST}"
  fi
  echo -e "${LOG_DIVIDER}"
done
