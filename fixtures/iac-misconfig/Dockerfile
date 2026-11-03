# Deliberate misconfiguration for the trivy self-test, never build or ship this.
# Trivy v0.76.1 reports DS-0002 (HIGH): no USER line, so the image runs as root.
# It also reports DS-0025 (HIGH): apk add without --no-cache.
FROM alpine:3.20
RUN apk add curl
