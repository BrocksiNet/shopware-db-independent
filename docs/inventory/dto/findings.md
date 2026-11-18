# DTO track findings (2026-11-18)

Sources: the worktree `review/pr-17858` (head `e5473a60bbe`), the instance at `ae0190f5892`, the web container's installed packages, and a scratch Composer install of Symfony 7.4 components outside the repo. Everything below was re-checked against the code or a run unless it sits under "Not checked".

## Part A: the DTO pull request

https://github.com/shopware/shopware/pull/17858 is open and a draft (author mitelg, last update 2026-11-07).

- 281 files changed, +17,616/-41 (`git diff --shortstat origin/trunk...pr-17858`).
- 77 commits ahead of and 229 behind `origin/trunk`.
- `git merge-tree --write-tree origin/trunk pr-17858` exits 0, so it merges into trunk without conflicts today.

What it does:

- A generator (`src/Core/Framework/Api/OpenApi/OpenApiDtoGenerator.php`) reads the hand-written OpenAPI JSON and writes PHP DTO classes. The vendor extensions `x-dto-namespace` (`:26`), `x-dto-package` (`:32`) and `x-dto-inline` (`:38`) steer where classes go.
- Generated classes are `final`, use promoted constructor properties and carry `#[Package]` and `#[Assert\*]` attributes. Example: `Checkout/Customer/SalesChannel/NewsletterRecipient/ReadNewsletterRecipientStatusResponse.php` has one property, `public NewsletterStatus $status` with `#[Assert\NotNull]`.
- Base classes: `Framework/Api/AbstractDto.php` (public `?array $extensions`, `has()`), `Request/AbstractRequest.php`, `Response/AbstractResponse.php`.
- Responses: `Response/DTOResponseListener.php` acts only on `AbstractResponse`, dispatches `<route name>.encode`, validates the DTO (violations become HTTP 500), serializes with the Symfony Serializer, replaces media and SEO URL placeholders and returns a `JsonResponse`.
- Requests: `Serializer/DtoNormalizer.php` wraps Symfony's `PropertyNormalizer` with public visibility and `REQUIRE_ALL_PROPERTIES`.
- CI: `.github/workflows/php.yml:89` runs `bin/console open-api:generate-dtos --check`.

What it does not do:

- It types the API boundary only. `AccountNewsletterRecipientV2Route::loadV2` still builds a `Criteria`, calls `SalesChannelRepository::search`, reads `->first()?->get('status')` as a string and converts it with `NewsletterStatus::from()`.
- The route's extension point `ReadNewsletterRecipientExtension` still exposes `Criteria` (`:27`), so plugins keep hooking into the DAL query.
- The PR adds no `#[MapRequestPayload]` usage outside tests (0 added lines in `src`).

Correction to a first reading: `#[MapRequestPayload]` is not new to Shopware. Trunk already uses it in 9 files under `src`, for example `Content/MailTemplate/Api/MailActionController.php:146` with a custom resolver (`SimulateRequestResolver`). Request DTOs in controllers are an existing pattern we can build on.

## Part B: Symfony and PHP building blocks

Installed in the lane's web container (`composer show`): `symfony/serializer`, `validator`, `http-kernel` and `property-info` at 7.4.23, `symfony/type-info` at 8.1.11. `symfony/object-mapper` and `symfony/json-streamer` are not installed and not in `composer.json`. PHP constraint: `~8.2.0 || ~8.3.0 || ~8.4.0 || ~8.5.0` (`composer.json:64`).

| Block | State | Fit for this project |
|---|---|---|
| Serializer (`denormalize`) | installed | Row array to DTO, with type coercion |
| Validator attributes | installed | Already used by the generated DTOs |
| `#[MapRequestPayload]` | installed, used on trunk | Request body to DTO |
| ObjectMapper 7.4 | not installed; changelog: "not marked as `@experimental` anymore" | Object to object only |
| JsonStreamer 7.4 | not installed; same changelog wording | Later optimization for large lists |

Experiments with the 7.4 components (scratch install, object-mapper 7.4.23):

- ObjectMapper does not coerce types. Mapping a `stdClass` with `status: 'optIn'` onto a constructor DTO typed with a backed enum throws `TypeError: Argument #1 ($status) must be of type NewsletterStatus, string given`.
- ObjectMapper with `#[Map(source: 'status', transform: [NewsletterStatus::class, 'fromRow'])]` works, for the enum and for `?DateTimeImmutable`. The transform callable gets 3 arguments, so `[NewsletterStatus::class, 'from']` throws `ArgumentCountError`; a wrapper method is needed.
- Serializer `denormalize(['status' => 'optIn'], Dto::class)` returns the DTO with the enum set. An unknown value throws `NotNormalizableValueException: The data must belong to a backed enumeration of type NewsletterStatus`.
- JsonStreamer `write()` encoded a constructor DTO and a no-constructor DTO, both with a backed enum. The read path threw a `TypeError` in the standalone setup; cause not established.

Conclusion: for database rows (arrays of scalars) use the Serializer or a hand-written constructor call. ObjectMapper only pays off for object-to-object mapping.

PHP: property hooks, asymmetric visibility and lazy objects need PHP 8.4, and core still allows 8.2 and 8.3. `readonly` classes (8.2) are usable.

## Part C: what leaks from the DAL into the API today

- `Criteria::addFields` makes the DAL return `PartialEntity` in a generic collection (`Search/Criteria.php:643`), and `Dbal/EntityHydrator.php:565-567,587` picks `PartialEntity` when partial. Callers then read untyped values with `get('status')`.
- `AccountNewsletterRecipientRoute::load` takes a `Criteria` in its signature (`:48`), adds an `EqualsFilter` on the email and wraps the search result in the response (`:59-63`). The HTTP contract is therefore the Criteria language.
- Extension points hand `Criteria` to plugins (see Part A).
- The email column is `VARCHAR(255) COLLATE utf8mb4_unicode_ci` (`Migration1536233430NewsletterRecipient.php:25`), so the lookup is case-insensitive on MySQL without the code saying so.

## Part D: proposed slice

Route (generated response DTO) calls a port, which has two adapters.

```php
namespace Shopware\Core\Content\Newsletter\Domain;

enum SubscriptionStatus: string { case NOT_SET = 'notSet'; case OPT_IN = 'optIn'; case OPT_OUT = 'optOut'; case DIRECT = 'direct'; }

final readonly class NewsletterRecipientStatusQuery
{
    public function __construct(public string $email, public string $salesChannelId) {}
}

final readonly class NewsletterRecipientStatusRecord
{
    public function __construct(public string $recipientId, public SubscriptionStatus $status, public ?\DateTimeImmutable $confirmedAt = null) {}
}

interface NewsletterRecipientStatusReader
{
    public function find(NewsletterRecipientStatusQuery $query): ?NewsletterRecipientStatusRecord;
}
```

- `DalNewsletterRecipientStatusReader`: builds the `Criteria` and maps `PartialEntity` to the record by hand. Keeps the DAL events.
- `DbalNewsletterRecipientStatusReader`: one SQL statement through the `SqlDialect`, row to record via the Serializer or `new`. Works on both databases.
- The route maps the record to `ReadNewsletterRecipientStatusResponse` and uses `undefined` when there is no record.

Trade-offs to decide during the slice:

- The DBAL adapter does not fire the Criteria-based plugin events. The replacement hooks are the route extension (carrying the query DTO instead of `Criteria`) and the `.encode` event.
- The DBAL adapter must restate the rules the DAL applies implicitly: sales channel scoping, id conversion, case-insensitive email match.
- Two adapters need one shared contract test.

## Not checked

These come from the sub-agent's report and were not re-read: the line numbers inside `OpenApiDtoSchemaParser`, `OpenApiDtoClassRenderer` and `OpenApi/AGENTS.md`, the test counts in the PR, and the `Struct`/`Entity` `jsonSerialize` details.

## Open questions

1. How should a `#[MapRequestPayload]` validation failure (Symfony default 422) be rendered in Shopware's error format? Check what the existing trunk resolvers do.
2. Where does the DAL adapter get its `SalesChannelContext` without putting it into the port?
3. Why does the JsonStreamer read path fail in the standalone setup (possibly `type-info` 8.1 next to 7.4 components)?
4. Do we add `symfony/object-mapper` at all, given it brings nothing for row mapping?
