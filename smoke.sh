#!/usr/bin/env bash
set -u
BASE=${BASE:-http://localhost:8080}
ADMIN_KEY=${ADMIN_KEY:?set ADMIN_KEY first}
pass=0; fail=0
code() { curl -s -o /dev/null -w "%{http_code}" "$@"; }
jget() { python -c "import sys,json;print(json.load(sys.stdin)['$1'])"; }
check() { # desc expected actual
  if [ "$2" = "$3" ]; then echo "PASS  $1 ($3)"; pass=$((pass+1));
  else echo "FAIL  $1 (expected $2, got $3)"; fail=$((fail+1)); fi; }

check "no-auth 401" 401 "$(code $BASE/v1/models)"
TID=$(curl -s -X POST $BASE/v1/tenants -H "Authorization: Bearer $ADMIN_KEY" \
  -H "Content-Type: application/json" -d '{"name":"smoke-acme"}' | jget id)
check "create tenant" 32 "${#TID}"
check "dup tenant 409" 409 "$(code -X POST $BASE/v1/tenants \
  -H "Authorization: Bearer $ADMIN_KEY" -H "Content-Type: application/json" \
  -d '{"name":"smoke-acme"}')"
R=$(curl -s -X POST $BASE/v1/tenants/$TID/api-keys -H "Authorization: Bearer $ADMIN_KEY" \
  -H "Content-Type: application/json" -d '{"name":"r","roles":["model.read"]}')
RK=$(echo "$R" | jget api_key); RID=$(echo "$R" | jget id)
check "reader read 200" 200 "$(code $BASE/v1/models -H "Authorization: Bearer $RK")"
check "reader write 403" 403 "$(code -X POST $BASE/v1/models \
  -H "Authorization: Bearer $RK" -H "Content-Type: application/json" \
  -d '{"name":"m","family":"llama"}')"
check "revoke" 200 "$(code -X POST $BASE/v1/tenants/$TID/api-keys/$RID/revoke \
  -H "Authorization: Bearer $ADMIN_KEY")"
check "revoked 401" 401 "$(code $BASE/v1/models -H "Authorization: Bearer $RK")"
echo "-----"; echo "PASS=$pass FAIL=$fail"
[ "$fail" -eq 0 ]
