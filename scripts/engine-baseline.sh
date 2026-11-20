#!/bin/sh
# Engine baseline (docs/22): sysbench and pgbench on the same containers, scratch databases sysbench_*, persistent connections.
# usage: scripts/engine-baseline.sh create|prepare|run <mariadb|mysql|pg> <test> <threads> <seconds>|pgbench init|S|SC|tpcb|tpcbC [<clients> <seconds>]|drop
# images: podman build -t sysbench-pg-arm -f scripts/sysbench.Containerfile /tmp   (Debian sysbench 1.0.20, mysql and pgsql drivers, aarch64)
#         pgbench from docker.io/library/postgres:18-alpine (same version as the server)
set -eu
IMG=localhost/sysbench-pg-arm
NET=instance_default
TABLES=${TABLES:-8}
SIZE=${SIZE:-100000}
common() {
    case $1 in
        mariadb) echo "--db-driver=mysql --mysql-host=database --mysql-user=root --mysql-password=root --mysql-db=sysbench_mariadb" ;;
        mysql) echo "--db-driver=mysql --mysql-host=mysql --mysql-user=root --mysql-password=root --mysql-db=sysbench_mysql" ;;
        pg) echo "--db-driver=pgsql --pgsql-host=postgres --pgsql-user=shopware --pgsql-password=shopware --pgsql-db=sysbench_pg" ;;
    esac
}
sb() { podman run --rm --network $NET $IMG sysbench "$@"; }
case $1 in
    create)
        podman exec instance-database-1 mariadb -uroot -proot -e "CREATE DATABASE IF NOT EXISTS sysbench_mariadb"
        podman exec instance-mysql-1 mysql -uroot -proot -e "CREATE DATABASE IF NOT EXISTS sysbench_mysql" 2>/dev/null
        podman exec instance-postgres-1 psql -U shopware -d postgres -c "CREATE DATABASE sysbench_pg" ;;
    prepare) for db in mariadb mysql pg; do sb $(common $db) --tables=$TABLES --table-size=$SIZE oltp_read_write prepare; done ;;
    run) # run <db> <test> <threads> <seconds>
        sb $(common $2) --tables=$TABLES --table-size=$SIZE --threads=$4 --time=$5 --report-interval=0 $3 run ;;
    pgbench) # pgbench <db> init|S|tpcb|SC|tpcbC <clients> <seconds>
        P="podman run --rm --network $NET -e PGPASSWORD=shopware docker.io/library/postgres:18-alpine pgbench -h postgres -U shopware sysbench_pg"
        case $2 in
            init) $P -i -s ${SCALE:-10} ;;
            S) $P -S -n -c $3 -j $3 -T $4 ;;
            tpcb) $P -n -c $3 -j $3 -T $4 ;;
            SC) $P -S -n -C -c $3 -j $3 -T $4 ;;
            tpcbC) $P -n -C -c $3 -j $3 -T $4 ;;
        esac ;;
    drop)
        podman exec instance-database-1 mariadb -uroot -proot -e "DROP DATABASE IF EXISTS sysbench_mariadb"
        podman exec instance-mysql-1 mysql -uroot -proot -e "DROP DATABASE IF EXISTS sysbench_mysql" 2>/dev/null
        podman exec instance-postgres-1 psql -U shopware -d postgres -c "DROP DATABASE IF EXISTS sysbench_pg" ;;
esac
