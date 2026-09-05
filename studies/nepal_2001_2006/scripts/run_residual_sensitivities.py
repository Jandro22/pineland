"""Preregistered compact structural sensitivities; no Nepal outcomes are read."""
from __future__ import annotations
from concurrent.futures import ProcessPoolExecutor,as_completed
import argparse,json,os,time
from pathlib import Path
import sys

HERE=Path(__file__).resolve().parent; ROOT=HERE.parents[2]; sys.path.insert(0,str(HERE))
from run_untuned_benchmark import run_seed,atomic_json
OUT=ROOT/"studies/nepal_2001_2006/results/post_structural_repair/sensitivities"
SEEDS=(20011126,20051154)
# Frozen before execution. Values are broad engineering/theory perturbations,
# not selected from Nepal performance.
DESIGNS={
 "baseline":{"horizon_days":365.0},
 "formation_500":{"force_structure.insurgent_target_personnel":500.0},
 "formation_2000":{"force_structure.insurgent_target_personnel":2000.0},
 "reserve_080":{"logistics.organization_sustainment_coverage":.80},
 "reserve_100":{"logistics.organization_sustainment_coverage":1.00},
 "reserve_150":{"logistics.organization_sustainment_coverage":1.50},
 "endogenous_survival":{"organization_ecology.observed_active_intervals":{}},
 "full_retention":{"information.observation_retention_days":0.0},
 "no_logistics":{"logistics.formation_supply_days":1000000.0,
                  "logistics.presence_consumption_per_person_day":1e-12,
                  "logistics.movement_consumption_per_person_km":0.0,
                  "logistics.patrol_consumption_per_person_hour":0.0,
                  "logistics.readiness_degradation_rate":0.0},
 "perfect_information":{"information.contact_true_positive_rate":1.0,
                         "information.contact_false_positive_rate":0.0},
 "no_adaptive_movement":{"movement_rate":0.0},
 "no_adaptive_response":{"logistics.reallocation_rate":0.0,
                          "physical.adaptive_patrol_routing":False},
 "degree_preserving_rewire":{},
 "reduced_mixing":{"social_network.mean_social_degree":1.0,
                    "social_network.maximum_social_degree":1,
                    "social_network.bridge_fraction":0.0},
}
for _design in DESIGNS.values():
    _design.setdefault("horizon_days",365.0)
TRANSFORMS={"degree_preserving_rewire":"degree_preserving_rewire"}

def compact(row):
    latent=[e for e in row["contacts"] if e["realized"]]; recorded=[e for e in latent if e["recorded"]]
    return {"variant":row["opportunity_variant"],"seed":row["seed"],"agent_count":row["agent_count"],
            "runtime_seconds":row["runtime_seconds"],"config":row["config"],
            "latent_engagements":len(latent),"recorded_engagements":len(recorded),
            "latent_active_cells":len({(e["district_id"],int(e["day"]//7)) for e in latent}),
            "recorded_active_cells":len({(e["district_id"],int(e["day"]//7)) for e in recorded}),
            "ever_active_districts":len({e["district_id"] for e in recorded}),
            "recorded_stream":recorded,"latent_stream":latent,
            "contact_funnel":row["contact_funnel"],"movement_history":row["movement_history"],
            "initial_formations":len(row["initial_formations"]),
            "final_formations":row["final_formations"],"checkpoints":row["checkpoints"]}

def main():
    parser=argparse.ArgumentParser(); parser.add_argument("--workers",type=int,default=min(8,os.cpu_count() or 1)); parser.add_argument("--force",action="store_true"); parser.add_argument("--designs",nargs="*",choices=tuple(DESIGNS)); args=parser.parse_args()
    OUT.mkdir(parents=True,exist_ok=True); jobs=[]
    for name,overrides in DESIGNS.items():
        if args.designs and name not in args.designs: continue
        for seed in SEEDS:
            path=OUT/f"{name}_seed_{seed}.json"
            if args.force or not path.exists():jobs.append((name,seed,overrides,path))
    started=time.perf_counter()
    with ProcessPoolExecutor(max_workers=min(args.workers,max(1,len(jobs)))) as pool:
        futures={pool.submit(run_seed,seed,300,"E_combined",overrides,TRANSFORMS.get(name)):(name,seed,path) for name,seed,overrides,path in jobs}
        for future in as_completed(futures):
            name,seed,path=futures[future]; row=compact(future.result()); atomic_json(path,row)
            print(json.dumps({"design":name,"seed":seed,"recorded_active_cells":row["recorded_active_cells"]}),flush=True)
    rows=[json.loads((OUT/f"{name}_seed_{seed}.json").read_text()) for name in DESIGNS for seed in SEEDS]
    summary={name:{key:sum(json.loads((OUT/f"{name}_seed_{seed}.json").read_text())[key] for seed in SEEDS)/len(SEEDS)
                   for key in ("latent_engagements","recorded_engagements","latent_active_cells","recorded_active_cells","ever_active_districts")}
             for name in DESIGNS}
    atomic_json(OUT/"summary.json",{"parameter_fit":False,"agent_count":300,"seeds":SEEDS,"design_declared_before_results":True,
                                    "formulation_tag":"post_structural_repair_v1",
                                    "diagnostic_horizon_days":365,
                                    "horizon_justification":"52 weeks covers 6.5 times the maximum prespecified 8-week response lag and many observed one-week active spells",
                                    "wall_seconds":time.perf_counter()-started,"designs":DESIGNS,"results":summary})
if __name__=="__main__":main()
