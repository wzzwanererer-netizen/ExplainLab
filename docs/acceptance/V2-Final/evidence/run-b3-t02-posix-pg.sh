#!/usr/bin/env bash
set -euo pipefail
umask 077
repo=/mnt/d/ExplainLab
out=$(mktemp -d "$repo/docs/acceptance/V2-Final/evidence/b3-t02-posix-pg.XXXXXXXX")
exec > >(tee "$out/driver.log") 2>&1
printf 'START UTC %s\nEvidence: %s\n' "$(date -u +%FT%TZ)" "$out"
previous="$HOME/explainlab-b1.u4iXLEhT"
cluster="$previous/acceptance.R3sYC6uE"
stage=$(mktemp -d "$HOME/explainlab-b3-http.XXXXXXXX")
pg="$cluster/pg-root/usr/lib/postgresql/18/bin"
data="$cluster/pg-data"
port=59927
db="explainlab_b3_http_${stage##*.}"
db=$(printf '%s' "$db" | tr '[:upper:]' '[:lower:]')
role=explainlab_b1_runner
started=0
created=0
finish() {
    local rc=$?
    trap - EXIT
    if (( created )); then
        "$pg/dropdb" -h "$cluster/pg-socket" -p "$port" -- "$db" || rc=1
    fi
    if (( started )); then
        "$pg/pg_ctl" -D "$data" -m fast -w -t 20 stop || rc=1
    fi
    if [[ -f "$stage/server.log" ]]; then cp -- "$stage/server.log" "$out/postgresql-server.log"; fi
    printf 'END UTC %s exit=%s\n' "$(date -u +%FT%TZ)" "$rc" | tee "$out/exit.txt"
    exit "$rc"
}
trap finish EXIT
[[ $(findmnt -n -T "$stage" -o FSTYPE) == ext4 ]]
[[ $(findmnt -n -T "$data" -o FSTYPE) == ext4 && ! -e "$data/postmaster.pid" ]]
archive="$repo/docs/acceptance/ExplainLab-B1-Round3-Linux-Input.zip"
printf '%s  %s\n' 503dc59a89b68578df9fbfedb65b357c4c1f854ed158b7a5722a79469802d486 "$archive" |
    sha256sum --check --strict
py="$previous/project/.venv/bin/python"
"$py" -m zipfile -e "$archive" "$stage/project"
cd "$stage/project"
sha256sum --check --strict SHA256SUMS > "$out/base-files.log"
while read -r file; do
    mkdir -p -- "$(dirname "$file")"
    cp -- "$repo/$file" "$file"
    cmp -- "$repo/$file" "$file"
    sha256sum -- "$file"
done <<'FILES' | tee "$out/source-overlays.sha256"
backend/app/api/routes/attachments.py
backend/app/api/routes/import_export.py
backend/app/api/schemas.py
backend/app/dependencies.py
backend/app/main.py
backend/app/services/attachment_validation.py
backend/app/services/attachment_staging.py
backend/app/services/attachment_promotion.py
backend/app/services/markdown.py
backend/app/services/markdown_item_repository.py
backend/app/services/attachments.py
backend/tests/test_attachment_staging.py
FILES
export PYTHONPATH="$stage/project/backend:$stage/project/knowledge-core/src"
unset DATABASE_URL EXPLAINLAB_PG_TEST_URL PGHOST PGHOSTADDR PGPORT PGUSER PGPASSWORD
unset PGPASSFILE PGSERVICE PGSERVICEFILE PGDATABASE PGOPTIONS
export LD_LIBRARY_PATH="$cluster/pg-root/usr/lib/$(uname -m)-linux-gnu:$cluster/pg-root/lib/$(uname -m)-linux-gnu"
export PGPASSFILE="$stage/pgpass"
findmnt -T "$stage" -o SOURCE,FSTYPE,TARGET
"$py" --version
"$py" -c 'from pathlib import Path; import app.main, knowledge_core; root=Path.cwd(); assert all(Path(m.__file__).is_relative_to(root) for m in (app.main, knowledge_core)); print(app.main.__file__, knowledge_core.__file__)'
"$pg/postgres" --version

run_suite() {
    local label=$1
    shift
    local rc=0
    (
        printf 'START UTC %s\nCommand:' "$(date -u +%FT%TZ)"
        printf ' %q' "$py" -m pytest -o addopts=--import-mode=importlib -ra -s \
            "--basetemp=$stage/pytest-$label" "--junitxml=$out/$label.xml" "$@"
        printf '\n'
        "$py" -m pytest -o addopts=--import-mode=importlib -ra -s \
            "--basetemp=$stage/pytest-$label" "--junitxml=$out/$label.xml" "$@"
    ) > "$out/$label.log" 2>&1 || rc=$?
    printf 'END UTC %s exit=%s\n' "$(date -u +%FT%TZ)" "$rc" >> "$out/$label.log"
    cat "$out/$label.log"
    return "$rc"
}

result=0
run_suite b3-posix-sqlite backend/tests/test_attachment_staging.py -k "not test_pg_concurrent_drafts_share_blob" || result=1
printf '%s\n' "Starting dedicated PG loopback cluster and creating $db"
"$pg/pg_ctl" -D "$data" -l "$stage/server.log" -w -t 20 \
    -o "-h 127.0.0.1 -p $port -k $cluster/pg-socket -c log_min_error_statement=panic" start
started=1
[[ $("$pg/psql" -X -h "$cluster/pg-socket" -p "$port" -d postgres -Atc 'show data_directory') == "$data" ]]
"$pg/createdb" -h "$cluster/pg-socket" -p "$port" -O "$role" -- "$db"
created=1
"$py" - "$cluster/pgpass" "$db" <<'PY'
from pathlib import Path
import os
import sys

old, db = sys.argv[1:]
host, port, _, role, password = Path(old).read_text().strip().split(":", 4)
assert host == "127.0.0.1" and role == "explainlab_b1_runner"
Path(os.environ["PGPASSFILE"]).write_text(f"{host}:{port}:{db}:{role}:{password}\n")
PY
export EXPLAINLAB_PG_TEST_URL="postgresql+psycopg://$role@127.0.0.1:$port/$db"
"$pg/psql" -X -h 127.0.0.1 -p "$port" -U "$role" -d "$db" \
    -Atc 'select version(), current_database(), current_user, inet_server_port()'
run_suite b3-postgresql backend/tests/test_attachment_staging.py::TestDraftImport::test_pg_concurrent_drafts_share_blob || result=1
"$pg/psql" -v ON_ERROR_STOP=1 -X -h 127.0.0.1 -p "$port" -U "$role" -d "$db" -Atc \
    "SELECT 'attachments=' || count(*) FROM attachment;
     SELECT 'advisory_locks=' || count(*) FROM pg_locks
     WHERE locktype='advisory' AND granted
       AND database=(SELECT oid FROM pg_database WHERE datname=current_database());" |
    tee "$out/db-after-http.log"
exit "$result"
