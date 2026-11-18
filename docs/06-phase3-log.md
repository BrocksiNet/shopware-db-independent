# Phase 3 log: getting requests through on PostgreSQL

Running log of what each step needed.
State: lane `pg` on PostgreSQL, branch `poc/postgresql` in `instance/`.

## Step 1: id codec at the driver boundary

Problem: `GET /admin` failed with `invalid byte sequence for encoding "UTF8": 0xb7`.
The PHP side binds ids as 16 raw bytes (`Uuid::fromHexToBytes`), the column is `uuid`.

Change: `Adapter/Database/PostgreSQL/IdCodecMiddleware.php` (plus `IdCodecStatement`, `IdCodecResult`), a DBAL driver middleware registered by `PostgreSQLFactory`.

- Bound values: a 16 byte string bound as `BINARY` or `LARGE_OBJECT` becomes a 32 character hex string, which PostgreSQL accepts as `uuid` input.
  A 16 byte string bound as `STRING` is converted only if it is not valid UTF-8.
- Results: a value in canonical uuid form (36 characters, lower case, dashes) becomes 16 raw bytes.

Verified with a script against the copied data: lookup by binary id, `fetchFirstColumn`, an `IN (:ids)` list bound as `ArrayParameterType::BINARY`, and a 16 character text that must stay untouched.
No call site had to change.

Limits, both because the driver middleware API exposes no column or parameter types:

- An id whose 16 bytes happen to be valid UTF-8 and that is bound as `STRING` is not converted and the query fails.
  Call sites that bind ids without `ParameterType::BINARY` are therefore a finding of their own.
- A text column that holds a dashed uuid string would be turned into bytes on read.
- A type-driven codec needs an own driver (access to `PDOStatement::getColumnMeta`).

## Next error class: backticks

After step 1 both entry points fail on identifier quoting:

| Request | Error |
|---|---|
| `GET /admin` | syntax error at ``SELECT `app`.`name`, `app`.`version`, ...`` |
| `GET /` | syntax error at `` CONCAT(TRIM(TRAILING '/' FROM domain.url), '/') `key` `` |
