#!/usr/bin/env bash
set -euo pipefail

evidence_root=/mnt/d/ExplainLab/docs/acceptance
archive="$evidence_root/ExplainLab-B1-Round3-Linux-Input.zip"
archive_sha=503dc59a89b68578df9fbfedb65b357c4c1f854ed158b7a5722a79469802d486
[[ $(findmnt -n -T "$HOME" -o FSTYPE) == ext4 ]] || {
    echo 'Refusing to stage outside ext4.' >&2
    exit 1
}
run_dir=$(mktemp -d "$HOME/explainlab-b1.XXXXXXXX")
echo "Run directory: $run_dir"
(
    trap 'rc=$?; printf "END %s exit=%s\n" "$(date -u +%FT%TZ)" "$rc"' EXIT
    set -x
    date -u +%FT%TZ
    id
    uname -a
    findmnt -T / -o SOURCE,FSTYPE,TARGET
    findmnt -T "$run_dir" -o SOURCE,FSTYPE,TARGET
    apt-cache policy postgresql
    printf '%s  %s\n' "$archive_sha" "$archive" | sha256sum --check -
    cp -- "$archive" "$run_dir/input.zip"
    printf '%s  %s\n' "$archive_sha" "$run_dir/input.zip" | sha256sum --check -
    python3 -m zipfile -e "$run_dir/input.zip" "$run_dir/project"
    cd "$run_dir/project"
    sha256sum --check --strict SHA256SUMS
    curl --fail --show-error --silent --location --max-time 120 \
        --output "$run_dir/uv-install.sh" https://astral.sh/uv/install.sh
    UV_UNMANAGED_INSTALL="$run_dir/tools" sh "$run_dir/uv-install.sh"
    export UV_CACHE_DIR="$run_dir/uv-cache"
    export UV_PYTHON_INSTALL_DIR="$run_dir/uv-python"
    uv="$run_dir/tools/uv"
    "$uv" --version
    "$uv" sync --locked --python 3.11.9 --all-packages
    .venv/bin/python -c 'import sys, sqlite3, app, knowledge_core, psycopg; assert sys.version_info[:3] == (3, 11, 9); print(sys.version); print("SQLite", sqlite3.sqlite_version, "psycopg", psycopg.__version__); print("Backend and Core imports OK")'
    sha256sum --check --strict SHA256SUMS
) 2>&1 | tee "$run_dir/environment.log"
