# Install without manual steps, translator fixes, native quoting

Wave 4, handoff C.
All numbers below come from runs in this session.

## 1. mysql-compat.sql loaded by the installer

`SetupDatabaseAdapter::initializeShopwareDb()` loads `PostgreSQL/mysql-compat.sql` on PostgreSQL before `schema.sql`; the file is idempotent.
`system:install` and the PHPUnit bootstrap (which runs `system:install` on `<db>_test`) therefore need no manual step.
The `if postgresql` block that applied the file by hand is removed from `scripts/switch-db.sh`.
Switch harness results: PostgreSQL pass (25.0 s, 0 failed steps), MySQL pass (39.2 s), MariaDB pass (24.5 s).

## 2. system:install on SQLite

`DatabaseConnectionInformation::fromEnv` and the connection factory accept `sqlite:///path`; `SetupDatabaseAdapter` drops by emptying the file and does not delete it.
`system:install --basic-setup` on SQLite ends with return code 0.
Result: 910 regular and 910 destructive migrations (same count as PostgreSQL), 250 tables, 1 admin user, 2 sales channels.
Storefront `/` and `/account/login` returned 200 and the admin OAuth token worked.
The SQLite SQL rewriter needed fixes on the way (generated columns, `UPDATE t AS alias`, `JSON_TYPE(JSON_EXTRACT())`, composite UNIQUE, `rowCount`).

## 3. The # operator

`#>` and `#>>` are kept as operators; real MySQL `#` comments are still stripped.
Unit tests added in `MySQLToPostgreSQLTranslatorTest`.

## 4. Native quoting

The translator now reads already double-quoted PostgreSQL identifiers.
Everything else in double quotes stays a MySQL string literal.
A double-quoted token is an identifier when its content looks like an identifier and the position says so:

- next to a dot, after a quote or `)`;
- in a column list after `INTO t (` or `ON CONFLICT (`;
- after FROM, JOIN, INTO, UPDATE, TABLE, SET, BY, DISTINCT, ONLY, EXISTS, WHERE, AND, OR, ON, HAVING, SELECT;
- before AS, FROM, ASC, DESC;
- in a select list before FROM, in an UPDATE SET list, in a tuple compared with IN or `=`;
- as the first argument of a function (COALESCE, LOWER, MAX, JSON_*, CAST and similar) and of any function when the content has a dot.

Identifiers over 63 bytes are still shortened.
`PostgreSqlDialect::quoteIdentifier()` now defaults to double quotes (`nativeIdentifiers = true`); backticks remain available through the constructor flag.
The position rules are a heuristic; a string literal that looks like an identifier in one of these positions would be misread.
Unit tests: translator 185 tests, 417 assertions, OK.
Migration check `scripts/check-migrations-on-postgresql.sh`: 910, 910, 910 migrations, columns 2168 of 2168, indexes 726 of 726, constraints 1878 of 1878, 0 differences.
Four unit test classes were made dialect neutral (they hard-coded backticks).

## 5. EntitySearcherTest ordering

`testSearchFiltersByTranslatedFieldsByApplyingInheritanceAndLanguageOverridesPreferringOwnTranslation` now sorts by `productNumber`.
A scan of the DAL integration tests for `assertSame` and `assertEquals` over two or more ids from `getIds()` without a sorting found no other such test.
The scan is a text heuristic, not a proof.
The class passes on MySQL (12 tests, 18 assertions).
On PostgreSQL the target test passes; other tests of the class fail in some runs (see below).

## Ids fixed on behalf of handoff D

Handoff D binds ids as hex strings on PostgreSQL, which broke three call sites that still bound bytes.
They now use `IdBinding`: `MediaFileExtensionWriteValidator`, `CustomerEmailUniqueSubscriber`, `PromotionValidator`.

## DAL integration tests on PostgreSQL

Full directory `tests/integration/Core/Framework/DataAbstractionLayer`, 801 tests, own database `shopware_c_test`.

| Run | Errors | Failures | Risky | Errors plus failures |
|---|---|---|---|---|
| Wave 3 baseline | | | | 168 |
| Native quoting (default) | 117 | 74 | 34 | 191 |
| Backticks (temporary env switch, since removed) | 113 | 74 | 34 | 187 |

The result is not better than the baseline: 191 against 168.
Native quoting adds about 4 problems against backticks in this run, among them `EntitySearcherTest` term search and `EntityWriteGatewayTest` change set tests; they were not analysed further and the runs overlapped with handoff D's uncommitted write gateway edits, so the 4 may be noise.
Categories seen in the native run, none of which I traced to quoting:

- 34 risky tests and "transaction was not closed" cascading from `SetNullOnDeleteTest`;
- 32 `WriteTypeIntendException` in `JoinFilterTest` and 8 `InvalidUuidLengthException` in `UpdatedByFieldTest` (hex write ids, handoff D);
- 14 `ProductTypeImmutableTest`;
- about 26 "Unmapped MySQL type key" from the DDL rewriter on named primary keys in test-created tables;
- 10 `EntityAggregatorTest` GROUP BY, 8 `CriteriaQueryHelperTest`, 7 foreign key violations in `EntityRepositoryTest`;
- 8 to 10 `EntitySearcherTest` integer cast of a decimal value;
- 3 `SET @n` syntax errors, 2 `jsonb_path_query_first`, 1 boolean `AND`.

## Unit tests

Full unit suite on PostgreSQL before the test fixes: 24337 tests, 20 failures (quoting expectations, 3 Thumbnail tests, `ManyToManyAssociationServiceTest`, 3 `EntityForeignKeyResolverTest` id shape).
After the fixes the four neutral test classes pass on MySQL (88 tests) and on PostgreSQL except the 3 id shape failures of handoff D.
The last full run on MySQL had 5 failures, 3 of them Thumbnail tests that fail on both databases.
The full suite was not rerun after the final fixes.

## Open

- DAL integration tests are at 191 against 168; the gap is not closed and not attributed.
- `EntityForeignKeyResolverTest` (3) and `ManyToManyAssociationServiceTest` on PostgreSQL depend on the id work of handoff D.
- `EntitySearcherTest` still has PostgreSQL failures in the term search (integer cast).
