# Dev web image plus the PostgreSQL PHP drivers and the mongodb extension (wave 9 read store).
FROM ghcr.io/shopware/docker-dev:php8.4-node24-caddy
USER root
RUN install-php-extensions pdo_pgsql pgsql mongodb
USER www-data
