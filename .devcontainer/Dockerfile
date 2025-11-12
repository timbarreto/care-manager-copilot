# Use Microsoft's base dev container image
FROM mcr.microsoft.com/devcontainers/base:ubuntu

# Install additional system dependencies
RUN apt-get update && export DEBIAN_FRONTEND=noninteractive \
    && apt-get -y install --no-install-recommends \
    build-essential \
    curl \
    ca-certificates \
    && apt-get clean -y && rm -rf /var/lib/apt/lists/*

# The features in devcontainer.json will install:
# - Python 3.11
# - Node.js LTS
# - Azure CLI
# - Git
