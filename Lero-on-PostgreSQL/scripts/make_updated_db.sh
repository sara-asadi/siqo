#!/usr/bin/env bash
# Build imdb_upd: a copy of imdb after a large data update, for robustness tests.
# Update = delete every movie with production_year > CUTOFF_YEAR (~40% of title at 2005)
# and all rows referencing it, then VACUUM FULL + ANALYZE so table sizes and stats change.
# The original imdb database is not modified.
# Usage: CUTOFF_YEAR=2005 ./scripts/make_updated_db.sh
set -euo pipefail

CUTOFF_YEAR="${CUTOFF_YEAR:-2005}"
SRC_DB="${SRC_DB:-imdb}"
DST_DB="${DST_DB:-imdb_upd}"
psql_in() { docker exec -i -e PGPASSWORD=postgres postgres-lero psql -U postgres -v ON_ERROR_STOP=1 "$@"; }

echo "==> Copy ${SRC_DB} -> ${DST_DB}"
psql_in -d postgres -c "DROP DATABASE IF EXISTS ${DST_DB};"
# CREATE DATABASE ... TEMPLATE fails while other sessions use the source; retry briefly
for i in $(seq 1 30); do
  psql_in -d postgres -c "CREATE DATABASE ${DST_DB} TEMPLATE ${SRC_DB};" && break
  sleep 10
done

echo "==> Delete movies with production_year > ${CUTOFF_YEAR}"
psql_in -d "${DST_DB}" <<SQL
\timing on
CREATE TEMP TABLE del_ids AS SELECT id FROM title WHERE production_year > ${CUTOFF_YEAR};
CREATE INDEX ON del_ids (id);
ANALYZE del_ids;
DELETE FROM cast_info x USING del_ids d WHERE x.movie_id = d.id;
DELETE FROM movie_info x USING del_ids d WHERE x.movie_id = d.id;
DELETE FROM movie_info_idx x USING del_ids d WHERE x.movie_id = d.id;
DELETE FROM movie_keyword x USING del_ids d WHERE x.movie_id = d.id;
DELETE FROM movie_companies x USING del_ids d WHERE x.movie_id = d.id;
DELETE FROM complete_cast x USING del_ids d WHERE x.movie_id = d.id;
DELETE FROM aka_title x USING del_ids d WHERE x.movie_id = d.id;
DELETE FROM movie_link x USING del_ids d WHERE x.movie_id = d.id OR x.linked_movie_id = d.id;
DELETE FROM title x USING del_ids d WHERE x.id = d.id;
SQL

echo "==> VACUUM FULL + ANALYZE"
psql_in -d "${DST_DB}" -c "VACUUM FULL;" -c "ANALYZE;"

psql_in -d postgres -Atc "SELECT pg_size_pretty(pg_database_size('${SRC_DB}')), pg_size_pretty(pg_database_size('${DST_DB}'));"
for db in "${SRC_DB}" "${DST_DB}"; do
  echo "--- ${db}"
  psql_in -d "${db}" -Atc "SELECT relname, relpages, reltuples::bigint FROM pg_class
    WHERE relkind='r' AND relnamespace='public'::regnamespace AND relpages > 100 ORDER BY relname;"
done
