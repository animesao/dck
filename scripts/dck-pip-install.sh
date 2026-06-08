#!/bin/sh
# dck-pip-install — skip pip install if packages are already satisfied
#
# Usage:
#   dck-pip-install requirements.txt && python app.py
#
# Uses pip's --dry-run (pip 21.1+) to check before installing.
# Falls through to real install on older pip versions.

if [ $# -lt 1 ]; then
    echo "Usage: $0 <requirements.txt>" >&2
    exit 1
fi

reqfile="$1"
shift

pip install --dry-run -r "$reqfile" -q 2>/dev/null \
    || pip install -r "$reqfile" "$@"
