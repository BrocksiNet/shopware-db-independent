-- Verification against the PostgreSQL schema produced by generated-pg-schema.sql
\echo tables
select count(*) from information_schema.tables where table_schema='scratch_schema_agent' and table_type='BASE TABLE';
\echo columns
select count(*) from information_schema.columns where table_schema='scratch_schema_agent';
\echo indexes total (incl. PK) / primary / unique-nonpk
select count(*) from pg_indexes where schemaname='scratch_schema_agent';
select count(*) filter (where contype='p') pk, count(*) filter (where contype='f') fk, count(*) filter (where contype='c') chk, count(*) filter (where contype='u') uq from pg_constraint c join pg_namespace n on n.oid=c.connamespace where n.nspname='scratch_schema_agent';
\echo column types
select data_type, count(*) from information_schema.columns where table_schema='scratch_schema_agent' group by 1 order by 2 desc;
\echo generated / identity / triggers
select count(*) from information_schema.columns where table_schema='scratch_schema_agent' and is_generated='ALWAYS';
select count(*) from information_schema.columns where table_schema='scratch_schema_agent' and is_identity='YES';
select count(*) from information_schema.triggers where trigger_schema='scratch_schema_agent';
\echo case-insensitive unique smoke test
set search_path to scratch_schema_agent;
begin;
insert into currency(id,factor,symbol,iso_code,position,item_rounding,total_rounding,created_at) values (gen_random_uuid(),1,'x','EUR',1,'{}','{}',now());
insert into currency(id,factor,symbol,iso_code,position,item_rounding,total_rounding,created_at) values (gen_random_uuid(),1,'x','eur',1,'{}','{}',now());
rollback;
