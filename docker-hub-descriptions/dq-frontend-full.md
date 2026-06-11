# Data Quality Made Easy - Web UI

React-based single-page application (SPA) for managing data quality rules. Built with Vite and React, served via Nginx.

## Features

- Interactive rule builder interface
- Data source management
- Rule execution monitoring
- Data profiling results viewer
- Rule suggestions from profiling
- Authentication via Keycloak (OIDC)
- Responsive design
- Dark theme support

## Quick Start

```bash
# Pull image
docker pull jacbeekers/dq-frontend:latest

# Run frontend
docker run -d \
  -p 5173:80 \
  -e KONG_PUBLIC_URL=http://kong:9111 \
  jacbeekers/dq-frontend:latest
```

Access at: http://localhost:5173

## Environment Variables

| Variable | Description | Default |
|----------|-------------|---------|
| `KONG_PUBLIC_URL` | Runtime backend API URL override (preferred) | http://localhost:9111 |
| `VITE_API_URL` | Backend API URL fallback (compatibility) | http://localhost:9111 |

## Exposed Ports

- **80** - HTTP (map to 5173 on host)

## Technology Stack

- React 18 with TypeScript
- Vite for build tooling
- React Router for navigation
- Axios for API communication
- Nginx as web server

## Browser Support

Modern browsers with ES2020+ JavaScript support:
- Chrome (latest)
- Firefox (latest)
- Safari (latest)
- Edge (latest)

## Tags

- `latest` - Most recent build
- `0.3.0-xxxxxxx` - Semantic version with content hash

## Part of Data Quality Made Easy Platform

Complete deployment: [GitHub Repository](https://github.com/jacbeekers/dq-rulebuilder)
