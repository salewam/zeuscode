#!/bin/bash
set -e
for d in /tmp/sto-cheap4-bake/*/src/frontend; do
  [ -f "$d/index.html" ] || continue
  name=$(basename "$(dirname "$(dirname "$d")")")
  DEST="/var/www/sto-demos/cheap4-$name"
  mkdir -p "$DEST"
  cp -f "$d/index.html" "$DEST/"
  [ -f "$d/app.js" ] && cp -f "$d/app.js" "$DEST/" || true
  cp -f "$d/styles.css" "$DEST/"
  if ! grep -q 'a.tel' "$DEST/styles.css"; then
    sed -i 's/\.tel{color:var(--amber)}/.tel,.top__nav a.tel{color:var(--amber);font-weight:700;text-decoration:none}/g' "$DEST/styles.css"
  fi
  sed -i 's|href="styles.css[^"]*"|href="styles.css?v=c4"|g' "$DEST/index.html"
  echo "pub $name $(wc -c <"$DEST/index.html")"
done

SNIP=/etc/nginx/snippets/sto-cheap4-demos.conf
: > "$SNIP"
for d in /var/www/sto-demos/cheap4-*; do
  [ -d "$d" ] || continue
  name=$(basename "$d")
  slug=${name#cheap4-}
  echo "    location /demo/sto-cheap4-${slug}/ { alias ${d}/; index index.html; }" >> "$SNIP"
done
cat "$SNIP"

NGINX=/etc/nginx/sites-available/retainer-ip
if ! grep -q 'sto-cheap4-demos.conf' "$NGINX"; then
  # insert include after agents4 location line
  sed -i '/location \/demo\/sto-agents4\//a\    include /etc/nginx/snippets/sto-cheap4-demos.conf;' "$NGINX"
fi
nginx -t && systemctl reload nginx && echo nginx_ok
ls /var/www/sto-demos/ | grep cheap4
