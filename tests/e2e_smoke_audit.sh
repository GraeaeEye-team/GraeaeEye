#!/usr/bin/env bash
set -e
BASE_URL="http://127.0.0.1:8001"

echo "=== 1. Healthcheck ==="
curl -s -f "$BASE_URL/health" | grep -q "ok" && echo "Healthcheck PASS"

echo "=== 2. Регистрация и получение токена ==="
curl -s -X POST "$BASE_URL/api/v1/auth/register" \
  -H "Content-Type: application/json" \
  -d '{"email":"pipeline_auditor@graeae.eye","password":"StrongAuditorPass2026!","full_name":"Chief Auditor"}' > /dev/null || true

TOKEN=$(curl -s -X POST "$BASE_URL/api/v1/auth/token" \
  -H "Content-Type: application/x-www-form-urlencoded" \
  -d "username=pipeline_auditor@graeae.eye&password=StrongAuditorPass2026!" | python3 -c "import sys, json; print(json.load(sys.stdin)['access_token'])")

test -n "$TOKEN" && echo "Auth PASS (JWT acquired)"

echo "=== 3. Подготовка пакета реальных документов (MDL/RO/RU) ==="
cat << 'EOF' > /tmp/audit_statement.csv
Sold precedent: 50000.00 MDL
Data,Descriere,Suma,Directie,Sold
2026-01-05,Incasare factura client SRL Alfa,25000.00,INFLOW,75000.00
2026-01-10,Plata chirie depozit,8000.00,OUTFLOW,67000.00
2026-01-15,Achitare impozit pe venit,4500.00,OUTFLOW,62500.00
EOF

cat << 'EOF' > /tmp/audit_invoices.csv
Număr factură,Data emiterii,Data scadenței,Suma totală,Nume client,Tip factură,Statut
INV-2026-001,2026-01-02,2026-01-20,25000.00,SRL Alfa,IESIRE,ACHITAT
INV-2026-002,2026-01-08,2026-01-28,12000.00,Beta Tehnologii SRL,IESIRE,NEACHITAT
EOF

cat << 'EOF' > /tmp/audit_credits.csv
Кредитор,Тип обязательства,Лимит,Остаток задолженности,Ставка %,Ежемесячный платеж,Просрочка дней
Moldova Agroindbank,КРЕДИТНАЯ ЛИНИЯ,200000.00,45000.00,12.5%,3800.00,0
EOF

echo "=== 4. Отправка пакета в центральный пайплайн (POST /analysis/start) ==="
START_RESP=$(curl -s -X POST "$BASE_URL/api/v1/analysis/start" \
  -H "Authorization: Bearer $TOKEN" \
  -F "input_company_name=Universal Agro Trade SRL" \
  -F "input_tax_id=1003600099881" \
  -F "input_industry_code=G46" \
  -F "bank_statement_file=@/tmp/audit_statement.csv;type=text/csv" \
  -F "invoices_file=@/tmp/audit_invoices.csv;type=text/csv" \
  -F "credit_obligations_file=@/tmp/audit_credits.csv;type=text/csv")

RUN_ID=$(echo "$START_RESP" | python3 -c "import sys, json; data=json.load(sys.stdin); print(data.get('run_id') or data.get('analysis_id'))")
echo "Analysis initiated! RUN_ID: $RUN_ID"

echo "=== 5. Мониторинг фонового конвейера через SSE-стрим ==="
# Читаем до 30 секунд или до финального статуса
curl -N -s -H "Authorization: Bearer $TOKEN" "$BASE_URL/api/v1/analysis/stream/$RUN_ID" | while read -r line; do
    echo "$line"
    if echo "$line" | grep -qE "COMPLETED|FAILED"; then
        echo "Stream finished."
        break
    fi
done

echo "=== 6. Получение финального отчета андеррайтера ==="
REPORT=$(curl -s -f -H "Authorization: Bearer $TOKEN" "$BASE_URL/api/v1/analysis/report/$RUN_ID")

echo "$REPORT" | python3 -c "
import sys, json
data = json.load(sys.stdin)
print(f\"Universal Score: {data.get('universal_score')}\")
print(f\"Risk Band / Verdict: {data.get('risk_band')} / {data.get('verdict')}\")
print(f\"Probability of Default: {data.get('probability_of_default')}\")
features = data.get('features') or {}
print(f\"Feature Vector 18D Count: {len(features)}\")
assert len(features) == 18, f'Expected 18 features, got {len(features)}'
assert data.get('universal_score') is not None, 'Score missing'
print('Final Report Validation: SUCCESS')
"
