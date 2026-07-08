# OpenShift MCP Auto-Reconnect Patch

## The Bug

When Odysseus users add custom MCP servers (stdio transport), those servers die after the first tool use with the error `Attempted to exit cancel scope in a different task than it was entered in`. Built-in MCP servers (image, memory, RAG, email, browser) are immune because they already have auto-reconnect logic. User-added servers fail permanently once their session dies, making the skill unusable for custom integrations.

## The Fix

This patch extends Odysseus's MCP auto-reconnect to user-added servers by:
1. Adding a `_reconnect_user()` method that tears down and reconnects servers from their persisted database row (mirroring the existing `_reconnect_builtin()` logic)
2. Removing the gate that limited reconnection attempts to builtin servers only
3. Allowing any stdio server to recover when its subprocess crashes

## Why ConfigMap Overlay

The patch is deployed as a Kubernetes ConfigMap volume mount that overlays `/app/src/mcp_manager.py` in the running pod. This approach:
- Survives pod restarts without requiring image rebuilds
- Is easily reversible (`./apply-mcp-patch.sh --remove`)
- Requires no base image changes, so it works with upstream Odysseus releases

This is a stopgap pending an upstream fix to release this reconnection logic in the mainline Odysseus image.

## Usage

### Apply the patch

```bash
./openshift/apply-mcp-patch.sh [-n NAMESPACE]
```

Default namespace is `odysseus`. The script:
1. Locates the running Odysseus pod
2. Verifies it's running the exact upstream version (checks MD5 checksum)
3. Creates a ConfigMap from the patched file
4. Mounts it into the Odysseus deployment
5. Waits for rollout to complete
6. Verifies the patch by checking for the `_reconnect_user` method

If the pod is already running a patched version, the script exits with "already patched" (idempotent).

### Remove the patch

```bash
./openshift/apply-mcp-patch.sh --remove [-n NAMESPACE]
```

Removes the ConfigMap volume mount and deletes the ConfigMap.

## Checksum Verification

The script MD5-checks the pod's `mcp_manager.py` before patching:
- **Match upstream checksum** (`eaf7e0085ba0d25a602d513cebc37607`): Patch is applied
- **Match patched checksum** (`39ffa8f9f1fdcfa7aae9177d66ae88ee`): Already patched, exit 0
- **Match neither**: Refuse with error `unknown Odysseus version; regenerate the patch — see README`

### Regenerating the patch for a newer Odysseus

If a new Odysseus release is used, regenerate `mcp_manager_patched.py`:
1. Download the new unpatched `src/mcp_manager.py` from the upstream Odysseus release
2. Locate the exception handler in `call_tool()` (around line 450-470) where `_reconnect_builtin()` is called
3. Change the gate from `if self.is_builtin(server_id):` to a two-branch pattern that calls either `_reconnect_builtin()` or `_reconnect_user()` depending on server type
4. Ensure the `_reconnect_user()` method (lines 479-514 in the current patch) is included with appropriate database imports (`from core.database import McpServer, SessionLocal`)
5. Update the checksums in `apply-mcp-patch.sh` (lines 13-14)
6. Test with `bash -n apply-mcp-patch.sh` and a test Odysseus pod

The patch region is self-describing: search for `_reconnect_user` and the surrounding `is_builtin()` gate to identify what needs to change.
