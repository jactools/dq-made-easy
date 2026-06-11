# DQ Base Image

This directory contains the base Docker image used throughout the Data Quality Made Easy project. The base image includes Node.js and essential build tools.

## Building and Pushing to Docker Hub

### Prerequisites

1. **Docker Hub Account**: Make sure you have a Docker Hub account
2. **Login to Docker Hub**:
   ```bash
   docker login docker.io
   ```
   Enter your Docker Hub username and password when prompted.

### Quick Start

Build and push the image to Docker Hub:
```bash
./build_and_push.sh
```

### Script Options

```bash
./build_and_push.sh [OPTIONS]
```

Options:
- `--no-cache` - Build without using Docker cache (clean build)
- `--no-push` - Build only, do not push to Docker Hub
- `-h, --help` - Show help message

### Examples

**Build and push to Docker Hub:**
```bash
./build_and_push.sh
```

**Build without cache and push:**
```bash
./build_and_push.sh --no-cache
```

**Build locally without pushing:**
```bash
./build_and_push.sh --no-push
```

**Rebuild from scratch without pushing:**
```bash
./build_and_push.sh --no-cache --no-push
```

## Configuration

The image name and registry are configured in the root `.env` file:

```bash
DQ_BASE_REGISTRY=docker.io/
DQ_BASE_NAMESPACE=jacbeekers/
DQ_BASE_IMAGE=npm-base:latest
```

Full image name: `docker.io/jacbeekers/npm-base:latest`

## Image Contents

The base image includes:
- Node.js 20 (Debian slim)
- Build essentials (gcc, g++, make, etc.)
- curl
- CA certificates

## Troubleshooting

### Push fails with authentication error

Make sure you're logged in to Docker Hub:
```bash
docker login docker.io
```

### Permission denied when running script

Make the script executable:
```bash
chmod +x build_and_push.sh
```

### Build fails

Try rebuilding without cache:
```bash
./build_and_push.sh --no-cache --no-push
```

Check the Dockerfile.base for any issues.

## Using in docker-compose

The base image is referenced in `docker-compose.yml`:

```yaml
services:
  base:
    image: ${DQ_BASE_REGISTRY}${DQ_BASE_NAMESPACE}${DQ_BASE_IMAGE}
    build:
      context: ./dq-base
      dockerfile: Dockerfile.base
```

Docker Compose will either:
1. Pull the image from Docker Hub if it exists
2. Build it locally if needed

## CI/CD Integration

To integrate with CI/CD pipelines:

```bash
# Login (using environment variables or secrets)
echo $DOCKER_PASSWORD | docker login docker.io -u $DOCKER_USERNAME --password-stdin

# Build and push
cd dq-base
./build_and_push.sh --no-cache
```

Make sure to set `DOCKER_USERNAME` and `DOCKER_PASSWORD` as secrets in your CI/CD system.
