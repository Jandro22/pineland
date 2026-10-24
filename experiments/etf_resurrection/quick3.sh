#!/bin/bash
# quick3.sh <label>: rebuild, then 60s-capped smoke for forcegen/logistics/command in parallel
cd "$(dirname "$0")/../.."
L=$1; R=experiments/etf_resurrection/results/local_v6; mkdir -p $R/$L
(cd rust && cargo build --release --example partner_force_autonomy_stage3 2>&1 | grep -E "^error" -A8) || true
for c in forcegen logistics command; do
  experiments/etf_resurrection/quick.sh $R/fast/c_${c}_s0_r008/contract.json $R/$L/$c > $R/$L/$c.txt 2>&1 &
done
mkdir -p $R/$L; wait
for c in forcegen logistics command; do echo "== $c"; cat $R/$L/$c.txt | grep -v "t=0.0\|t=20.0\|t=40.0\|t=60.0"; done
