#!/bin/bash
# quick.sh <contract> <outdir> : 60s-capped traced smoke run + ledger/strike summary
set -u
D=$2; mkdir -p "$D"
BIN="$(dirname "$0")/../../rust/target/release/examples/partner_force_autonomy_stage3.exe"
cp "$BIN" "$D/bin.exe"
PINELAND_FUNNEL=1 timeout 60 "$D/bin.exe" --stage4-contract "$1" --output "$D/w.csv" --trajectory-output "$D/t.csv" --allow-dirty --allow-unfrozen --smoke --execute >"$D/out.log" 2>"$D/f.log"
echo "exit=$?"
grep LEDGER "$D/f.log" | awk 'NR%2==1||1' | awk '{split($2,a,"="); if (a[2]%20==0) print}'
grep "stage=strike" "$D/f.log" | awk '{print $3,$6}' | sort | uniq -c
grep -c "org_collapse" "$D/f.log"
