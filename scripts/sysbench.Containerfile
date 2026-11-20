FROM docker.io/library/debian:bookworm-slim
RUN apt-get update >/dev/null && apt-get install -y --no-install-recommends sysbench postgresql-client >/dev/null && sysbench --version
