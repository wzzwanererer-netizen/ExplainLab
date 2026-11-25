#!/usr/bin/env bash
set -euo pipefail
umask 077
repo=/mnt/d/ExplainLab
out=$(mktemp -d "$repo/docs/acceptance/V2-Final-Closure/evidence/closure-posix-pg.XXXXXXXX")
exec > >(tee "$out/driver.log") 2>&1
printf 'START UTC %s\nEvidence: %s\n' "$(date -u +%FT%TZ)" "$out"
previous="$HOME/explainlab-b1.u4iXLEhT"
cluster="$previous/acceptance.R3sYC6uE"
stage=$(mktemp -d "$HOME/explainlab-v2-closure.XXXXXXXX")
pg="$cluster/pg-root/usr/lib/postgresql/18/bin"
data="$cluster/pg-data"
port=59927
role=explainlab_b1_runner
started=0
databases=()
finish() {
    local rc=$?
    trap - EXIT
    local test_db
    for test_db in "${databases[@]}"; do
        "$pg/dropdb" -h "$cluster/pg-socket" -p "$port" -- "$test_db" || rc=1
    done
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
backend/app/api/routes/governance.py
backend/app/api/schemas.py
backend/app/dependencies.py
backend/app/main.py
backend/app/db/orphan_scan_lock.py
backend/app/core/config.py
backend/app/db/session.py
backend/app/services/repositories_v2.py
backend/app/services/attachment_maintenance.py
backend/app/services/attachment_validation.py
backend/app/services/attachment_staging.py
backend/app/services/attachment_promotion.py
backend/app/services/markdown.py
backend/app/services/markdown_item_repository.py
backend/app/services/import_review_hook.py
backend/app/services/retrieval.py
backend/app/services/source_identity.py
backend/app/services/attachments.py
backend/tests/test_attachment_staging.py
backend/tests/test_attachment_review.py
backend/tests/test_attachment_api.py
backend/tests/test_attachment_validation.py
backend/tests/test_attachment_maintenance.py
backend/tests/test_attachment_pg.py
backend/tests/test_storage_lock_pg.py
backend/tests/test_v2_closure_gc_orp.py
backend/tests/test_v2_closure_pg_index_faults.py
FILES
export PYTHONPATH="$stage/project/backend:$stage/project/knowledge-core/src"
unset DATABASE_URL EXPLAINLAB_PG_TEST_URL PGHOST PGHOSTADDR PGPORT PGUSER PGPASSWORD
unset PGPASSFILE PGSERVICE PGSERVICEFILE PGDATABASE PGOPTIONS
export LD_LIBRARY_PATH="$cluster/pg-root/usr/lib/$(uname -m)-linux-gnu:$cluster/pg-root/lib/$(uname -m)-linux-gnu"
export PGPASSFILE="$stage/pgpass"
findmnt -T "$stage" -o SOURCE,FSTYPE,TARGET
"$py" --version
"$pg/postgres" --version

run_suite() {
    local label=$1
    shift
    local rc=0
    (
        printf 'START UTC %s\nCommand:' "$(date -u +%FT%TZ)"
        printf ' %q' "$py" -m pytest -o addopts=--import-mode=importlib -ra -s \
            -o log_cli=true -o log_cli_level=INFO \
            "--basetemp=$stage/pytest-$label" "--junitxml=$out/$label.xml" "$@"
        printf '\n'
        "$py" -m pytest -o addopts=--import-mode=importlib -ra -s \
            -o log_cli=true -o log_cli_level=INFO \
            "--basetemp=$stage/pytest-$label" "--junitxml=$out/$label.xml" "$@"
    ) > "$out/$label.log" 2>&1 || rc=$?
    printf 'END UTC %s exit=%s\n' "$(date -u +%FT%TZ)" "$rc" >> "$out/$label.log"
    cat "$out/$label.log"
    return "$rc"
}

result=0
run_suite closure-posix-sqlite backend/tests/test_v2_closure_gc_orp.py -k "not test_pg_" || result=1

printf '%s\n' "Starting dedicated PG loopback cluster"
"$pg/pg_ctl" -D "$data" -l "$stage/server.log" -w -t 20 \
    -o "-h 127.0.0.1 -p $port -k $cluster/pg-socket -c log_min_error_statement=panic" start
started=1
[[ $("$pg/psql" -X -h "$cluster/pg-socket" -p "$port" -d postgres -Atc 'show data_directory') == "$data" ]]
"$pg/postgres" --version
suffix=$(printf '%s' "${stage##*.}" | tr '[:upper:]' '[:lower:]')

create_test_db() {
    local prefix=$1
    db="${prefix}${suffix}"
    "$pg/createdb" -h "$cluster/pg-socket" -p "$port" -O "$role" -- "$db"
    databases+=("$db")
    "$py" - "$cluster/pgpass" "$db" <<'PY'
from pathlib import Path
import os
import sys

old, db = sys.argv[1:]
host, port, _, role, password = Path(old).read_text().strip().split(":", 4)
assert host == "127.0.0.1" and role == "explainlab_b1_runner"
with Path(os.environ["PGPASSFILE"]).open("a") as file:
    file.write(f"{host}:{port}:{db}:{role}:{password}\n")
PY
    export EXPLAINLAB_PG_TEST_URL="postgresql+psycopg://$role@127.0.0.1:$port/$db"
    "$pg/psql" -X -h 127.0.0.1 -p "$port" -U "$role" -d "$db" -Atc \
        'select current_database(), current_user, inet_server_port()'
}

create_test_db explainlab_closure_gc02_
run_suite closure-pg-gc02 backend/tests/test_v2_closure_gc_orp.py -k test_pg_gc02 || result=1

create_test_db explainlab_closure_orp01_
run_suite closure-pg-orp01 backend/tests/test_v2_closure_gc_orp.py -k test_pg_orp01 || result=1

create_test_db explainlab_closure_orp05_
run_suite closure-pg-orp05 backend/tests/test_v2_closure_gc_orp.py -k test_pg_orp05 || result=1

create_test_db explainlab_closure_idx_
run_suite closure-pg-index-faults backend/tests/test_v2_closure_pg_index_faults.py || result=1

create_test_db explainlab_b4_http_cl_
run_suite closure-pg-review backend/tests/test_attachment_review.py \
    -k "test_pg_review_approval_commits_and_releases_advisory_lock or test_pg_review_hook_all_breakpoints" || result=1

create_test_db explainlab_b5_http_cl_
run_suite closure-pg-e2e backend/tests/test_attachment_maintenance.py \
    -k test_pg_gc_and_orphan_scan_leadership || result=1

"$pg/psql" -v ON_ERROR_STOP=1 -X -h 127.0.0.1 -p "$port" -U "$role" -d "$db" -Atc \
    "SELECT 'attachments=' || count(*) FROM attachment;
     SELECT 'advisory_locks=' || count(*) FROM pg_locks
     WHERE locktype='advisory' AND granted
       AND database=(SELECT oid FROM pg_database WHERE datname=current_database());" |
    tee "$out/db-after-e2e.log"

create_test_db explainlab_v2_reg_cl_
run_suite closure-pg-regression backend/tests/*_pg.py || result=1

exit "$result"
