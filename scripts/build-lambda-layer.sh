#!/usr/bin/env bash
# Builds the Lambda layer for the IoT-to-Kafka producer (kafka-python +
# aws-msk-iam-sasl-signer-python). Both are pure Python (no compiled
# extensions) so a plain pip install works for the Lambda Linux runtime
# regardless of build host OS. Idempotent: skips if the layer already exists
# unless FORCE=1.
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT_DIR="$(cd "$SCRIPT_DIR/.." && pwd)"
LAYER_DIR="$ROOT_DIR/lambda/layer/python"

if [[ -d "$LAYER_DIR" && -n "$(ls -A "$LAYER_DIR" 2>/dev/null)" && "${FORCE:-0}" != "1" ]]; then
  echo "[build-lambda-layer] layer already built at $LAYER_DIR, skipping (set FORCE=1 to rebuild)"
  exit 0
fi

rm -rf "$LAYER_DIR"
mkdir -p "$LAYER_DIR"

pip3 install --no-cache-dir --only-binary=:none: \
  -t "$LAYER_DIR" \
  "kafka-python==3.0.8"

# botocore/boto3 are not bundled here - they already ship in the standard
# Lambda Python runtime and provide the credentials kafka-python's native
# AWS_MSK_IAM sasl mechanism signs with (the Lambda execution role).
echo "[build-lambda-layer] layer built at $LAYER_DIR"
