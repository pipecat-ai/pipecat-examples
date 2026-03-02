#!/bin/bash

# Script to destroy the agent and clean up generated files.
# `agentcore destroy` removes .bedrock_agentcore.yaml but not the build directory.

uv run agentcore destroy

rm -rf .bedrock_agentcore/ .bedrock_agentcore.yaml.backup
