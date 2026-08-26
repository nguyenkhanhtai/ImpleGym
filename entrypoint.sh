#!/bin/bash
set -e

# Run problem synchronization command via implegym CLI if AUTO_SYNC_PROBLEMS is enabled (default: true)
if [ "${AUTO_SYNC_PROBLEMS:-${AUTO_SYNC_YOSUPO:-true}}" = "true" ]; then
    echo "==> [ImpleGym] Synchronizing official problems base repository..."
    python -m implegym.cli sync-problems || echo "==> [Warning] sync-problems encountered an issue, proceeding with container startup..."
fi

# Execute CMD passed to container
exec "$@"
