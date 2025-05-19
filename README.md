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
SEARCH_BASE_URL=search.opencitations.net
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

The application supports the following command line arguments:

- `--sync-static`: Synchronize static files at startup
- `--port PORT`: Specify the port to run the application on (default: 8080)

Examples:
```bash
# Run with default settings
python3 search_oc.py

# Run with static sync enabled
python3 search_oc.py --sync-static

# Run on custom port
python3 search_oc.py --port 8085

# Run with both options
python3 search_oc.py --sync-static --port 8085
```

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

# Install system dependencies
RUN apt-get update && \
    apt-get install -y \
    git \
    python3-dev \
    build-essential && \
    apt-get clean

WORKDIR /app

# Clone the repository
RUN git clone --single-branch --branch main https://github.com/opencitations/oc_search .

# Install Python dependencies
RUN pip install -r requirements.txt

# Expose port
EXPOSE 8080

# Start the application
CMD ["python3", "search_oc.py", "--sync-static"]
```
