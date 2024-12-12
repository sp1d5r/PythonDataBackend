#!/bin/bash
set -e

echo "=== Debug: Starting script ==="
echo "Dumping environment variables (sanitized):"
# echo "GITHUB_RUNNER_APP_ID: $GITHUB_RUNNER_APP_ID"
# echo "GITHUB_RUNNER_INSTALLATION_ID: $GITHUB_RUNNER_INSTALLATION_ID"
# echo "Private key exists: [$(if [ ! -z "$GITHUB_RUNNER_PRIVATE_KEY" ]; then echo "YES"; else echo "NO"; fi)]"

# Create JWT header and payload
echo "=== Creating JWT components ==="
HEADER=$(echo -n '{"alg":"RS256","typ":"JWT"}' | base64 -w0 | tr '/+' '_-' | tr -d '=')
PAYLOAD=$(echo -n "{
 \"iat\": $(date +%s),
 \"exp\": $(date -d "+10 minutes" +%s),
 \"iss\": \"$GITHUB_RUNNER_APP_ID\"
}" | base64 -w0 | tr '/+' '_-' | tr -d '=')

# echo "Header: $HEADER"
# echo "Payload: $PAYLOAD"

# Create signature
echo "=== Creating signature ==="
UNSIGNED="$HEADER.$PAYLOAD"

echo "Debug: Creating temporary private key file..."
# Write private key to file with proper formatting
echo "=== Private key processing ==="
echo "1. Removing braces and formatting key..."
FORMATTED_KEY=$(echo "$GITHUB_RUNNER_PRIVATE_KEY" | sed 's/^{//;s/}$//' | tr -d '\n' | sed 's/\\n/\n/g')
echo "2. Writing key to temporary file..."
echo "$FORMATTED_KEY" > /tmp/private-key.pem

echo "Debug: Checking private key file contents:"
echo "=== Start of private key file ==="
head -n 1 /tmp/private-key.pem
echo "[... key content ...]"
tail -n 1 /tmp/private-key.pem
echo "=== End of private key file ==="

echo "3. Verifying private key format..."
openssl rsa -in /tmp/private-key.pem -check -noout || {
    echo "Error: Invalid private key format"
    cat /tmp/private-key.pem
    exit 1
}

echo "4. Creating signature..."
SIGNATURE=$(echo -n "$UNSIGNED" | openssl dgst -sha256 -sign /tmp/private-key.pem | openssl base64 -A | tr '/+' '_-' | tr -d '=')
rm /tmp/private-key.pem

if [ -z "$SIGNATURE" ]; then
    echo "Error: Signature generation failed"
    exit 1
fi

echo "Signature generated successfully"

# Combine into JWT token
echo "=== Creating final JWT token ==="
JWT_TOKEN="$HEADER.$PAYLOAD.$SIGNATURE"

echo "JWT token length: ${#JWT_TOKEN}"
echo "First 20 chars of JWT: ${JWT_TOKEN:0:20}..."

# Get installation token using JWT
echo "=== Getting installation token ==="
INSTALL_TOKEN_RESPONSE=$(curl -s -X POST \
    -H "Authorization: Bearer $JWT_TOKEN" \
    -H "Accept: application/vnd.github+json" \
    "https://api.github.com/app/installations/$GITHUB_RUNNER_INSTALLATION_ID/access_tokens")

echo "Installation token response: $INSTALL_TOKEN_RESPONSE"
INSTALL_TOKEN=$(echo "$INSTALL_TOKEN_RESPONSE" | jq -r .token)

if [ "$INSTALL_TOKEN" == "null" ] || [ -z "$INSTALL_TOKEN" ]; then
    echo "Error: Failed to get installation token"
    echo "Full response: $INSTALL_TOKEN_RESPONSE"
    exit 1
fi

echo "=== Getting runner token ==="
RUNNER_TOKEN_RESPONSE=$(curl -s -X POST \
    -H "Authorization: Bearer $INSTALL_TOKEN" \
    -H "Accept: application/vnd.github+json" \
    "https://api.github.com/repos/sp1d5r/PythonDataBackend/actions/runners/registration-token")

echo "Runner token response: $RUNNER_TOKEN_RESPONSE"
RUNNER_TOKEN=$(echo "$RUNNER_TOKEN_RESPONSE" | jq -r .token)

if [ "$RUNNER_TOKEN" == "null" ] || [ -z "$RUNNER_TOKEN" ]; then
    echo "Error: Failed to get runner token"
    echo "Full response: $RUNNER_TOKEN_RESPONSE"
    exit 1
fi

echo "=== Configuring and running the runner ==="
./config.sh --url https://github.com/sp1d5r/PythonDataBackend --token "$RUNNER_TOKEN" --name "fargate-runner-${RANDOM}" --ephemeral --unattended

echo "=== Starting runner with timeout ==="
timeout 300 ./run.sh

# Handle exit code
exit_code=$?
if [ $exit_code -eq 124 ]; then
    echo "Runner timed out waiting for jobs"
    exit 1
fi

echo "Script execution completed with exit code: $exit_code"
exit $exit_code