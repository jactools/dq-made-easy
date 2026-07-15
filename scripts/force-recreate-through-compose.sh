container_name="$1"

docker compose --env-file .env.dev.local up -d --force-recreate $container_name
