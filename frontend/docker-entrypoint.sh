#!/bin/sh
set -eu

# Only substitute the specific variables we define -- passing no arg list
# to envsubst would also mangle any literal ${...} that happens to appear
# elsewhere, which is a real (if obscure) failure mode for this pattern.
envsubst '${API_BASE} ${WS_BASE} ${OIDC_AUTHORITY} ${OIDC_CLIENT_ID} ${OIDC_AUDIENCE}' \
  < /usr/share/nginx/html/env.template.js \
  > /usr/share/nginx/html/env.js

exec nginx -g "daemon off;"
