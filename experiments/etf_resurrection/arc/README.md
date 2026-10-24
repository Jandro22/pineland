# Autonomy-trap ARC campaign

From the repository root on an ARC login node (Tinkercliffs):

```bash
git pull                                              # this branch
bash experiments/etf_resurrection/arc/build_arc.sh    # tests + x86-64-v3 harness build
bash experiments/etf_resurrection/arc/submit.sh --dry-run
bash experiments/etf_resurrection/arc/submit.sh       # or add --preemptable (0 SU, may requeue)
squeue -u $USER
python3 experiments/etf_resurrection/arc/collect.py \
  --campaign campaigns/autonomy_trap_v1 --scratch /scratch/$USER/pineland/autonomy_trap_v1
```

66,576 paired production-scale worlds (1000 agents, 72 localities), 64 seeds per
condition, one whole node (128 cores) per array element. Resubmitting `submit.sh`
skips finished tasks. Blocks and variants: see `build_campaign.py`.
