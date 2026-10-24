"""Print dynamics of fullcheck trajectories: personnel, contacts/30d, ON-OFF gaps."""
import csv, sys
from pathlib import Path
R = Path(sys.argv[1])
for f in sorted(R.glob("*.traj.csv")):
    rows = list(csv.DictReader(open(f)))
    print(f"== {f.stem}")
    print(" day  phase  ins_pers ins_forms ins_ctrl  mil_pers  rdy   gov_ctrl contacts_30d mil_loss_30d")
    by = {}
    for r in rows:
        by.setdefault(r["phase"], []).append(r)
    for ph, rs in by.items():
        acc_c = acc_l = 0.0; last = 0.0
        for r in rs:
            t = float(r["time_days"]); acc_c += float(r["interval_contacts"]); acc_l += float(r["interval_military_losses"])
            if t - last >= 30 or r is rs[-1]:
                print(f"{t:5.0f} {ph[:8]:8s} {float(r['insurgent_personnel']):8.0f} {r['insurgent_active_formations']:>5s} {float(r['insurgent_territorial_control']):7.3f} {float(r['military_personnel']):8.0f} {float(r['readiness']):5.3f} {float(r['government_control']):7.3f} {acc_c:8.0f} {acc_l:9.0f}")
                acc_c = acc_l = 0.0; last = t
