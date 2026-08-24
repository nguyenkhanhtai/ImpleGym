#!/bin/bash
set -e

# Run Yosupo synchronization command via implegym CLI if AUTO_SYNC_YOSUPO is enabled (default: true)
if [ "${AUTO_SYNC_YOSUPO:-true}" = "true" ]; then
    echo "==> [ImpleGym] Synchronizing official Yosupo Library Checker problems..."
    python -m implegym.cli sync-yosupo || echo "==> [Warning] sync-yosupo encountered an issue, proceeding with container startup..."
fi

# Execute CMD passed to container
exec "$@"
