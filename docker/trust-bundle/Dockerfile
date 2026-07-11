FROM eclipse-temurin:21-jdk-alpine

RUN apk add --no-cache openssl bash && \
    mkdir -p /source /output

COPY docker/trust-bundle/generate.sh /generate.sh
RUN chmod +x /generate.sh

ENTRYPOINT ["/generate.sh"]
