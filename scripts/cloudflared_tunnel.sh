#!/usr/bin/env bash
# Publish ImageLab through a Cloudflare quick tunnel.
#   ./scripts/cloudflared_tunnel.sh [machine]
set -euo pipefail

MACHINE="${1:-kromoss}"
cd "$(dirname "$0")/.."

echo "==> Uploading the tunnel unit and installer to $MACHINE"
kube-labs exec "$MACHINE" -- mkdir -p /srv/imagelab/systemd /srv/imagelab/scripts
kube-labs cp systemd/imagelab-tunnel.service "$MACHINE":/srv/imagelab/systemd/imagelab-tunnel.service
kube-labs cp scripts/remote_tunnel.sh "$MACHINE":/srv/imagelab/scripts/remote_tunnel.sh

kube-labs exec "$MACHINE" -- bash /srv/imagelab/scripts/remote_tunnel.sh
