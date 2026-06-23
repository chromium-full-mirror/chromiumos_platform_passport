#!/bin/bash

# Copyright 2025 The ChromiumOS Authors
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

# This script manages the passport docker container for local test running.
# It supports starting the container and checking its status as well as other
# operations.

set -euo pipefail

# --- Self-Update Configuration ---
# (No SCRIPT_VERSION needed if using SHA256)
SCRIPT_URL="https://chromium.googlesource.com/chromiumos/platform/passport.git/+/refs/heads/main/scripts/passportd.sh?format=TEXT"
# --- End Configuration ---

# --- Robust Trap Handler ---
declare -a EXIT_CLEANUP_CMDS=()

#######################################
# Adds a command to be run on script exit.
# Globals:
#   EXIT_CLEANUP_CMDS
# Arguments:
#   Command string to execute.
#######################################
add_to_cleanup() {
  EXIT_CLEANUP_CMDS+=( "$@" )
}

#######################################
# Executes all registered cleanup commands.
# Globals:
#   EXIT_CLEANUP_CMDS
# Arguments:
#   None
#######################################
cleanup_on_exit() {
  for cmd in "${EXIT_CLEANUP_CMDS[@]}"; do
    # Using eval to correctly handle commands with quoted paths
    eval "${cmd}"
  done
}

# Set the EXIT trap once.
trap cleanup_on_exit EXIT
# --- End Trap Handler ---

readonly DOCKER_IMAGE_REPO="us-docker.pkg.dev/cros-passport/passport/passport"
readonly TEMP_DIR="/tmp/passport_docker"

#######################################
# Determines the correct passport image and tag based on host architecture.
# Globals:
#   None
# Arguments:
#   None
# Outputs:
#   Writes the full docker image name to stdout.
#######################################
get_passport_image_for_host() {
  local arch
  arch=$(uname -m)
  local tag
  case "${arch}" in
    "aarch64" | "arm64")
      tag="latest-arm64"
      ;;
    "x86_64")
      tag="latest-amd64"
      ;;
    *)
      echo "Error: Unsupported architecture: ${arch}" >&2
      exit 1
      ;;
  esac
  echo "${DOCKER_IMAGE_REPO}:${tag}"
}

#######################################
# Helper function to get the ID of a single running container.
# Exits with an error if multiple containers are found.
# Globals:
#   None
# Arguments:
#   image_name: The name of the docker image to check for.
# Outputs:
#   Writes the container ID to stdout on success, or an empty string if no
#   containers are found.
#######################################
get_single_container_id() {
  local image_name="${1}"
  local running_containers
  running_containers=$(docker ps -q --filter ancestor="${image_name}")

  if [[ -z "${running_containers}" ]]; then
    return
  fi

  local container_count
  container_count=$(echo "${running_containers}" | wc -l | xargs)

  if [ "${container_count}" -ne 1 ]; then
    echo "Error: Multiple running containers found. Please specify which one to use with --container <container_id>" >&2
    docker ps --filter ancestor="${image_name}" --format "table {{.ID}}\t{{.Status}}\t{{.Ports}}"
    exit 1
  fi

  echo "${running_containers}"
}

#######################################
# Installs the passport docker image.
# Globals:
#   None
# Arguments:
#   None
#######################################
install() {
  if ! command -v docker &> /dev/null; then
    echo "Error: docker could not be found." >&2
    echo "Please install docker and try again." >&2
    exit 1
  fi

  local image_name
  image_name=$(get_passport_image_for_host)

  if [[ -n "$(docker images -q "${image_name}")" ]]; then
    echo "Docker image '${image_name}' is already installed."
    return
  fi

  echo "Passport docker image not found. Installing..."

  local tmp_dir
  tmp_dir=$(mktemp -d)
  # Ensure temp directory is cleaned up on script exit
  add_to_cleanup "rm -rf '${tmp_dir}'"

  local scripts_dir="${tmp_dir}/scripts"
  local dockerfiles_dir="${tmp_dir}/dockerfiles"
  mkdir -p "${scripts_dir}" "${dockerfiles_dir}"

  local build_script_url="https://chromium.googlesource.com/chromiumos/platform/passport.git/+/refs/heads/main/scripts/build_docker.sh?format=TEXT"
  local build_script_path="${scripts_dir}/build_docker.sh"

  echo "Downloading and decoding build script..."
  if ! curl -L "${build_script_url}" | base64 -d > "${build_script_path}"; then
    echo "Error: Failed to download or decode build script." >&2
    exit 1
  fi
  chmod +x "${build_script_path}"

  local dockerfile_url="https://chromium.googlesource.com/chromiumos/platform/passport.git/+/refs/heads/main/dockerfiles/Dockerfile?format=TEXT"
  local dockerfile_path="${dockerfiles_dir}/Dockerfile"

  echo "Downloading and decoding Dockerfile..."
  if ! curl -L "${dockerfile_url}" | base64 -d > "${dockerfile_path}"; then
    echo "Error: Failed to download or decode Dockerfile." >&2
    exit 1
  fi

  echo "Running build script to create docker image tarballs..."
  (
    cd "${scripts_dir}"
    local build_flags="--platforms amd64"
    local arch
    arch=$(uname -m)
    if [[ "${arch}" == "aarch64" || "${arch}" == "arm64" ]]; then
      build_flags="--platforms amd64,arm64"
    fi
    if ! /bin/bash "${build_script_path}" --remote_source --tag latest ${build_flags}; then
      echo "Error: Failed to build docker images." >&2
      exit 1
    fi
  )

  echo "Loading docker images..."
  if [ -f "${TEMP_DIR}/passport-amd64.tar" ]; then
    docker load -i "${TEMP_DIR}/passport-amd64.tar"
    docker tag "${DOCKER_IMAGE_REPO}:latest-local-amd64" "${DOCKER_IMAGE_REPO}:latest-amd64"
  fi
  if [ -f "${TEMP_DIR}/passport-arm64.tar" ]; then
    docker load -i "${TEMP_DIR}/passport-arm64.tar"
    docker tag "${DOCKER_IMAGE_REPO}:latest-local-arm64" "${DOCKER_IMAGE_REPO}:latest-arm64"
  fi

  echo "Installation complete. Verifying..."
}


#######################################
# Prints the status of passport images and containers.
# Globals:
#   None
# Arguments:
#   None
#######################################
status() {
  local image_name
  image_name=$(get_passport_image_for_host)

  echo "--- Checking for local passport docker image: ${image_name}"
  local passport_image
  passport_image=$(docker images --filter "reference=${image_name}" --format "{{.Repository}}:{{.Tag}}")

  if [[ -z "${passport_image}" ]]; then
    echo "Error: Docker image '${image_name}' not found. Please install it." >&2
    exit 1
  fi

  echo "Found passport image:"
  echo "${passport_image}"

  echo ""
  echo "--- Checking for running passport containers..."
  if [ -n "$(docker ps -q --filter ancestor="${image_name}")" ]; then
    docker ps --filter ancestor="${image_name}" --format "table {{.ID}}\t{{.Status}}\t{{.Ports}}"
  else
    echo "No running containers found for image ${image_name}."
  fi
}

#######################################
# Starts a new docker container from the passport image.
# Globals:
#   None
# Arguments:
#   --port: Optional port to map to the container's port 8300.
#######################################
start() {
  local port=8300

  while [[ ${#} -gt 0 ]]; do
    case "${1}" in
      --port)
        if [[ -n "${2}" ]]; then
          port="${2}"
          shift 2
        else
          echo "Error: --port requires an argument." >&2
          exit 1
        fi
        ;;
      *)
        echo "Unknown argument for start: ${1}" >&2
        exit 1
        ;;
    esac
  done

  local image_name
  image_name=$(get_passport_image_for_host)

  if [[ -z "$(docker images -q "${image_name}")" ]]; then
    echo "Error: Docker image '${image_name}' not found. Cannot start container." >&2
    exit 1
  fi

  echo "Starting container in the background from image: ${image_name}, mapping host port ${port} to container port 8300"
  docker run -d --privileged -v /dev/bus/usb:/dev/bus/usb -p "${port}":8300 "${image_name}"
}

#######################################
# Stops the passport docker container.
# Globals:
#   None
# Arguments:
#   --container: Optional container ID to stop. If not provided, it will be
#                inferred if only one container is running.
#   --all:       Stop all running passport containers.
#######################################
stop() {
  local container_id=""
  local stop_all=false

  while [[ ${#} -gt 0 ]]; do
    case "${1}" in
      --container)
        if [[ -n "${2}" ]]; then
          container_id="${2}"
          shift 2
        else
          echo "Error: --container requires an argument." >&2
          exit 1
        fi
        ;;
      --all)
        stop_all=true
        shift
        ;;
      *)
        echo "Unknown argument for stop: ${1}" >&2
        exit 1
        ;;
    esac
  done

  local image_name
  image_name=$(get_passport_image_for_host)

  if [[ "${stop_all}" = true ]]; then
    local running_containers
    running_containers=$(docker ps -q --filter ancestor="${image_name}")
    if [[ -z "${running_containers}" ]]; then
      echo "No running passport containers to stop."
      return
    fi
    echo "Stopping all running passport containers..."
    docker stop "${running_containers}"
    return
  fi

  if [[ -z "${container_id}" ]]; then
    container_id=$(get_single_container_id "${image_name}")
    if [[ -z "${container_id}" ]]; then
      echo "No running passport containers to stop."
      return
    fi
  fi

  echo "Stopping container ${container_id}..."
  docker stop "${container_id}"
}

#######################################
# Shows the logs from the passport docker container.
# Globals:
#   None
# Arguments:
#   --container: Optional container ID to get logs from. If not provided, it
#                will be inferred if only one container is running.
#######################################
log() {
  local container_id=""

  while [[ ${#} -gt 0 ]]; do
    case "${1}" in
      --container)
        if [[ -n "${2}" ]]; then
          container_id="${2}"
          shift 2
        else
          echo "Error: --container requires an argument." >&2
          exit 1
        fi
        ;;
      *)
        echo "Unknown argument for log: ${1}" >&2
        exit 1
        ;;
    esac
  done

  if [[ -z "${container_id}" ]]; then
    local image_name
    image_name=$(get_passport_image_for_host)
    container_id=$(get_single_container_id "${image_name}")
    if [[ -z "${container_id}" ]]; then
      echo "No running passport containers found."
      return
    fi
  fi

  echo "Showing logs from container ${container_id}..."
  docker exec "${container_id}" cat /tmp/cros-passport/log.txt
}

#######################################
# Checks for updates to this script and applies them using SHA256.
# Globals:
#   SCRIPT_URL
# Arguments:
#   None
#######################################
update_script() {
    echo "Checking for updates..."

    if ! command -v sha256sum &> /dev/null; then
        echo "Error: 'sha256sum' command not found. Cannot check for updates." >&2
        return 1
    fi

    local SCRIPT_PATH
    SCRIPT_PATH="${BASH_SOURCE[0]}"
    if [[ ! -f "${SCRIPT_PATH}" ]]; then
        echo "Error: Could not determine script path." >&2
        exit 1
    fi

    # Calculate the hash of the currently running script
    local local_hash
    local_hash=$(sha256sum "${SCRIPT_PATH}" | awk '{print $1}')

    local tmp_script
    tmp_script=$(mktemp)

    # Clean up temp file on exit
    add_to_cleanup "rm -f '${tmp_script}'"

    # Download and decode the latest script
    echo "Downloading and decoding latest script..."
    if ! curl -sL "${SCRIPT_URL}" | base64 -d > "${tmp_script}"; then
        echo "Error: Failed to download or decode update." >&2
        return 1
    fi

    # Calculate the hash of the downloaded script
    local remote_hash
    remote_hash=$(sha256sum "${tmp_script}" | awk '{print $1}')

    # Compare the hashes
    if [[ "${local_hash}" == "${remote_hash}" ]]; then
        echo "Script is up to date (SHA: ${local_hash:0:12})."
        return 0
    fi

    echo "New version available (SHA: ${remote_hash:0:12}). Updating from ${local_hash:0:12}..."

    # Perform the update
    chmod +x "${tmp_script}"

    if ! cp "${tmp_script}" "${SCRIPT_PATH}"; then
        echo "Error: Failed to overwrite script with new version." >&2
        return 1
    fi

    echo "Update complete. Relaunching..."

    # Relaunch to confirm the new version is now "up to date"
    exec "${SCRIPT_PATH}" "update-script"
    exit 0
}

# Prints the help message.
help() {
  cat <<EOF
Usage: ${0} <command> [options]

Manages the passport docker container.

Commands:
  install       Install the passport docker image.
  status        Show the status of passport docker images and containers.
  start         Start a new passport docker container.
  stop          Stop a running passport docker container.
  log           Show logs from a running passport container.
  update-script Update this script to the latest version.
  help          Show this help message.

Options:
  --port <port>               (for start) Port to map to the container's port 8300.
  --container <container_id>  (for stop/log) Specify the container ID. If not provided, it will be inferred if only one container is running.
  --all                       (for stop) Stop all running passport containers.
EOF
}

main() {
  if [ ${#} -eq 0 ]; then
    help
    exit 1
  fi

  local command=${1}
  shift

  case "${command}" in
    install)
      install
      ;;
    status)
      status
      ;;
    start)
      start "${@}"
      ;;
    stop)
      stop "${@}"
      ;;
    log)
      log "${@}"
      ;;
    update-script)
      update_script
      ;;
    help)
      help
      ;;
    *)
      echo "Unknown command: ${command}"
      help
      exit 1
      ;;
  esac
}

main "${@}"
