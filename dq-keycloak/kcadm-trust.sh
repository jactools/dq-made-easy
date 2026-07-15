#!/bin/sh
# Wrapper that sources trust-bundle env before running kcadm.sh
. /certs/trust/java-truststore-env.sh 2>/dev/null
exec /opt/keycloak/bin/kcadm.sh "$@"
