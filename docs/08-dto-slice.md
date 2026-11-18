# DTO slice: newsletter recipient routes (phase 5)

Date: 2026-11-18.
Scope: subscribe, confirm and unsubscribe in `src/Core/Content/Newsletter/SalesChannel/`.
Goal: the routes know neither `Criteria` nor SQL, the store API contract stays unchanged, and the slice runs on MariaDB and PostgreSQL.

## Evaluation of the mapping options

Every row was run against the lane's web container unless marked otherwise.

| Option | Direction | Runnable example | Result |
|---|---|---|---|
| `#[MapRequestPayload]` (installed, `symfony/http-kernel` 7.4) | request body to DTO | `scripts/dto-eval/map-request-payload.php` | Works, but errors differ from the store API (see below). |
| Symfony Serializer `denormalize` (installed) | DB row to DTO | `scripts/dto-eval/serializer-row-to-dto.php` | Coerces enum and date, about 17 µs per row against about 1 µs for a constructor call. Unknown enum value throws `NotNormalizableValueException`. |
| Hand-written constructor call | DB row to DTO | same script | Fastest and explicit, used by the SQL adapter in the slice. |
| Symfony ObjectMapper (not installed, not in `composer.json`) | object to object | phase 1 scratch install, see `docs/inventory/dto/findings.md` part B | No type coercion (enum from string throws `TypeError`), needs a transform callable with three arguments. Only pays off for entity to DTO. Not re-run in this phase. |
| Generated DTOs of https://github.com/shopware/shopware/pull/17858 | API boundary | not run, the worktree has no `vendor/`; code read in phase 1 | Types request and response only; the route still builds a `Criteria` and the extension still exposes it. It does not give us a storage port. |

### `#[MapRequestPayload]` against today's store API errors

Invalid payload `{"email":"nope","option":"bogus"}`:

- Store API today (`POST /store-api/newsletter/subscribe`, run on the lane): status 400 and one error per violation, `code` `VIOLATION::INVALID_FORMAT_ERROR` and `VIOLATION::NO_SUCH_CHOICE_ERROR`, with `source.pointer` `/email` and `/option`.
- `#[MapRequestPayload]` (resolver run directly): `UnprocessableEntityHttpException` (422) wrapping a `ValidationFailedException` with the violations `email` and `option`.
- `ErrorResponseFactory::convertExceptionToError` (`src/Core/Framework/Api/EventListener/ErrorResponseFactory.php:80`) turns a generic Symfony exception into one error with `code` `"0"`, the exception's status and message. So 422 and a single error would replace 400 and per-field codes, unless a listener converts `ValidationFailedException` into `ConstraintViolationException`. I did not build that listener.
- A wrong type (`"email": ["x"]`) is a 422 with an empty property path, a missing field a 422 with property `email`, both different from today's codes.
- `BuildValidationEvent` (plugins add rules to the `DataValidationDefinition`) has no equivalent with attribute constraints on a DTO.

## Recommendation

1. Keep validation in `DataValidator` for store API routes for now.
   It keeps the error codes and `BuildValidationEvent` working; request DTOs are built after validation (`fromDataBag`).
   `#[MapRequestPayload]` is worth adopting for new routes only together with a listener that maps `ValidationFailedException` to the store API violation format.
2. Row to DTO: hand-written constructor in SQL adapters, a small `toDto` in the DAL adapter; no Serializer in hot paths, no ObjectMapper dependency.
3. The type boundary that matters is the storage port, not the HTTP layer; the generated DTOs of the pull request do not address it and can be adopted independently for the API surface.

## Slice design

New code, all `@internal`, under `src/Core/Content/Newsletter/Domain/`:

| File | Role |
|---|---|
| `NewsletterStatus` | backed enum (`notSet`, `optIn`, `optOut`, `direct`) |
| `NewsletterRecipient`, `NewsletterSalutation` | `final readonly` read model, no entity |
| `NewsletterRecipientWrite` | `final readonly` write model; a `null` optional field means "not provided" |
| `Request/SubscribeRequest`, `ConfirmRequest`, `UnsubscribeRequest` | `final readonly` request DTOs built from the validated `RequestDataBag` |
| `Response/NewsletterSubscribeResult` | response DTO (status enum); the wire shape `{status, success, apiAlias}` is produced by the unchanged `NewsletterSubscribeRouteResponse` |
| `NewsletterRecipientStorage` | port: `findByEmail`, `findByHash`, `upsert`, `confirm`, `optOut`, `findCustomerEmail` |
| `Dal/DalNewsletterRecipientStorage` | adapter on `EntityRepository`; default alias, fires written events and indexers |
| `Sql/SqlNewsletterRecipientStorage` | adapter on DBAL `Connection`, MySQL dialect only, no platform branch |
| `NewsletterRecipientEntityFactory` | bridge: the public events still carry `NewsletterRecipientEntity`, so the route builds one from the DTO |

The three routes keep their public signatures (`RequestDataBag`, extension points, rate limiter, events, responses).
Constructor change: the recipient and customer repositories are replaced by `NewsletterRecipientStorage` (DI in `newsletter_recipient.php`, alias `NewsletterRecipientStorage` to the DAL adapter).
The SQL adapter is not the default because it skips written events and indexers (for example the customer's newsletter sales channel ids), so it is not a drop-in replacement.

How the SQL adapter stays portable:

- `INSERT ... ON DUPLICATE KEY UPDATE ... VALUES(col)`, ids as `Uuid::fromHexToBytes`, `LOWER(HEX(id))` for reads: the PostgreSQL layer (upsert rewriter, id codec, compat functions) translates them, no `instanceof`.
- Datetimes are passed as strings in `Defaults::STORAGE_DATE_TIME_FORMAT` and parsed back as UTC.
- JSON columns are encoded and decoded in PHP.

Behaviour differences found while building it:

- The old subscribe flow loaded the recipient twice (ids, then entity); the new one loads it once before the write and once after.
- Optional profile fields are `null` = keep (an explicit `null` in the payload no longer clears a stored value).
- The unsubscribe update no longer re-writes the unchanged email; the unit test's expected payload lost that key.
- The salutation is resolved with the context language and the system language, not the full language chain (SQL adapter).
- Events receive an entity rebuilt from the DTO; fields outside the DTO (tags, associations) are not loaded.

## Proof

- Unit tests `tests/unit/Core/Content/Newsletter`: 75 tests, 272 assertions, green (MariaDB URL override). Fixtures were extended and the repository result queues adapted; one assertion changed (unsubscribe update payload, see above).
- Existing integration tests `tests/integration/Core/Content/Newsletter` (store API through the kernel, including error cases): 61 tests, 400 assertions, green on MariaDB with the DAL adapter, including the new storage test.
- New `tests/integration/Core/Content/Newsletter/Domain/NewsletterRecipientStorageTest.php`: the same cases for both adapters plus a check that both return equal read models (MariaDB).
- PostgreSQL: `scripts/dto-slice-smoke.sh dal|sql` runs subscribe, re-subscribe, invalid email, option and storefront URL, confirm (wrong `em`, unknown hash, success, twice) and unsubscribe (missing email, unknown, success) over HTTP on lane `pg`.
  The status codes, error codes and the final database row are identical for both adapters (diff of the outputs); the codes match the MariaDB integration tests (`VIOLATION::*`, `CONTENT__NEWSLETTER_RECIPIENT_NOT_FOUND`, `CONTENT__MISSING_EMAIL_PARAMETER`).
- Not done: PHPUnit on PostgreSQL (the test bootstrap installs on MySQL only), a PHPStan run (the analysis cache directory is missing in the container, it printed no result).

## Cost of migrating other routes

Counted in `src/Core` (non-abstract `*Route.php` under `SalesChannel` folders): 86 routes, 59 mention `Criteria`, 24 take a `RequestDataBag`.
This slice (3 routes, 12 new source files, 7 changed files, about +158/-215 lines in the changed files, plus about 250 lines of new tests) took one session including tests.
Per route, expect: one port with 3 to 6 methods, two adapters, request and response DTOs, and fixture work in the existing unit tests, which are tied to repository result queues.
Costs that do not shrink with routine: events that carry entities (needs the bridge or a BC break), extension points that expose `Criteria`, and plugins decorating the abstract routes.
Read-heavy routes (product listing, search) are a different problem: `Criteria` is the query language there, so a port would need its own query model; this slice does not show that cost.
