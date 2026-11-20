FROM docker.io/library/alpine:latest
RUN apk add --no-cache bash build-base autoconf automake libtool pkgconf git postgresql-dev mariadb-connector-c-dev mariadb-dev libaio-dev luajit-dev openssl-dev ck-dev 2>&1 | tail -1 || true
RUN git clone --depth 1 --branch 1.0.20 https://github.com/akopytov/sysbench /sb && cd /sb && ./autogen.sh && ./configure --with-pgsql --with-mysql --without-gcc-arch >/dev/null && make -j4 >/dev/null 2>&1 && make install
RUN apk add --no-cache postgresql-client libpq mariadb-connector-c libaio luajit libstdc++ >/dev/null
