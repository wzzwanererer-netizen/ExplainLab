#!/usr/bin/env bash
set -euo pipefail
umask 077
repo=/mnt/d/ExplainLab
evidence="$repo/docs/acceptance/V2-A1-04-Batch-B-B1-final-verification-round/evidence"
previous="$HOME/explainlab-b1.u4iXLEhT"
cluster="$previous/acceptance.R3sYC6uE"
out=$(mktemp -d "$evidence/wsl-final.XXXXXXXX")
exec > >(tee "$out/driver.log") 2>&1
printf 'START UTC %s\nEvidence: %s\n' "$(date -u +%FT%TZ)" "$out"
stage=$(mktemp -d "$HOME/explainlab-b1-final.XXXXXXXX")
pg="$cluster/pg-root/usr/lib/postgresql/18/bin"
data="$cluster/pg-data"
started=0
finish() {
    local rc=$?
    trap - EXIT
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
sha256sum --check --strict SHA256SUMS > "$out/baseline-sha256.log"
for name in test_attachment_storage test_attachment_windows test_attachment_pg test_storage_lock_pg; do
    file="backend/tests/$name.py"
    cp -- "$repo/$file" "$file"
    cmp -- "$repo/$file" "$file"
    sha256sum -- "$file"
done | tee "$out/round-test-sha256.log"
export PYTHONPATH="$stage/project/backend:$stage/project/knowledge-core/src"
unset DATABASE_URL EXPLAINLAB_PG_TEST_URL PGHOST PGHOSTADDR PGPORT PGUSER PGPASSWORD
unset PGPASSFILE PGSERVICE PGSERVICEFILE PGDATABASE PGOPTIONS
findmnt -T "$stage" -o SOURCE,FSTYPE,TARGET
findmnt -T /dev/shm -o SOURCE,FSTYPE,TARGET
"$py" --version
"$py" -c 'from pathlib import Path; import app.main, knowledge_core; import sys; root=Path.cwd(); assert all(Path(m.__file__).is_relative_to(root) for m in (app.main, knowledge_core)); print(sys.executable, app.main.__file__, knowledge_core.__file__)'

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
run_suite t01-linux backend/tests/test_attachment_storage.py::test_t01_linux_lifespan_rejects_real_separate_mount || result=1

export LD_LIBRARY_PATH="$cluster/pg-root/usr/lib/$(uname -m)-linux-gnu:$cluster/pg-root/lib/$(uname -m)-linux-gnu"
export PGPASSFILE="$cluster/pgpass"
port=59927
export EXPLAINLAB_PG_TEST_URL="postgresql+psycopg://explainlab_b1_runner@127.0.0.1:$port/explainlab_b1_acceptance"
test -r "$PGPASSFILE"
"$pg/postgres" --version | grep -F '18.6'
printf 'Starting dedicated PG cluster on loopback port %s\n' "$port"
started=1
"$pg/pg_ctl" -D "$data" -l "$stage/server.log" -w -t 20 \
    -o "-h 127.0.0.1 -p $port -k $cluster/pg-socket -c log_min_error_statement=panic" start
[[ $("$pg/psql" -X -h "$cluster/pg-socket" -p "$port" -d postgres -Atc 'show data_directory') == "$data" ]]
"$pg/psql" -X -h 127.0.0.1 -p "$port" -U explainlab_b1_runner -d explainlab_b1_acceptance \
    -Atc 'select version(), current_database(), current_user, inet_server_port()'
run_suite t04-postgresql backend/tests/test_attachment_pg.py || result=1
run_suite lck07-postgresql backend/tests/test_storage_lock_pg.py::test_lck07_pg_client_process_death_releases_advisory_lock || result=1
run_suite pg-lock-regression backend/tests/test_storage_lock_pg.py -k 'not client_process_death' || result=1
exit "$result"
