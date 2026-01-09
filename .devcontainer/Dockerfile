FROM ubuntu:24.04

ARG ARG_PYTHON_VERSION
ARG ARG_UV_VERSION

# Install base packages
RUN apt-get update && apt-get install -y --no-install-recommends \
    git ca-certificates bash curl wget \
    jq sudo vim unzip gpg gnupg apt-transport-https lsb-release && \
    rm -rf /var/lib/apt/lists/*

# Install GitHub CLI
RUN mkdir -p -m 755 /etc/apt/keyrings && \
    wget -qO /etc/apt/keyrings/githubcli-archive-keyring.gpg https://cli.github.com/packages/githubcli-archive-keyring.gpg && \
    chmod go+r /etc/apt/keyrings/githubcli-archive-keyring.gpg && \
    echo "deb [arch=$(dpkg --print-architecture) signed-by=/etc/apt/keyrings/githubcli-archive-keyring.gpg] https://cli.github.com/packages stable main" > /etc/apt/sources.list.d/github-cli.list && \
    apt-get update && apt-get install -y --no-install-recommends gh && \
    apt-get clean && rm -rf /var/lib/apt/lists/*

# Install uv
RUN wget -qO- https://astral.sh/uv/${ARG_UV_VERSION}/install.sh | sh && \
    cp /root/.local/bin/uv /usr/local/bin/uv && \
    cp /root/.local/bin/uvx /usr/local/bin/uvx

ENV UV_PYTHON_INSTALL_DIR=/opt/python

# Install Python using uv
RUN uv python install --install-dir /opt/python ${ARG_PYTHON_VERSION}

# Create a default virtual environment
RUN uv venv /opt/venv
ENV VIRTUAL_ENV=/opt/venv
ENV PATH="/opt/venv/bin:$PATH"
RUN uv pip install pip

# Copy source code into the workspace
RUN mkdir -p /workspace
COPY . /workspace

# Create non-root user and set permissions
RUN useradd -m -s /bin/bash devuser && \
    usermod -aG sudo devuser && \
    echo "devuser ALL=(ALL) NOPASSWD:ALL" >> /etc/sudoers && \
    chown -R devuser:devuser /opt/venv /opt/python /workspace

# Switch to non-root user
USER devuser

WORKDIR /workspace

CMD ["/bin/bash"]
