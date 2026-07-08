#!/bin/bash
set -euo pipefail

# OpenShift MCP auto-reconnect patch deployment script
# Applies the Odysseus MCP manager patch to enable user-added server reconnection
# Usage: ./apply-mcp-patch.sh [-n NAMESPACE] [--remove]

NAMESPACE="${1:-odysseus}"
MODE="apply"

# Parse arguments
while [[ $# -gt 0 ]]; do
    case "$1" in
        -n|--namespace)
            NAMESPACE="$2"
            shift 2
            ;;
        --remove)
            MODE="remove"
            shift
            ;;
        *)
            echo "Unknown argument: $1" >&2
            exit 1
            ;;
    esac
done

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
UPSTREAM_MD5="eaf7e0085ba0d25a602d513cebc37607"
PATCHED_MD5="39ffa8f9f1fdcfa7aae9177d66ae88ee"
CONFIGMAP_NAME="odysseus-mcp-manager-patch"
VOLUME_NAME="mcp-manager-patch"
MOUNT_PATH="/app/src/mcp_manager.py"

if [[ "$MODE" == "remove" ]]; then
    echo "Removing MCP patch from namespace: $NAMESPACE"

    # Remove volume from deployment
    oc -n "$NAMESPACE" set volume deploy/odysseus --remove --name="$VOLUME_NAME" || true

    # Delete ConfigMap
    oc -n "$NAMESPACE" delete configmap "$CONFIGMAP_NAME" || true

    echo "MCP patch removed successfully"
    exit 0
fi

# Apply mode
echo "Applying MCP patch to namespace: $NAMESPACE"

# Find the running Odysseus pod
POD=$(oc -n "$NAMESPACE" get pods -o name | grep odysseus | head -1 | sed 's|^pods/||')
if [[ -z "$POD" ]]; then
    echo "Error: No Odysseus pod found in namespace $NAMESPACE" >&2
    exit 1
fi

echo "Found pod: $POD"

# Get MD5 of the pod's current mcp_manager.py
CURRENT_MD5=$(oc -n "$NAMESPACE" exec "$POD" -- md5sum /app/src/mcp_manager.py | awk '{print $1}')
echo "Current file MD5: $CURRENT_MD5"

# Check if already patched
if [[ "$CURRENT_MD5" == "$PATCHED_MD5" ]]; then
    echo "Already patched with current version"
    exit 0
fi

# Check if it's the unpatched upstream version
if [[ "$CURRENT_MD5" != "$UPSTREAM_MD5" ]]; then
    echo "Error: unknown Odysseus version; regenerate the patch — see README" >&2
    exit 1
fi

echo "Upstream version confirmed, proceeding with patch application"

# Create/replace ConfigMap
echo "Creating/updating ConfigMap..."
oc -n "$NAMESPACE" create configmap "$CONFIGMAP_NAME" \
    --from-file=mcp_manager.py="$SCRIPT_DIR/mcp_manager_patched.py" \
    --dry-run=client -o yaml | oc apply -f -

# Check if volume already exists
EXISTING_VOLUMES=$(oc -n "$NAMESPACE" get deploy odysseus -o jsonpath='{.spec.template.spec.volumes[*].name}')
if echo "$EXISTING_VOLUMES" | grep -q "$VOLUME_NAME"; then
    echo "Volume $VOLUME_NAME already exists, skipping add"
else
    echo "Adding volume and mount..."
    oc -n "$NAMESPACE" set volume deploy/odysseus \
        --add \
        --name="$VOLUME_NAME" \
        --type=configmap \
        --configmap-name="$CONFIGMAP_NAME" \
        --mount-path="$MOUNT_PATH" \
        --sub-path=mcp_manager.py
fi

# Wait for rollout to complete
echo "Waiting for deployment to rollout..."
oc -n "$NAMESPACE" rollout status deploy/odysseus --timeout=180s

# Get the new pod name
NEW_POD=$(oc -n "$NAMESPACE" get pods -o name | grep odysseus | head -1 | sed 's|^pods/||')
echo "New pod: $NEW_POD"

# Verify the patch was applied
echo "Verifying patch application..."
RECONNECT_COUNT=$(oc -n "$NAMESPACE" exec "$NEW_POD" -- grep -c _reconnect_user /app/src/mcp_manager.py || echo 0)
if (( RECONNECT_COUNT >= 2 )); then
    echo "Success! Patch verified: found $_reconnect_user method ($RECONNECT_COUNT occurrences)"
    exit 0
else
    echo "Error: Patch verification failed - could not find expected _reconnect_user implementation" >&2
    exit 1
fi
