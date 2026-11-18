<?php declare(strict_types=1);
// Run: podman exec -i instance-web-1 php < scripts/dto-eval/map-request-payload.php
// Shows what #[MapRequestPayload] produces for an invalid newsletter payload.
require '/var/www/html/vendor/autoload.php';

use Symfony\Component\HttpFoundation\Request;
use Symfony\Component\HttpKernel\Attribute\MapRequestPayload;
use Symfony\Component\HttpKernel\Controller\ArgumentResolver\RequestPayloadValueResolver;
use Symfony\Component\HttpKernel\ControllerMetadata\ArgumentMetadata;
use Symfony\Component\HttpKernel\Exception\HttpException;
use Symfony\Component\Serializer\Encoder\JsonEncoder;
use Symfony\Component\Serializer\Normalizer\ObjectNormalizer;
use Symfony\Component\Serializer\Serializer;
use Symfony\Component\Validator\Constraints as Assert;
use Symfony\Component\Validator\Validation;
use Symfony\Component\HttpKernel\Event\ControllerArgumentsEvent;
use Symfony\Component\HttpKernel\HttpKernelInterface;
use Symfony\Component\HttpKernel\Kernel;

final readonly class SubscribeDto
{
    public function __construct(
        #[Assert\NotBlank, Assert\Email] public string $email,
        #[Assert\Choice(['direct', 'subscribe', 'unsubscribe', 'confirmSubscribe'])] public string $option,
        public ?string $firstName = null,
    ) {
    }
}

$validator = Validation::createValidatorBuilder()->enableAttributeMapping()->getValidator();
$serializer = new Serializer([new ObjectNormalizer()], [new JsonEncoder()]);
$resolver = new RequestPayloadValueResolver($serializer, $validator);

foreach ([
    'valid' => '{"email":"a@example.com","option":"subscribe"}',
    'invalid' => '{"email":"nope","option":"bogus"}',
    'wrong type' => '{"email":["x"],"option":"subscribe"}',
    'missing' => '{"option":"subscribe"}',
] as $label => $body) {
    $request = Request::create('/x', 'POST', server: ['CONTENT_TYPE' => 'application/json'], content: $body);
    $meta = new ArgumentMetadata('dto', SubscribeDto::class, false, false, null, attributes: [new MapRequestPayload()]);
    try {
        $args = $resolver->resolve($request, $meta);
        $event = new ControllerArgumentsEvent(
            new class extends Kernel { public function __construct() { parent::__construct('x', false); } public function registerBundles(): iterable { return []; } public function registerContainerConfiguration($l): void {} },
            static fn () => null, $args, $request, HttpKernelInterface::MAIN_REQUEST,
        );
        $resolver->onKernelControllerArguments($event);
        echo str_pad($label, 11), 'OK ', json_encode($event->getArguments()[0] ?? null), "\n";
    } catch (HttpException $e) {
        $prev = $e->getPrevious();
        $v = method_exists($prev, 'getViolations') ? $prev->getViolations() : [];
        $list = [];
        foreach ($v as $violation) {
            $list[] = $violation->getPropertyPath() . ' ' . $violation->getCode();
        }
        echo str_pad($label, 11), $e->getStatusCode(), ' ', $e::class, ' ', json_encode($list), ' ', $prev === null ? '' : substr($prev::class, strrpos($prev::class, '\\') + 1), "\n";
    }
}
