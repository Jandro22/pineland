import sys
from pathlib import Path
ROOT=Path.cwd()
sys.path.insert(0,str(ROOT/'src'))
sys.path.insert(0,str(ROOT/'studies/afghanistan_2004_2021/scripts'))
from historical_case import HistoricalCoalitionSchedule
from run_transfer_test import build_conditioned_world, initialization_gate
from pineland_sim import Simulation
h=1096
world,inputs=build_conditioned_world(20070113,float(h),5000)
print('init',initialization_gate(world,inputs,5000)['passed'],flush=True)
schedule=HistoricalCoalitionSchedule(inputs)
result=Simulation(world,policy_hook=lambda state,day:schedule(state,day)).run()
print('OK',h,result.events_processed,result.stopped_at,world.stock_ledger_residual(),world.supply_conservation_residual(),world.global_accounting_diagnostics()['population_residual'],flush=True)
