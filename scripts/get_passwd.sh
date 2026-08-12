kubectl get secret keycloak-user-credentials -n dq-made-easy-dev -o jsonpath='{.data.credentials\.csv}' | base64 -d >tmp/.user-credentials.txt


