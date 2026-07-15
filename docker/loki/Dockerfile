FROM grafana/loki:3.6.4 AS loki

FROM alpine:3.21
RUN apk --no-cache add ca-certificates wget
COPY --from=loki /usr/bin/loki /usr/bin/loki
ENTRYPOINT ["/usr/bin/loki"]
CMD ["-config.file=/etc/loki/local-config.yml"]
