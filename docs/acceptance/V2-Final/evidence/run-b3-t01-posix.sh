#!/usr/bin/env bash
set -euo pipefail
umask 077
repo=/mnt/d/ExplainLab
out=$(mktemp -d "$repo/docs/acceptance/V2-Final/evidence/b3-t01-posix.XXXXXXXX")
exec > >(tee "$out/pytest.log") 2>&1
trap 'rc=$?; printf "END UTC %s exit=%s\n" "$(date -u +%FT%TZ)" "$rc" | tee "$out/exit.txt"; exit "$rc"' EXIT
printf 'START UTC %s\nEvidence: %s\n' "$(date -u +%FT%TZ)" "$out"
stage=$(mktemp -d "$HOME/explainlab-b3-t01.XXXXXXXX")
[[ $(findmnt -n -T "$stage" -o FSTYPE) == ext4 ]]
findmnt -T "$stage" -o SOURCE,FSTYPE,TARGET
archive="$repo/docs/acceptance/ExplainLab-B1-Round3-Linux-Input.zip"
printf '%s  %s\n' 503dc59a89b68578df9fbfedb65b357c4c1f854ed158b7a5722a79469802d486 "$archive" | sha256sum --check --strict
py="$HOME/explainlab-b1.u4iXLEhT/project/.venv/bin/python"
"$py" -m zipfile -e "$archive" "$stage/project"
cd "$stage/project"
sha256sum --check --strict SHA256SUMS > "$out/base-files.log"
while IFS= read -r file; do
    mkdir -p -- "$(dirname "$file")"
    cp -- "$repo/$file" "$file"
    sha256sum -- "$file"
done <<'FILES' | tee "$out/source-overlays.sha256"
backend/app/api/routes/attachments.py
backend/app/api/routes/import_export.py
backend/app/api/schemas.py
backend/app/dependencies.py
backend/app/main.py
backend/app/services/attachment_staging.py
backend/app/services/attachment_validation.py
backend/app/services/attachments.py
backend/app/services/markdown.py
backend/tests/test_attachment_staging.py
FILES
unset DATABASE_URL EXPLAINLAB_PG_TEST_URL
export PYTHONPATH="$PWD/backend:$PWD/knowledge-core/src"
"$py" -c 'from pathlib import Path; import app.main; assert Path(app.main.__file__).is_relative_to(Path.cwd())'
"$py" -m pytest -o addopts=--import-mode=importlib -ra -s \
    --basetemp="$stage/pytest" --junitxml="$out/pytest.xml" \
    backend/tests/test_attachment_staging.py
