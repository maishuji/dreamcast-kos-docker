#!/bin/sh
# Retry package operations so transient repository/DNS failures do not abort the build.
set -eu

for attempt in 1 2 3 4 5; do
    if apk "$@"; then
        exit 0
    else
        status=$?
    fi

    if [ "$attempt" -eq 5 ]; then
        echo "apk failed after 5 attempts. Check the errors above; DNS or APKINDEX errors indicate unreachable Alpine repositories." >&2
        exit "$status"
    fi

    delay=$((attempt * 5))
    echo "apk failed (attempt $attempt/5); retrying in ${delay}s..." >&2
    sleep "$delay"
done
