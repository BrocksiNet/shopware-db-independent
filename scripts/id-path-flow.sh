#!/bin/sh
# Store API flow over the converted request path (context, product listing, detail, cart, context switch). Needs /tmp/pg-store.sh (lane helper).
# usage: scripts/id-path-flow.sh  -> prints one line per request, exit 1 on a non 2xx
P=aaaaaaaaaaaa4aaa8aaaaaaaaaaaaa10
CAT=01a1ee5dbe6873a1aad758911362d195
rc=0
run() { out=$(/tmp/pg-store.sh "$@" 2>&1 | head -3); echo "$out" | head -1; case "$out" in *" -> 2"*) ;; *) echo "$out" | tail -2 | cut -c1-300; rc=1;; esac; }
run GET /context
run POST /product '{"limit":10,"includes":{"product":["id"]}}'
run POST /product-listing/$CAT '{"limit":10,"includes":{"product":["id"]}}'
run POST /product/$P '{"includes":{"product":["id"]}}'
run POST /product/$P/find-variant '{"switchedGroup":"x","options":{}}'
run POST /checkout/cart/line-item "{\"items\":[{\"type\":\"product\",\"referencedId\":\"$P\",\"quantity\":1}]}"
run GET /checkout/cart
run PATCH /context '{"languageId":"2fbb5fe2e29a4d70aa5854ce7ce3e20b"}'
run GET /context
exit $rc
