#!/bin/bash
# fullcheck.sh <label> [seed]: full-horizon untraced runs for 3 cells in parallel, then dynamics table
cd "$(dirname "$0")/../.."
L=$1; S=${2:-2026200000}; R=experiments/etf_resurrection/results/local_v6/$L; mkdir -p $R
BIN=rust/target/release/examples/partner_force_autonomy_stage3.exe; cp $BIN $R/bin.exe
for c in forcegen logistics command; do
  python - "$c" "$S" "$R" <<'PY'
import json,sys
c,s,R=sys.argv[1],int(sys.argv[2]),sys.argv[3]
d=json.load(open(f"experiments/etf_resurrection/results/local_v6/fast/c_{c}_s0_r008/contract.json"))
d["seed_base"]=s; d["horizons_days"]=[7.0,30.0,90.0,180.0,360.0]
json.dump(d,open(f"{R}/{c}.json","w"))
PY
  timeout 900 $R/bin.exe --stage4-contract $R/$c.json --output $R/$c.csv --trajectory-output $R/$c.traj.csv --allow-dirty --allow-unfrozen --execute > $R/$c.out 2>&1 &
done
wait
python experiments/etf_resurrection/dynamics.py $R
