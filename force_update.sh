#!/bin/bash
echo "Force update..."
# Stelle sicher kein Nginx cache
sudo rm -f /var/cache/nginx/* 2>/dev/null || true
# Kopiere direkt
sudo curl -sL --header "Cache-Control: no-cache" --header "Pragma: no-cache" \
  "https://raw.githubusercontent.com/RobcatRobi/charge-goertz/main/index.html" \
  -o /tmp/cg_index_new.html
echo "Downloaded: $(wc -c < /tmp/cg_index_new.html) bytes"
sudo cp /tmp/cg_index_new.html /opt/charge-goertz/web/index.html
echo "Installed: $(wc -c < /opt/charge-goertz/web/index.html) bytes"
sudo systemctl restart charge-goertz
echo "✅ Done"
