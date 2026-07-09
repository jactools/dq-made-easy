# Docker Compose Split - Troubleshooting

## Common Issues

### 1. No such file or directory
**Error**: ERROR: No such file or directory: 'docker-compose/docker-compose.yml'

**Solution**: 
- Navigate to repository root: `cd /path/to/dq-made-easy`
- Verify files exist: `ls -la docker-compose/`
- Use full path: `docker compose -f /full/path/to/docker-compose/docker-compose.yml up`

### 2. Unsupported config option: include
**Error**: ERROR: Unsupported config option: include

**Solution**: 
- Upgrade Docker Compose to v2.4.0+
- Check version: `docker compose version`
- Workaround: Use multiple -f flags:
  ```bash
  docker compose \
    -f docker-compose/base.yml \
    -f docker-compose/core.yml \
    up -d
  ```

### 3. Service not found
**Error**: ERROR: Service 'api' not found in any file

**Solution**:
- Check service is in correct file: `grep -r "api:" docker-compose/`
- List all services: `docker compose -f docker-compose/docker-compose.yml config --services`
- Verify all files are included in docker-compose.yml

### 4. Network not found
**Error**: ERROR: Network 'dq-made-easy-default' not found

**Solution**:
- Ensure base.yml is included
- Create networks manually: `docker network create dq-made-easy-default`
- List networks: `docker network ls`

### 5. Volume not found
**Error**: ERROR: Volume 'pgdata_v18' not found

**Solution**:
- Ensure base.yml is included (volumes defined there)
- Create volume: `docker volume create pgdata_v18`
- List volumes: `docker compose -f docker-compose/docker-compose.yml config --volumes`

### 6. Variable not set
**Error**: The variable 'DQ_DB_INTERNAL_URL' is not set

**Solution**:
- Load env file: `docker compose -f docker-compose/docker-compose.yml --env-file .env.dev.local up`
- Set variable directly: `DQ_DB_INTERNAL_URL=... docker compose ... up`
- Check .env file: `grep DQ_DB_INTERNAL_URL .env.dev.local`

### 7. Dependency failed
**Error**: Service 'api' depends on service 'db' which is not healthy

**Solution**:
- Check dependency: `docker compose -f docker-compose/docker-compose.yml ps db`
- View logs: `docker compose -f docker-compose/docker-compose.yml logs db`
- Restart: `docker compose -f docker-compose/docker-compose.yml restart db`

### 8. Port already in use
**Error**: ERROR: Port 8000 already in use

**Solution**:
- Find process: `sudo lsof -i :8000` or `sudo netstat -tulnp \| grep 8000`
- Kill process: `sudo kill &lt;PID&gt;`
- Change port: Edit service in appropriate file, change host port binding

### 9. Build failed
**Error**: ERROR: Service 'api' build failed

**Solution**:
- Check build logs: `docker compose -f docker-compose/docker-compose.yml build api`
- Verify Dockerfile: `ls -la dq-api/Dockerfile.api`
- Set build args: `--build-arg PIP_INDEX_URL=...`

### 10. Out of memory
**Error**: Container killed: OOM

**Solution**:
- Increase memory limit in service config
- Check usage: `docker stats`
- Reduce service memory usage via env vars

## Validation Commands

### Validate Configuration
```bash
docker compose -f docker-compose/docker-compose.yml config
```

### Check Services
```bash
docker compose -f docker-compose/docker-compose.yml ps
docker compose -f docker-compose/docker-compose.yml ps --format json
```

### View Logs
```bash
docker compose -f docker-compose/docker-compose.yml logs
docker compose -f docker-compose/docker-compose.yml logs -f <service>
```

### Debug Mode
```bash
DEBUG=1 docker compose -f docker-compose/docker-compose.yml up
```

## Support

1. Check this guide
2. Review migration guide for full details
3. Ask in Slack: #devops
4. Create GitHub issue with docker-compose label

When asking for help, provide:
- Error message (full text)
- Command you ran
- Docker Compose version: `docker compose version`
- Docker version: `docker version`
- OS: `uname -a`
