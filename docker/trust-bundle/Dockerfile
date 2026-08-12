ARG JAVA_REGISTRY=""
ARG JAVA_NAMESPACE=""
ARG JAVA_IMAGE="eclipse-temurin"
ARG JAVA_TAG="21-jdk-jammy"

FROM ${JAVA_REGISTRY}${JAVA_NAMESPACE}${JAVA_IMAGE}:${JAVA_TAG}

RUN apt-get update && \
    apt-get install -y --no-install-recommends openssl bash ca-certificates && \
    rm -rf /var/lib/apt/lists/* && \
    mkdir -p /source /output

COPY docker/trust-bundle/generate.sh /generate.sh
RUN chmod +x /generate.sh

ENTRYPOINT ["/generate.sh"]
