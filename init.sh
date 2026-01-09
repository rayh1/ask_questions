#!/bin/bash

# GitHub authentication
if [ -z "$GH_TOKEN" ]; then
  echo "GH_TOKEN is not set. Authenticating..."
  gh auth login
  if [ $? -eq 0 ]; then
    echo "Authentication successful."
  else
    echo "Authentication failed. Please try again."
    exit 1
  fi
else
  echo "GH_TOKEN is set. No need to authenticate."
fi

cd /workspace

# Initialize Python project with uv (if pyproject.toml exists)
if [ -f "pyproject.toml" ]; then
  echo "Initializing Python project..."
  uv sync
fi

# Install Node.js dependencies (if package.json exists)
if [ -f "package.json" ]; then
  echo "Installing Node.js dependencies..."
  npm install
fi

# Configure git user if not already set
current_name="$(git config --global --get user.name || true)"
current_email="$(git config --global --get user.email || true)"

if [ -z "$current_name" ]; then
  read -r -p "Git global user.name is not set. Enter your full name: " user_name
  while [ -z "$user_name" ]; do
    read -r -p "Name cannot be empty. Enter your full name: " user_name
  done
  git config --global user.name "$user_name"
  echo "Set git global user.name to '$user_name'"
else
  echo "Git global user.name already set to '$current_name'"
fi

if [ -z "$current_email" ]; then
  read -r -p "Git global user.email is not set. Enter your email: " user_email
  while ! echo "$user_email" | grep -q -E '^[^@[:space:]]+@[^@[:space:]]+\.[^@[:space:]]+$'; do
    read -r -p "Please enter a valid email address (e.g. user@example.com): " user_email
  done
  git config --global user.email "$user_email"
  echo "Set git global user.email to '$user_email'"
else
  echo "Git global user.email already set to '$current_email'"
fi

echo "Environment ready for development!"
