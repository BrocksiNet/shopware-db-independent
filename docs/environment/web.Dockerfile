# Dev web image plus the PostgreSQL PHP drivers.
FROM ghcr.io/shopware/docker-dev:php8.4-node24-caddy
USER root
RUN install-php-extensions pdo_pgsql pgsql
USER www-data
