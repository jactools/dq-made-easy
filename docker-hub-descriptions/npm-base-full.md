# Base Node.js Image for Data Quality Made Easy

Foundational image containing Node.js 20 (Bullseye Slim) with build essentials and common dependencies. Serves as the parent image for `dq-api` and `dq-profiling` services.

## Features

- Node.js 20 LTS on Debian Bullseye Slim
- Build essentials (gcc, g++, make)
- curl and ca-certificates pre-installed
- Optimized for production with minimal attack surface

## Quick Start

```bash
docker pull jacbeekers/npm-base:latest
```

## Tags

- `latest` - Most recent build
- `0.3.0-xxxxxxx` - Semantic version with content hash (recommended for production)

## Usage

This is a base image meant to be used in `FROM` statements:

```dockerfile
FROM jacbeekers/npm-base:0.3.0-e625985
WORKDIR /app
COPY package*.json ./
RUN npm ci --production
```

## Part of Data Quality Made Easy

This image is part of the Data Quality Made Easy platform - a comprehensive data quality rule management system.

**Other Services:**
- `jacbeekers/dq-api` - REST API backend
- `jacbeekers/dq-engine` - Rule execution engine
- `jacbeekers/dq-profiling` - Profiling worker
- `jacbeekers/dq-frontend` - Web UI
- `jacbeekers/dq-kong` - API Gateway

## Documentation

Full documentation: [GitHub Repository](https://github.com/jacbeekers/dq-rulebuilder)
