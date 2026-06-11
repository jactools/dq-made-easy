# Deploying to Azure Container Apps

This guide covers deploying the Data Quality Made Easy application to Azure Container Apps.

## Table of Contents

- [Prerequisites](#prerequisites)
- [Version Management](#version-management)
- [Building the Application](#building-the-application)
- [Container Images](#container-images)
- [Azure Resources Setup](#azure-resources-setup)
- [Deployment Steps](#deployment-steps)
- [CI/CD Pipeline](#cicd-pipeline)
- [Environment Variables](#environment-variables)
- [Monitoring and Troubleshooting](#monitoring-and-troubleshooting)

## Prerequisites

- **Azure CLI** installed and authenticated (`az login`)
- **Docker** installed and running
- **Node.js 20+** for building the frontend
- **Azure subscription** with appropriate permissions
- **Container Registry** (Azure Container Registry recommended)

## Version Management

The application uses automatic version injection from `package.json` to ensure consistency across builds.

### How It Works

1. **Source of Truth**: `dq-ui/package.json` contains the version number
2. **Build Time Injection**: Vite reads version during `npm run build` and embeds it into the bundle
3. **Runtime Display**: Version appears in the header without any dynamic lookups

### Configuration Files

**dq-ui/vite.config.ts**:
```typescript
import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'
import * as fs from 'fs'

const packageJson = JSON.parse(fs.readFileSync('./package.json', 'utf-8'))
const buildDate = new Date().toLocaleDateString('en-US', { year: 'numeric', month: 'long' })

export default defineConfig({
  plugins: [react()],
  define: {
    __APP_VERSION__: JSON.stringify(packageJson.version),
    __BUILD_DATE__: JSON.stringify(buildDate)
  }
})
```

**dq-ui/src/components/Header.tsx**:
```typescript
declare const __APP_VERSION__: string
declare const __BUILD_DATE__: string
// These constants are injected at build time
```

### Updating Version

```bash
# Edit dq-ui/package.json
{
  "version": "0.3.0"  # Update this
}

# Rebuild
cd dq-ui
npm run build

# Version is now embedded in dist/assets/*.js
```

## Building the Application

### Local Build Process

```bash
# 1. Build frontend (embeds version from package.json)
./scripts/local_build_frontend.sh

# This script:
# - Runs npm install in dq-ui/
# - Runs npm run build (Vite embeds version here)
# - Builds Docker image with prebuilt dist/
```

### Manual Build Steps

```bash
# Build frontend
cd dq-ui
npm install
npm run build  # Version from package.json is embedded here
cd ..

# Build Docker images
docker compose build

# Or build individual services
docker compose build frontend
docker compose build api
docker compose build profiling
```

## Container Images

### Frontend Image

**Dockerfile.frontend** (Nginx-based):
- Expects pre-built `dist/` directory
- Nginx serves static files with embedded version
- No Node.js runtime needed

```dockerfile
FROM nginx:stable-alpine
COPY dist/ /usr/share/nginx/html/
COPY nginx/default.conf /etc/nginx/conf.d/default.conf
EXPOSE 80
```

### API Image

**Dockerfile.fastapi** (FastAPI backend):
- Node.js runtime
- Handles /api endpoints
- Connects to PostgreSQL and Redis

### Profiling Service Image

**Dockerfile (Python-based)**:
- Python runtime
- Background job processing
- Data profiling and analysis

## Azure Resources Setup

### Required Azure Resources

1. **Azure Container Registry (ACR)**
2. **Azure Container Apps Environment**
3. **Azure Database for PostgreSQL Flexible Server**
4. **Azure Cache for Redis**
5. **Azure Log Analytics Workspace** (for monitoring)

### Create Resources

```bash
# Variables
RESOURCE_GROUP="dq-rulebuilder-rg"
LOCATION="westeurope"
ACR_NAME="dqrulebuilderacr"
ENVIRONMENT_NAME="dq-environment"
POSTGRES_SERVER="dq-postgres-server"
REDIS_NAME="dq-redis"

# Create resource group
az group create \
  --name $RESOURCE_GROUP \
  --location $LOCATION

# Create Azure Container Registry
az acr create \
  --resource-group $RESOURCE_GROUP \
  --name $ACR_NAME \
  --sku Standard \
  --admin-enabled true

# Get ACR credentials
ACR_USERNAME=$(az acr credential show --name $ACR_NAME --query username -o tsv)
ACR_PASSWORD=$(az acr credential show --name $ACR_NAME --query passwords[0].value -o tsv)
ACR_LOGIN_SERVER=$(az acr show --name $ACR_NAME --query loginServer -o tsv)

# Create PostgreSQL Flexible Server
az postgres flexible-server create \
  --resource-group $RESOURCE_GROUP \
  --name $POSTGRES_SERVER \
  --location $LOCATION \
  --admin-user dqadmin \
  --admin-password <YourSecurePassword> \
  --sku-name Standard_B2s \
  --tier Burstable \
  --storage-size 32 \
  --version 14 \
  --public-access 0.0.0.0

# Create database
az postgres flexible-server db create \
  --resource-group $RESOURCE_GROUP \
  --server-name $POSTGRES_SERVER \
  --database-name dqrulebuilder

# Create Redis
az redis create \
  --resource-group $RESOURCE_GROUP \
  --name $REDIS_NAME \
  --location $LOCATION \
  --sku Basic \
  --vm-size c0

# Create Log Analytics Workspace
az monitor log-analytics workspace create \
  --resource-group $RESOURCE_GROUP \
  --workspace-name dq-logs

# Get workspace ID
WORKSPACE_ID=$(az monitor log-analytics workspace show \
  --resource-group $RESOURCE_GROUP \
  --workspace-name dq-logs \
  --query customerId -o tsv)

WORKSPACE_KEY=$(az monitor log-analytics workspace get-shared-keys \
  --resource-group $RESOURCE_GROUP \
  --workspace-name dq-logs \
  --query primarySharedKey -o tsv)

# Create Container Apps Environment
az containerapp env create \
  --name $ENVIRONMENT_NAME \
  --resource-group $RESOURCE_GROUP \
  --location $LOCATION \
  --logs-workspace-id $WORKSPACE_ID \
  --logs-workspace-key $WORKSPACE_KEY
```

## Deployment Steps

### 1. Build and Push Images

```bash
# Login to ACR
az acr login --name $ACR_NAME

# Tag images
docker tag dq-ui:latest ${ACR_LOGIN_SERVER}/dq-ui:0.3.0
docker tag dq-api:latest ${ACR_LOGIN_SERVER}/dq-api:0.3.0
docker tag dq-profiling:latest ${ACR_LOGIN_SERVER}/dq-profiling:0.3.0

# Push to ACR
docker push ${ACR_LOGIN_SERVER}/dq-ui:0.3.0
docker push ${ACR_LOGIN_SERVER}/dq-api:0.3.0
docker push ${ACR_LOGIN_SERVER}/dq-profiling:0.3.0
```

### 2. Deploy Container Apps

#### Frontend Container App

```bash
az containerapp create \
  --name dq-frontend \
  --resource-group $RESOURCE_GROUP \
  --environment $ENVIRONMENT_NAME \
  --image ${ACR_LOGIN_SERVER}/dq-ui:0.3.0 \
  --registry-server ${ACR_LOGIN_SERVER} \
  --registry-username $ACR_USERNAME \
  --registry-password $ACR_PASSWORD \
  --target-port 80 \
  --ingress external \
  --min-replicas 1 \
  --max-replicas 3 \
  --cpu 0.5 \
  --memory 1.0Gi
```

#### API Container App

```bash
# Get database connection string
POSTGRES_HOST=$(az postgres flexible-server show \
  --resource-group $RESOURCE_GROUP \
  --name $POSTGRES_SERVER \
  --query fullyQualifiedDomainName -o tsv)

REDIS_HOST=$(az redis show \
  --resource-group $RESOURCE_GROUP \
  --name $REDIS_NAME \
  --query hostName -o tsv)

REDIS_KEY=$(az redis list-keys \
  --resource-group $RESOURCE_GROUP \
  --name $REDIS_NAME \
  --query primaryKey -o tsv)

# Deploy API
az containerapp create \
  --name dq-api \
  --resource-group $RESOURCE_GROUP \
  --environment $ENVIRONMENT_NAME \
  --image ${ACR_LOGIN_SERVER}/dq-api:0.3.0 \
  --registry-server ${ACR_LOGIN_SERVER} \
  --registry-username $ACR_USERNAME \
  --registry-password $ACR_PASSWORD \
  --target-port 3000 \
  --ingress internal \
  --min-replicas 1 \
  --max-replicas 5 \
  --cpu 1.0 \
  --memory 2.0Gi \
  --env-vars \
    DATABASE_URL="postgresql://dqadmin:<password>@${POSTGRES_HOST}:5432/dqrulebuilder?sslmode=require" \
    REDIS_HOST="${REDIS_HOST}" \
    REDIS_PORT="6380" \
    REDIS_PASSWORD="${REDIS_KEY}" \
    REDIS_TLS="true" \
    NODE_ENV="production"
```

#### Profiling Service Container App

```bash
az containerapp create \
  --name dq-profiling \
  --resource-group $RESOURCE_GROUP \
  --environment $ENVIRONMENT_NAME \
  --image ${ACR_LOGIN_SERVER}/dq-profiling:0.3.0 \
  --registry-server ${ACR_LOGIN_SERVER} \
  --registry-username $ACR_USERNAME \
  --registry-password $ACR_PASSWORD \
  --target-port 3001 \
  --ingress internal \
  --min-replicas 1 \
  --max-replicas 3 \
  --cpu 1.0 \
  --memory 2.0Gi \
  --env-vars \
    DATABASE_URL="postgresql://dqadmin:<password>@${POSTGRES_HOST}:5432/dqrulebuilder?sslmode=require" \
    REDIS_HOST="${REDIS_HOST}" \
    REDIS_PORT="6380" \
    REDIS_PASSWORD="${REDIS_KEY}" \
    REDIS_TLS="true"
```

### 3. Update Frontend to Point to API

```bash
# Get internal API FQDN
API_FQDN=$(az containerapp show \
  --name dq-api \
  --resource-group $RESOURCE_GROUP \
  --query properties.configuration.ingress.fqdn -o tsv)

# Update frontend with API URL
az containerapp update \
  --name dq-frontend \
  --resource-group $RESOURCE_GROUP \
  --set-env-vars API_BASE_URL="https://${API_FQDN}"
```

### 4. Run Database Migrations

```bash
# Get a shell in the API container
az containerapp exec \
  --name dq-api \
  --resource-group $RESOURCE_GROUP \
  --command /bin/sh

# Inside container, run migrations
npm run migration:run
```

## CI/CD Pipeline

### GitHub Actions Example

```yaml
name: Deploy to Azure Container Apps

on:
  push:
    branches: [main]
  workflow_dispatch:

env:
  AZURE_RESOURCE_GROUP: dq-rulebuilder-rg
  ACR_NAME: dqrulebuilderacr
  
jobs:
  build-and-deploy:
    runs-on: ubuntu-latest
    
    steps:
    - name: Checkout code
      uses: actions/checkout@v3
    
    - name: Setup Node.js
      uses: actions/setup-node@v3
      with:
        node-version: '22'
    
    - name: Get version from package.json
      id: package-version
      run: |
        VERSION=$(node -p "require('./dq-ui/package.json').version")
        echo "VERSION=$VERSION" >> $GITHUB_OUTPUT
        echo "Deploying version: $VERSION"
    
    - name: Build frontend
      run: |
        cd dq-ui
        # npm is pinned to 11.14.1 in the repo manifests.
        npm install
        npm run build  # Version embedded here from package.json
        cd ..
    
    - name: Azure Login
      uses: azure/login@v1
      with:
        creds: ${{ secrets.AZURE_CREDENTIALS }}
    
    - name: Login to ACR
      run: |
        az acr login --name ${{ env.ACR_NAME }}
    
    - name: Build and Push Docker Images
      run: |
        VERSION=${{ steps.package-version.outputs.VERSION }}
        ACR_LOGIN_SERVER=$(az acr show --name ${{ env.ACR_NAME }} --query loginServer -o tsv)
        
        # Build with version tag
        docker compose build
        docker tag dq-ui:latest ${ACR_LOGIN_SERVER}/dq-ui:${VERSION}
        docker tag dq-api:latest ${ACR_LOGIN_SERVER}/dq-api:${VERSION}
        docker tag dq-profiling:latest ${ACR_LOGIN_SERVER}/dq-profiling:${VERSION}
        
        # Also tag as latest
        docker tag dq-ui:latest ${ACR_LOGIN_SERVER}/dq-ui:latest
        docker tag dq-api:latest ${ACR_LOGIN_SERVER}/dq-api:latest
        docker tag dq-profiling:latest ${ACR_LOGIN_SERVER}/dq-profiling:latest
        
        # Push both tags
        docker push ${ACR_LOGIN_SERVER}/dq-ui:${VERSION}
        docker push ${ACR_LOGIN_SERVER}/dq-api:${VERSION}
        docker push ${ACR_LOGIN_SERVER}/dq-profiling:${VERSION}
        docker push ${ACR_LOGIN_SERVER}/dq-ui:latest
        docker push ${ACR_LOGIN_SERVER}/dq-api:latest
        docker push ${ACR_LOGIN_SERVER}/dq-profiling:latest
    
    - name: Deploy to Container Apps
      run: |
        VERSION=${{ steps.package-version.outputs.VERSION }}
        ACR_LOGIN_SERVER=$(az acr show --name ${{ env.ACR_NAME }} --query loginServer -o tsv)
        
        # Update frontend
        az containerapp update \
          --name dq-frontend \
          --resource-group ${{ env.AZURE_RESOURCE_GROUP }} \
          --image ${ACR_LOGIN_SERVER}/dq-ui:${VERSION}
        
        # Update API
        az containerapp update \
          --name dq-api \
          --resource-group ${{ env.AZURE_RESOURCE_GROUP }} \
          --image ${ACR_LOGIN_SERVER}/dq-api:${VERSION}
        
        # Update profiling service
        az containerapp update \
          --name dq-profiling \
          --resource-group ${{ env.AZURE_RESOURCE_GROUP }} \
          --image ${ACR_LOGIN_SERVER}/dq-profiling:${VERSION}
    
    - name: Run Database Migrations
      run: |
        az containerapp exec \
          --name dq-api \
          --resource-group ${{ env.AZURE_RESOURCE_GROUP }} \
          --command "npm run migration:run"
```

### Azure DevOps Pipeline Example

```yaml
trigger:
  branches:
    include:
    - main

variables:
  azureSubscription: 'your-service-connection'
  resourceGroup: 'dq-rulebuilder-rg'
  acrName: 'dqrulebuilderacr'

stages:
- stage: Build
  jobs:
  - job: BuildAndPush
    pool:
      vmImage: 'ubuntu-latest'
    steps:
    - task: NodeTool@0
      inputs:
        versionSpec: '20.x'
    
    - script: |
        cd dq-ui
        npm install
        npm run build
        cd ..
      displayName: 'Build Frontend (Version Embedded)'
    
    - task: Docker@2
      inputs:
        command: buildAndPush
        repository: dq-ui
        dockerfile: dq-ui/Dockerfile.frontend
        containerRegistry: $(acrName)
        tags: |
          $(Build.BuildNumber)
          latest

- stage: Deploy
  dependsOn: Build
  jobs:
  - job: DeployToAzure
    pool:
      vmImage: 'ubuntu-latest'
    steps:
    - task: AzureCLI@2
      inputs:
        azureSubscription: $(azureSubscription)
        scriptType: bash
        scriptLocation: inlineScript
        inlineScript: |
          az containerapp update \
            --name dq-frontend \
            --resource-group $(resourceGroup) \
            --image $(acrName).azurecr.io/dq-ui:$(Build.BuildNumber)
```

## Environment Variables

### Frontend (dq-ui)

| Variable | Description | Example |
|----------|-------------|---------|
| `API_BASE_URL` | Backend API URL | `https://dq-api.internal.example.com` |

### Backend (dq-api)

| Variable | Description | Example |
|----------|-------------|---------|
| `DATABASE_URL` | PostgreSQL connection string | `postgresql://user:pass@host:5432/db?sslmode=require` |
| `REDIS_HOST` | Redis hostname | `dq-redis.redis.cache.windows.net` |
| `REDIS_PORT` | Redis port | `6380` |
| `REDIS_PASSWORD` | Redis password | `<from Azure>` |
| `REDIS_TLS` | Enable TLS for Redis | `true` |
| `NODE_ENV` | Environment | `production` |
| `JWT_SECRET` | JWT signing secret | `<secure-random-string>` |
| `CORS_ORIGIN` | Allowed CORS origins | `https://dq-frontend.example.com` |

### Profiling Service (dq-profiling)

| Variable | Description | Example |
|----------|-------------|---------|
| `DATABASE_URL` | PostgreSQL connection string | Same as API |
| `REDIS_HOST` | Redis hostname | Same as API |
| `REDIS_PORT` | Redis port | `6380` |
| `REDIS_PASSWORD` | Redis password | Same as API |

## Monitoring and Troubleshooting

### View Logs

```bash
# Frontend logs
az containerapp logs show \
  --name dq-frontend \
  --resource-group $RESOURCE_GROUP \
  --follow

# API logs
az containerapp logs show \
  --name dq-api \
  --resource-group $RESOURCE_GROUP \
  --follow

# Profiling service logs
az containerapp logs show \
  --name dq-profiling \
  --resource-group $RESOURCE_GROUP \
  --follow
```

### Check Container App Status

```bash
# Get all container apps
az containerapp list \
  --resource-group $RESOURCE_GROUP \
  --output table

# Get specific app details
az containerapp show \
  --name dq-frontend \
  --resource-group $RESOURCE_GROUP
```

### Verify Version in Running Container

```bash
# Get frontend URL
FRONTEND_URL=$(az containerapp show \
  --name dq-frontend \
  --resource-group $RESOURCE_GROUP \
  --query properties.configuration.ingress.fqdn -o tsv)

# Fetch and check for version
curl -s https://${FRONTEND_URL} | grep -o "0\.2\.0"
```

### Common Issues

#### Issue: Version not updating

**Cause**: Frontend not rebuilt before Docker image creation

**Solution**:
```bash
# Always rebuild frontend first
cd dq-ui
npm run build  # This embeds the version
cd ..
docker compose build frontend
```

#### Issue: Container apps can't connect to database

**Cause**: Firewall rules or connection string incorrect

**Solution**:
```bash
# Add container apps to PostgreSQL firewall
az postgres flexible-server firewall-rule create \
  --resource-group $RESOURCE_GROUP \
  --name $POSTGRES_SERVER \
  --rule-name AllowAzureServices \
  --start-ip-address 0.0.0.0 \
  --end-ip-address 0.0.0.0
```

#### Issue: API not accessible from frontend

**Cause**: CORS or ingress configuration

**Solution**:
- Ensure API has `--ingress internal`
- Ensure frontend can resolve internal API FQDN
- Check CORS_ORIGIN environment variable

## Scaling Configuration

### Auto-scaling Rules

```bash
# Scale based on HTTP requests
az containerapp update \
  --name dq-api \
  --resource-group $RESOURCE_GROUP \
  --min-replicas 1 \
  --max-replicas 10 \
  --scale-rule-name http-rule \
  --scale-rule-type http \
  --scale-rule-http-concurrency 100
```

### Manual Scaling

```bash
# Scale to specific number of replicas
az containerapp update \
  --name dq-api \
  --resource-group $RESOURCE_GROUP \
  --min-replicas 3 \
  --max-replicas 3
```

## Cost Optimization

- Use **Consumption plan** for Container Apps (pay per use)
- Scale to zero when not in use (if applicable)
- Use **Burstable tier** for PostgreSQL (cost-effective for variable workloads)
- Use **Basic tier** for Redis (for non-critical caching)
- Enable **automatic pause** for PostgreSQL during off-hours

## Security Best Practices

1. **Use Managed Identities** instead of connection strings where possible
2. **Store secrets in Azure Key Vault** and reference them
3. **Enable HTTPS only** for all ingress
4. **Restrict database access** to Azure services only
5. **Use latest container images** with security patches
6. **Enable diagnostic logging** for all resources
7. **Implement network security** with VNet integration

## Additional Resources

- [Azure Container Apps Documentation](https://learn.microsoft.com/en-us/azure/container-apps/)
- [Azure Container Registry Documentation](https://learn.microsoft.com/en-us/azure/container-registry/)
- [Azure Database for PostgreSQL](https://learn.microsoft.com/en-us/azure/postgresql/)
- [Azure Cache for Redis](https://learn.microsoft.com/en-us/azure/azure-cache-for-redis/)
