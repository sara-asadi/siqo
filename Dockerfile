FROM ubuntu:22.04

ENV DEBIAN_FRONTEND=noninteractive

# 👇 IMPORTANT: make PostgreSQL binaries visible everywhere
ENV PATH="/usr/local/pgsql/bin:$PATH"

# 1. Install build dependencies
RUN apt-get update && apt-get install -y \
    wget \
    build-essential \
    libreadline-dev \
    zlib1g-dev \
    flex \
    bison \
    libxml2-dev \
    libxslt1-dev \
    git \
    ca-certificates

# 2. Download PostgreSQL 13.1 source
WORKDIR /build
RUN wget https://ftp.postgresql.org/pub/source/v13.1/postgresql-13.1.tar.bz2 \
    && tar -xvf postgresql-13.1.tar.bz2

WORKDIR /build/postgresql-13.1

# 3. Copy and apply patch
COPY 0001-init-lero.patch /build/
RUN git apply /build/0001-init-lero.patch || patch -p1 < /build/0001-init-lero.patch

# 4. Build & install (IMPORTANT: explicit prefix)
RUN ./configure --prefix=/usr/local/pgsql \
    && make -j$(nproc) \
    && make install

# 5. Create postgres user + data dir
RUN useradd -m postgres \
    && mkdir -p /var/lib/postgresql/data \
    && chown -R postgres:postgres /var/lib/postgresql

USER postgres

# 6. Init DB (now works because PATH is set)
RUN initdb -D /var/lib/postgresql/data

# 7. Config (will be overridden by compose anyway)
COPY postgresql.conf /var/lib/postgresql/data/postgresql.conf

EXPOSE 5432

# 8. Start server (use PATH, not hardcoded path)
CMD ["postgres", "-D", "/var/lib/postgresql/data"]