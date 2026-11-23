# DAL v2: batched update on PostgreSQL

Docs 33 to 35 report that the DAL v2 batched update (lever W1b) does not engage on PostgreSQL: S4 stays at 123 statements, as the DAL.
They give the reason as "PostgreSQL types an untyped `CASE` as text, so the `CASE` needs a cast per column type".
That reason is wrong.
This document gives the real cause, the fix and new S4 timings.
Code: instance branch `poc/orm-spike`, commit `bda47928e8d`.
Timing script: `scripts/orm-spike-case-block.sh`.

## Cause

The batched statement of `WriteGatewayV2::executeBatchedUpdate` had this shape:

```sql
UPDATE "product" SET "stock" = CASE WHEN "id" = ? AND "version_id" = ? THEN ? ... ELSE "stock" END
WHERE ("id" = ? AND "version_id" = ?) OR ...
```

On PostgreSQL the PoC sends every statement through the MySQL to PostgreSQL translator (`MySQLToPostgreSQLTranslator`).
The translator treats a double-quoted token as a MySQL string literal unless its position only allows an identifier (`isQuotedIdentifier`: after `FROM`, `JOIN`, `SET`, `WHERE`, `AND`, `ON` and a few more, or next to a dot).
`WHEN`, `THEN` and `ELSE` are not in that list, so `WHEN "id" = ?` became `WHEN 'id' = ?` and `ELSE "stock"` became `ELSE 'stock'`.
With every branch a literal or a parameter, PostgreSQL resolves the `CASE` to `text`, which gives the error seen in doc 33: `column "stock" is of type integer but expression is of type text`.
The gateway therefore had a PostgreSQL fallback to per-row updates for every non-integer column, and that fallback fired for the product update.

PostgreSQL itself needs no cast here.
Sent without the translator (raw PDO) and through the app connection, `CASE WHEN id = ? THEN ? ... ELSE stock END` runs with integer and string parameters, because the parameters take the type of the typed `ELSE stock` branch.

## Fix

The gateway now qualifies every column inside the `CASE` with the table: `WHEN "product"."id" = ?` and `ELSE "product"."stock"`.
A token next to a dot is always an identifier for the translator, and the statement is still valid on MySQL, MariaDB and SQLite.
The PostgreSQL fallback and its platform check are removed.
The translator is not changed: reading `THEN "x"` and `ELSE "x"` as identifiers would break real MySQL string literals in those positions.

## Verification

`orm-spike:bench --impl=dalv2 --scenario=S4 --verify --option write=key+upd`, and the same with all write and count levers, give `OK (dalv2 equals dal)` on MySQL, MariaDB, PostgreSQL and SQLite.

Statements per S4 call with DAL v2:

| Engine | before | after |
|---|---|---|
| MySQL | 23 | 23 |
| MariaDB | 23 | 23 |
| PostgreSQL | 123 | 25 |
| SQLite | 23 | 23 |

PostgreSQL has two statements more than the other engines.
The `REPLACE INTO product_category` becomes a `DELETE` plus an `INSERT` (`UpsertRewriter` of the PoC), and one primary key introspection query (`SELECT i.indexrelid ...`) is sent.
In the SQL log of one call, the two batched updates take 3.45 ms (`product`) and 2.50 ms (`product_translation`) on PostgreSQL.

## Conditions

Same protocol as docs 34 and 35: timing lock held, the 48 other podman lanes stopped and restarted afterwards, `APP_ENV=prod`, own cache directory per engine plus `cache:clear`, `--verify` before timing, 50 measured iterations after 5 warm-up iterations, S4 only.
Run 2026-11-23 13:15 to 13:19.
Load averages (1, 5, 15 min): start 9.44 8.66 7.67, PostgreSQL 7.46 8.21 7.56, end 10.21 8.77 7.88.
The load was higher than in doc 35, so compare within this table first and with doc 35 only roughly.

## Results

Median and p95 in ms, S4.
"Doc 35" is DAL v2 with `count=window agg=stats write=key+upd` from doc 35, runs 1 and 2.

| Engine | dal | dalv2 `write=key+upd` | dalv2 `count=window agg=stats write=key+upd` | p95 of the last | stmts dal / dalv2 | Doc 35 |
|---|---|---|---|---|---|---|
| MySQL | 93.67 | 52.31 | 51.58 | 63.10 | 371 / 23 | 52.09 / 46.51 |
| MariaDB | 105.01 | 55.75 | 55.78 | 69.71 | 371 / 23 | 53.74 / 52.18 |
| PostgreSQL | 84.46 | 74.27 | 68.76 | 76.89 | 123 / 25 | 85.12 / 81.62 |
| SQLite | 338.63 | 317.58 | 350.80 | 392.36 | 371 / 23 | 301.02 / 292.18 |

Reading the numbers:

- PostgreSQL: DAL v2 goes from level with the DAL (doc 35: 1.03 and 0.96 of the DAL) to 0.81 to 0.88 of the DAL in this block, 68.76 ms against 84.46 ms.
  That is the first DAL v2 write gain on PostgreSQL.
  It is about 10 to 16 ms, less than on MySQL and MariaDB (about 40 to 50 ms), because the key bug of W1a never existed on PostgreSQL and the DAL already sends 123 statements there, not 371.
  It is in the range of the full ORM variants of doc 35 on PostgreSQL (62.73 to 68.88 ms), measured under a different load.
- MySQL and MariaDB: unchanged against doc 35 within the noise; the fix does not change their statements.
- SQLite: unchanged, the 5 ms per row of the `UPDATE product` from doc 33 is still open and is not related to this fix.

## Docs corrected

Docs 29, 33 and 35 and the issue draft E3.04 now point here instead of naming missing casts as the reason.
For E2.01 (batching the single row updates of the product indexer updaters) this means: a batched `CASE` needs no cast on PostgreSQL as long as one branch is typed by the column, for example `ELSE <column>`.
