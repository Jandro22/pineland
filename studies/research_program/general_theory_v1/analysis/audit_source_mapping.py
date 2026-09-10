from __future__ import annotations
import argparse, hashlib, json, re, subprocess
from pathlib import Path

ROOT=Path(__file__).resolve().parents[4]
MODEL=ROOT/'rust/pineland-model/src'
CORE=ROOT/'rust/pineland-core/src'
PATTERNS={
 'M_membership':['people.organization','people.armed_fraction','people.represented_population','people.home','people.residence','people.social_exposure','manpower.pool'],
 'F_fielded':['formations.personnel','formations.readiness','formations.sustainment','formations.embeddedness','formations.availability','formations.command'],
 'L_logistics':['formations.supply_stock','manpower.supply_reserve','logistics.source_stock','logistics.source_production','shipment_'],
 'K_information':['beliefs.','presence_beliefs.','information_observations','formations.information','organizations.local_knowledge'],
 'E_foothold':['footholds.strength','footholds.renewal_count','footholds.cumulative_arrivals','footholds.cumulative_recruits','footholds.cumulative_actions'],
 'C_control':['government_control','insurgent_control','organization_control'],
 'X_expectations':['expected_control','political_access','state_legitimacy','government_legitimacy','grievance','fear','trust_insurgent'],
 'S_state':['political.institution_','security_posts.','government_governance','administrative_capacity'],
 'U_external':['foreign_interventions.','external_support','external_sanctuary']
}
FOOTHOLD_FIELDS=['strength','raw_signal','membership','embeddedness','access','target_knowledge','infrastructure','sustainment','updated_at','first_activated_at','last_activated_at','cumulative_active_days','cumulative_arrivals','cumulative_recruits','cumulative_actions','viable_activation_count','renewal_count','active']

def sha(p:Path): return hashlib.sha256(p.read_bytes()).hexdigest()
def git(*a): return subprocess.check_output(['git',*a],cwd=ROOT,text=True,errors='replace').strip()

def occurrences(pattern:str):
    out=[]
    for p in sorted(MODEL.glob('*.rs')):
        for n,line in enumerate(p.read_text(encoding='utf-8').splitlines(),1):
            if pattern in line:
                out.append({'file':str(p.relative_to(ROOT)).replace('\\','/'),'line':n,'text':line.strip()[:240]})
    return out

def main():
    ap=argparse.ArgumentParser(); ap.add_argument('--out',default=str(ROOT/'studies/research_program/general_theory_v1/source_mapping_audit_v1.json')); ns=ap.parse_args()
    construct={}
    for k,pats in PATTERNS.items():
        construct[k]={pat:{'count':len(occurrences(pat)),'files':sorted({x['file'] for x in occurrences(pat)})} for pat in pats}
    footholds={}
    for f in FOOTHOLD_FIELDS:
        occ=occurrences('footholds.'+f)
        non_init=[x for x in occ if not (x['file'].endswith('/lib.rs') and 3400 <= x['line'] <= 3600) and not x['file'].endswith('/foreign.rs')]
        footholds[f]={'total_occurrences':len(occ),'non_initializer_occurrences':len(non_init),'files':sorted({x['file'] for x in occ}),'sample':occ[:12]}
    source=list(sorted(MODEL.glob('*.rs')))+[CORE/'state.rs',CORE/'config.rs']
    result={
      'schema_version':'pineland.source_mapping_audit.v1','status':'source_audit_not_mechanism_validation','historical_outcomes_used':False,
      'git_head':git('rev-parse','HEAD'),'rust_source_sha256':{str(p.relative_to(ROOT)).replace('\\','/'):sha(p) for p in source},
      'construct_pattern_usage':construct,'foothold_field_usage':footholds,
      'adjudicated_findings':[
        {'id':'A1','finding':'local embeddedness uses a probabilistic-OR composition of member, pool, formation, and institutional channels','evidence':'rust/pineland-model/src/organizations.rs::local_embeddedness'},
        {'id':'A2','finding':'recruitment access uses a max operator across social, formation, member, and foothold access','evidence':'rust/pineland-model/src/recruitment.rs::update'},
        {'id':'A3','finding':'FootholdState access/target_knowledge/infrastructure/sustainment have substantially weaker live transition usage than foothold strength and renewal counters','evidence':'field-level occurrence audit; absence of a read is evidence about implementation, not substantive irrelevance'},
        {'id':'A4','finding':'global organization local_knowledge and locality-specific information coexist; they must not be collapsed without a closure test','evidence':'OrganizationState.local_knowledge plus BeliefState/PresenceState/FormationState.information'},
        {'id':'A5','finding':'adapt_organization implements stochastic phenotype mutation around current traits, not explicit reward-directed strategic learning','evidence':'rust/pineland-model/src/organizations.rs::adapt_organization'}
      ]
    }
    Path(ns.out).write_text(json.dumps(result,indent=2)+"\n",encoding='utf-8'); print(ns.out)
if __name__=='__main__': main()
