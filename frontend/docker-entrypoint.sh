#!/bin/sh
set -eu

# Defaults so unset vars substitute to something valid rather than an
# empty string that config.ts would have to guess is "unset".
: "${API_BASE:=http://localhost:8000}"
: "${WS_BASE:=ws://localhost:8000}"
: "${OIDC_AUTHORITY:=https://auth.example.com/}"
: "${OIDC_CLIENT_ID:=clinical-ai-frontend}"
: "${OIDC_AUDIENCE:=clinical-ai-api}"
: "${DEV_AUTH_BYPASS:=false}"
: "${DEV_USER_ID:=dev-clinician}"
: "${DEV_TENANT_ID:=dev-tenant}"
: "${DEV_ROLES:=clinician,reviewer}"
export API_BASE WS_BASE OIDC_AUTHORITY OIDC_CLIENT_ID OIDC_AUDIENCE \
       DEV_AUTH_BYPASS DEV_USER_ID DEV_TENANT_ID DEV_ROLES

# Only substitute the specific variables we define -- passing no arg list
# to envsubst would also mangle any literal ${...} that happens to appear
# elsewhere, which is a real (if obscure) failure mode for this pattern.
envsubst '${API_BASE} ${WS_BASE} ${OIDC_AUTHORITY} ${OIDC_CLIENT_ID} ${OIDC_AUDIENCE} ${DEV_AUTH_BYPASS} ${DEV_USER_ID} ${DEV_TENANT_ID} ${DEV_ROLES}' \
  < /usr/share/nginx/html/env.template.js \
  > /usr/share/nginx/html/env.js

exec nginx -g "daemon off;"
