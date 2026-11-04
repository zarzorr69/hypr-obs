#!/bin/sh
# Install the standalone hypr-obs command; no pip or root privileges needed.
set -eu
umask 077

if ! command -v python3 >/dev/null 2>&1; then
    echo "hypr-obs requires Python 3.9 or newer." >&2
    exit 1
fi
if ! python3 -c 'import sys; raise SystemExit(sys.version_info < (3, 9))'; then
    echo "hypr-obs requires Python 3.9 or newer." >&2
    exit 1
fi

# A cloned checkout can install without any network request.
case "$0" in
    */install.sh|install.sh)
        source_dir=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
        if [ -f "$source_dir/hypr_obs.py" ]; then
            exec python3 "$source_dir/hypr_obs.py" setup "$@"
        fi
        ;;
esac

ref=${HYPR_OBS_REF:-main}
case "$ref" in
    ''|*[!A-Za-z0-9._/-]*)
        echo "Invalid HYPR_OBS_REF." >&2
        exit 1
        ;;
esac
temporary=$(mktemp -d "${TMPDIR:-/tmp}/hypr-obs.XXXXXXXX")
trap 'rm -rf -- "$temporary"' EXIT HUP INT TERM
url="https://raw.githubusercontent.com/zarzorr69/hypr-obs/$ref/hypr_obs.py"
if command -v curl >/dev/null 2>&1; then
    curl --fail --silent --show-error --location "$url" --output "$temporary/hypr_obs.py"
elif command -v wget >/dev/null 2>&1; then
    wget --quiet --output-document="$temporary/hypr_obs.py" "$url"
else
    echo "Install curl or wget, or run install.sh from a cloned checkout." >&2
    exit 1
fi
python3 "$temporary/hypr_obs.py" setup "$@"
