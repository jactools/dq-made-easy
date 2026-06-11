# How to Set Categories on Docker Hub (Manual Process)

## Why Manual?

Docker Hub's API does not support setting categories for community repositories. Categories must be set through the web interface.

## Steps to Set Categories

For each repository, follow these steps:

### 1. npm-base
- URL: https://hub.docker.com/repository/docker/jacbeekers/npm-base/general
- Categories: **Base images**

### 2. dq-api
- URL: https://hub.docker.com/repository/docker/jacbeekers/dq-api/general
- Categories: **Languages & frameworks**, **Databases & storage**

### 3. dq-engine
- URL: https://hub.docker.com/repository/docker/jacbeekers/dq-engine/general
- Categories: **Languages & frameworks**, **Databases & storage**

### 4. dq-profiling  
- URL: https://hub.docker.com/repository/docker/jacbeekers/dq-profiling/general
- Categories: **Languages & frameworks**, **Databases & storage**

### 5. dq-frontend
- URL: https://hub.docker.com/repository/docker/jacbeekers/dq-frontend/general
- Categories: **Languages & frameworks**

### 6. dq-kong
- URL: https://hub.docker.com/repository/docker/jacbeekers/dq-kong/general
- Categories: **Networking**, **Databases & storage**

## Manual Process

1. Click the URL above (or navigate to: Repository → Settings → General)
2. Scroll down to the **Categories** section
3. Click the dropdown and select the categories listed above
4. Click **Update** at the bottom of the page
5. Verify categories appear on the repository page

## Available Docker Hub Categories

When selecting in the web UI, you'll see these options:
- Base images
- Languages & frameworks
- Databases & storage
- Networking
- Operating systems
- Continuous integration & delivery
- Developer tools
- Web servers
- Proxy servers
- Security
- Message queues
- Monitoring & observability
- (and more...)

## Note

The `update_docker_hub.sh` script attempts to set categories via API (for future compatibility), but Docker Hub silently ignores these updates for community repositories. The category files in `docker-hub-descriptions/` use the proper format (`name:slug`) and are ready if Docker Hub enables API access in the future.
