# OpenCitations Search Service

This repository contains the Search service for OpenCitations, allowing users to search and query OpenCitations datasets through a web interface.

## Configuration

### Environment Variables

The service requires the following environment variables. These values take precedence over the ones defined in `conf.json`:

- `BASE_URL`: Base URL for the search service
- `LOG_DIR`: Directory path where log files will be stored
- `SPARQL_ENDPOINT_INDEX`: URL for the index SPARQL endpoint
- `SPARQL_ENDPOINT_META`: URL for the meta SPARQL endpoint
- `SEARCH_SYNC_ENABLED`: Enable/disable static files synchronization

For instance:
```env
BASE_URL=search.opencitations.net
LOG_DIR=/home/dir/log/
SPARQL_ENDPOINT_INDEX=http://qlever-service.default.svc.cluster.local:7011  
SPARQL_ENDPOINT_META=http://virtuoso-service.default.svc.cluster.local:8890/sparql
SEARCH_SYNC_ENABLED=true
```

> **Note**: When running with Docker, environment variables always override the corresponding values in `conf.json`. If an environment variable is not set, the application will fall back to the values defined in `conf.json`.

### Static Files Synchronization

The application can synchronize static files from a GitHub repository. This configuration is managed in `conf.json`:
```json
{
  "oc_services_templates": "https://github.com/opencitations/oc_services_templates",
  "sync": {
    "folders": [
      "static",
      "html-template/common"
    ],
    "files": [
      "test.txt"
    ]
  }
}
```

- `oc_services_templates`: The GitHub repository URL to sync files from
- `sync.folders`: List of folders to synchronize
- `sync.files`: List of individual files to synchronize

## Running Options

### Local Development

This project uses [uv](https://docs.astral.sh/uv/) for dependency management. To set up the development environment:
```bash
# Install uv (if not already installed)
curl -LsSf https://astral.sh/uv/install.sh | sh

# Install dependencies
uv sync

# Run with default settings
uv run python search_oc.py

# Run with static sync enabled
uv run python search_oc.py --sync-static

# Run on custom port
uv run python search_oc.py --port 8085

# Run with both options
uv run python search_oc.py --sync-static --port 8085
```

The application supports the following command line arguments:

- `--sync-static`: Synchronize static files at startup
- `--port PORT`: Specify the port to run the application on (default: 8080)

### Production Deployment (Docker)

When running in Docker/Kubernetes, the application uses **Gunicorn** as the WSGI HTTP server for better performance and concurrency handling:

- **Server**: Gunicorn with gevent workers
- **Workers**: 4 concurrent worker processes
- **Worker Type**: gevent (async) for handling thousands of simultaneous requests
- **Timeout**: 1200 seconds (to handle long-running SPARQL queries)
- **Connections per worker**: 300 simultaneous connections

The Docker container automatically uses Gunicorn and is configured with static sync enabled by default.

> **Note**: The application code automatically detects the execution environment. When run with `uv run python search_oc.py`, it uses the built-in web.py server. When run with Gunicorn (as in Docker), it uses the WSGI interface.
You can customize the Gunicorn server configuration by modifying the `gunicorn.conf.py` file.

### Dockerfile
```dockerfile
# Base image: Python slim for a lightweight container
FROM python:3.11-slim

# Define environment variables with default values
ENV BASE_URL="search.opencitations.net" \
    LOG_DIR="/mnt/log_dir/oc_search"  \
    SPARQL_ENDPOINT_INDEX="http://qlever-service.default.svc.cluster.local:7011" \
    SPARQL_ENDPOINT_META="http://virtuoso-service.default.svc.cluster.local:8890/sparql" \
    SYNC_ENABLED="true"

# Ensure Python output is unbuffered
ENV PYTHONUNBUFFERED=1

# Install system dependencies + uv
RUN apt-get update && \
    apt-get install -y \
    git \
    python3-dev \
    build-essential \
    curl && \
    curl -LsSf https://astral.sh/uv/install.sh | sh && \
    apt-get clean && \
    rm -rf /var/lib/apt/lists/*

# Make uv available in PATH
ENV PATH="/root/.local/bin:$PATH"

# Set the working directory for our application
WORKDIR /website

# Copy dependency files first for better Docker layer caching
COPY pyproject.toml uv.lock README.md ./

# Install dependencies (frozen = use exact lockfile versions)
RUN uv sync --frozen --no-dev --no-install-project

# Copy application code
COPY . .

# Expose the port that our service will listen on
EXPOSE 8080

# Start the application with gunicorn via uv
CMD ["uv", "run", "gunicorn", "-c", "gunicorn.conf.py", "search_oc:application"]
```