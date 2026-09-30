#!/bin/sh
set -eu

CONFIG_PATH="${CONFIG_PATH:-/app/config/config.json}"
DATA_DIR="${DATA_DIR:-/app/data}"
SETUP_MARKER="${DATA_DIR}/.fishingbucket-setup-complete"

echo "[FishingBucket] Starting container"
echo "[FishingBucket] Configuration: ${CONFIG_PATH}"
echo "[FishingBucket] Data directory: ${DATA_DIR}"

if [ ! -f "${CONFIG_PATH}" ]; then
    echo "[FishingBucket] ERROR: Configuration file not found: ${CONFIG_PATH}" >&2
    echo "[FishingBucket] Mount config.json at /app/config/config.json" >&2
    exit 1
fi

mkdir -p "${DATA_DIR}"

if [ ! -f "${SETUP_MARKER}" ]; then
    echo "[FishingBucket] Running initial setup scripts..."

    script_found=false

    for script in /app/scripts/*.py; do
        if [ ! -f "${script}" ]; then
            continue
        fi

        script_found=true
        echo "[FishingBucket] Running ${script}"
        python "${script}"
    done

    if [ "${script_found}" = false ]; then
        echo "[FishingBucket] WARNING: No Python setup scripts found in /app/scripts"
    fi

    touch "${SETUP_MARKER}"
    echo "[FishingBucket] Initial setup completed"
else
    echo "[FishingBucket] Setup was already completed"
fi

echo "[FishingBucket] Launching bot"

exec "$@"