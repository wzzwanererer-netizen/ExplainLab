#!/usr/bin/env bash
set -euo pipefail
umask 077
run=$(realpath -e -- "$1")
attempt="$run/acceptance.R3sYC6uE"
[[ $(dirname "$run") == "$(realpath -e -- "$HOME")" ]]
[[ $(findmnt -n -T "$attempt/pg-data" -o FSTYPE) == ext4 ]]
[[ ! -e "$attempt/pg-data/postmaster.pid" ]]
dest=/mnt/d/ExplainLab/docs/acceptance/V2-A1-04-Batch-B-B1-environment-recovery/evidence
probe=$(mktemp -d "$attempt/release-filesystem.XXXXXXXX")
out="$dest/${probe##*/}"
mkdir -- "$out"
pg="$attempt/pg-root/usr/lib/postgresql/18/bin"
export LD_LIBRARY_PATH="$attempt/pg-root/usr/lib/$(uname -m)-linux-gnu:$attempt/pg-root/lib/$(uname -m)-linux-gnu"
unset DATABASE_URL EXPLAINLAB_PG_TEST_URL PGHOST PGHOSTADDR PGPORT PGUSER PGPASSWORD PGSERVICE PGSERVICEFILE PGDATABASE PGOPTIONS
export PGPASSFILE="$attempt/pgpass"
data="$attempt/pg-data"
port=59927
export EXPLAINLAB_PG_TEST_URL="postgresql+psycopg://explainlab_b1_runner@127.0.0.1:$port/explainlab_b1_acceptance"
(
    finish() {
        local rc=$?
        trap - EXIT
        if [[ -f "$data/postmaster.pid" ]]; then
            "$pg/pg_ctl" -D "$data" -m fast -w -t 20 stop || { if [[ $rc == 0 ]]; then rc=1; fi; }
        fi
        if [[ -f "$probe/server.log" ]]; then cp -- "$probe/server.log" "$out/server.log"; fi
        printf 'Release/EXDEV exit=%s\nEvidence: %s\n' "$rc" "$out"
        exit "$rc"
    }
    trap finish EXIT
    date -u +%FT%TZ
    set -x
    "$pg/pg_ctl" -D "$data" -l "$probe/server.log" -w -t 20 \
        -o "-h 127.0.0.1 -p $port -k $attempt/pg-socket -c log_min_error_statement=panic" start
    actual=$("$pg/psql" -X -h "$attempt/pg-socket" -p "$port" -d postgres -Atc 'show data_directory')
    [[ $actual == "$data" ]]
    cd "$run/project"
    .venv/bin/python -u "$dest/release-filesystem-probe.py" "$probe"
) 2>&1 | tee "$out/probe.log"
