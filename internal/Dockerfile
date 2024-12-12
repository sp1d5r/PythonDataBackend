# Use Ubuntu as the base image
FROM --platform=linux/amd64 ubuntu:22.04

# Set environment variables
ENV RUNNER_VERSION="2.320.0"
ENV DEBIAN_FRONTEND=noninteractive

# Install required packages
RUN apt-get update && apt-get install -y \
    curl \
    tar \
    jq \
    sudo \
    git \
    # Install .NET Core 6.0 dependencies
    libicu-dev \
    libssl-dev \
    && rm -rf /var/lib/apt/lists/*

# Create a runner user
RUN useradd -m runner && \
    usermod -aG sudo runner && \
    echo "runner ALL=(ALL) NOPASSWD:ALL" >> /etc/sudoers

# Set working directory
WORKDIR /home/runner

# Download and extract the GitHub runner
RUN curl -o actions-runner-linux-x64-${RUNNER_VERSION}.tar.gz -L \
    https://github.com/actions/runner/releases/download/v${RUNNER_VERSION}/actions-runner-linux-x64-${RUNNER_VERSION}.tar.gz && \
    tar xzf ./actions-runner-linux-x64-${RUNNER_VERSION}.tar.gz && \
    rm actions-runner-linux-x64-${RUNNER_VERSION}.tar.gz && \
    chown -R runner:runner /home/runner

# Switch to runner user
USER runner

# Create an entrypoint script
COPY --chown=runner:runner entrypoint.sh .
RUN sudo chmod +x ./entrypoint.sh

# Set the entrypoint
ENTRYPOINT ["./entrypoint.sh"]