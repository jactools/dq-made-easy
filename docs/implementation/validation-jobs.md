# Validation Job Template for Kind Cluster
#
# Usage:
#   1. Apply this Job YAML to run a validation script inside the cluster
#   2. The Job uses the dq-made-easy-api image which has curl, jq, kubectl
#   3. Scripts are mounted from a ConfigMap or the repo volume
#
# Example:
#   kubectl apply -f - <<EOF
#   apiVersion: batch/v1
#   kind: Job
#   metadata:
#     name: validate-user-login
#     namespace: dq-dev
#     labels:
#       app.kubernetes.io/part-of: dq-made-easy
#       dq.jaccloud.nl/type: validation
#   spec:
#     ttlSecondsAfterFinished: 300
#     template:
#       spec:
#         serviceAccountName: default
#         restartPolicy: Never
#         containers:
#         - name: validate
#           image: jacloud.nl/docker/jacbeekers/dq-made-easy-api:0.11
#           command:
#           - bash
#           - /scripts/validation/validate_user_login_end_to_end.sh
#           env:
#           - name: ROOT_ENV_FILE
#             value: /env/.env.dev.local
#           envFrom:
#           - configMapRef:
#               name: dq-common-config
#           - secretRef:
#               name: dq-api-secrets
#           - secretRef:
#               name: dq-keycloak-secrets
#           volumeMounts:
#           - name: scripts
#             mountPath: /scripts
#           - name: env
#             mountPath: /env
#           - name: certs
#             mountPath: /etc/ssl/certs/platform-root-ca.pem
#             subPath: rootCA.pem
#             readOnly: true
#         volumes:
#         - name: scripts
#           configMap:
#             name: dq-validation-scripts
#             defaultMode: 0755
#         - name: env
#           configMap:
#             name: dq-env-dev
#         - name: certs
#           configMap:
#             name: platform-root-ca
#   EOF
