<?php declare(strict_types=1);
// Run: podman exec -i instance-web-1 php < scripts/dto-eval/serializer-row-to-dto.php
// Database row (array of scalars) to a readonly DTO with enum and date, with the Symfony Serializer, and the hand-written constructor call.
require '/var/www/html/vendor/autoload.php';

use Shopware\Core\Content\Newsletter\Domain\NewsletterStatus;
use Symfony\Component\Serializer\Normalizer\BackedEnumNormalizer;
use Symfony\Component\Serializer\Normalizer\DateTimeNormalizer;
use Symfony\Component\Serializer\Normalizer\ObjectNormalizer;
use Symfony\Component\Serializer\Normalizer\PropertyNormalizer;
use Symfony\Component\Serializer\Serializer;
use Symfony\Component\Serializer\NameConverter\CamelCaseToSnakeCaseNameConverter;

final readonly class Row
{
    public function __construct(public string $email, public NewsletterStatus $status, public ?\DateTimeImmutable $confirmedAt = null)
    {
    }
}

$s = new Serializer([new BackedEnumNormalizer(), new DateTimeNormalizer(), new ObjectNormalizer(nameConverter: new CamelCaseToSnakeCaseNameConverter())]);
$row = ['email' => 'a@example.com', 'status' => 'optIn', 'confirmed_at' => '2026-01-02 03:04:05.000'];

$t = microtime(true);
for ($i = 0; $i < 10000; ++$i) {
    $dto = $s->denormalize($row, Row::class);
}
printf("serializer   %s %s %.0f us/row\n", $dto->status->value, $dto->confirmedAt?->format('c'), (microtime(true) - $t) * 100);

$t = microtime(true);
for ($i = 0; $i < 10000; ++$i) {
    $dto = new Row($row['email'], NewsletterStatus::from($row['status']), new \DateTimeImmutable($row['confirmed_at']));
}
printf("constructor  %s %s %.0f us/row\n", $dto->status->value, $dto->confirmedAt?->format('c'), (microtime(true) - $t) * 100);

try {
    $s->denormalize(['email' => 'a', 'status' => 'bogus'], Row::class);
} catch (\Throwable $e) {
    echo 'unknown enum: ', (new ReflectionClass($e))->getShortName(), ': ', $e->getMessage(), "\n";
}
