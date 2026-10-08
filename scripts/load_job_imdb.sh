#!/usr/bin/env bash
set -euo pipefail

CONTAINER="${CONTAINER:-postgres-lero}"
DB="${DB:-imdb}"
DATA_DIR="${DATA_DIR:-/job_data}"

TABLES=(
  comp_cast_type
  company_type
  info_type
  kind_type
  link_type
  role_type
  company_name
  keyword
  char_name
  name
  title
  aka_name
  aka_title
  complete_cast
  movie_link
  movie_companies
  movie_keyword
  movie_info_idx
  cast_info
  movie_info
  person_info
)

echo "Loading JOB IMDB CSVs into ${DB} on ${CONTAINER}..."

{
  for table in "${TABLES[@]}"; do
    echo "\\echo Loading ${table}..."
    echo "\\copy ${table} FROM '${DATA_DIR}/${table}.csv' csv escape '\\'"
  done
} | docker exec -i "${CONTAINER}" psql -U postgres -d "${DB}" -v ON_ERROR_STOP=1

echo "Done loading all tables."
