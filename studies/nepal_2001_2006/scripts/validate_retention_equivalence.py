"""Metamorphic test: evidence retention must not alter decisions or state."""
from __future__ import annotations
from concurrent.futures import ProcessPoolExecutor
import hashlib,json,sys
from pathlib import Path
HERE=Path(__file__).resolve().parent; ROOT=HERE.parents[2];sys.path.insert(0,str(HERE))
from run_untuned_benchmark import CASE_PATH
OUT=ROOT/"studies/nepal_2001_2006/results/post_structural_repair/retention_equivalence.json"

def run_retention(days):
    from dataclasses import asdict
    from pineland_sim import SimulationConfig,generate_pineland,Simulation
    case=json.loads(CASE_PATH.read_text())
    cfg=SimulationConfig(seed=20011126,agent_count=len(case["localities"]),locality_count=len(case["localities"]),horizon_days=180,output_mode="ensemble")
    cfg.information.observation_retention_days=days
    cfg.organization_ecology.observed_active_intervals={"insurgent":[[0,180]]}
    world=Simulation(generate_pineland(cfg,empirical_geography=case)).run().world
    canonical={"beliefs":{str(k):asdict(v) for k,v in world.beliefs.items()},
               "presence_beliefs":{str(k):asdict(v) for k,v in world.presence_beliefs.items()},
               "patrols":{k:asdict(v) for k,v in world.patrols.items()},
               "movements":{k:asdict(v) for k,v in world.movement_orders.items()},
               "formations":{k:asdict(v) for k,v in world.formations.items()},
               "controls":{k:{a:asdict(v) for a,v in x.control.items()} for k,x in world.localities.items()},
               "contacts":list(zip(world.contact_event_times,world.contact_event_localities))}
    return canonical,len(world.observations)
def digest(x):return hashlib.sha256(json.dumps(x,sort_keys=True,separators=(",",":")).encode()).hexdigest()
def main():
    OUT.parent.mkdir(parents=True,exist_ok=True)
    common={"horizon_days":180.0}
    with ProcessPoolExecutor(max_workers=2) as pool:
        fa=pool.submit(run_retention,30.0); fb=pool.submit(run_retention,0.0)
        (a,acount),(b,bcount)=fa.result(),fb.result()
    payload={"horizon_days":180,"seed":20011126,"agent_count":300,"bounded_days":30,"full_days":0,
             "behaviorally_equivalent":a==b,"bounded_hash":digest(a),"full_hash":digest(b),
             "component_equivalence":{key:{"equal":a[key]==b[key],"bounded_hash":digest(a[key]),"full_hash":digest(b[key])}
                                      for key in a},
             "compared_state":["actor beliefs and confidence","presence beliefs","patrol allocation and routes","movement decisions","formations","local control","engagement times and locations"],
             "raw_observation_counts":{"bounded":acount,"full":bcount},
             "interpretation":"Raw evidence storage may differ; decisions and state must not."}
    OUT.write_text(json.dumps(payload,indent=2)+"\n");print(json.dumps(payload,indent=2))
if __name__=="__main__":main()
