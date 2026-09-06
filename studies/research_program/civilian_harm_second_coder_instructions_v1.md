# Blind civilian-harm second-coder instructions v1

You are independently coding historical measurement evidence. Do not inspect any Pineland model outputs, predictions, residuals, first-coder files, agreement results, or historical fit diagnostics.

Use only the packet, the frozen `civilian_harm_coding_contract_v1.json`, and the source documents named in the packet. For each `blind_task_id`, inspect the named source at the `locator_hint` and extract all claims at that locator that satisfy the frozen civilian-harm ontology. A task may contain zero, one, or several admissible claims.

Allowed components are `direct_harm`, `displacement`, and `resource_loss`. Use the exact measure vocabulary in the coding contract. Allowed actor categories are exactly: `government`, `insurgent`, `foreign_or_international_force`, `multiple_or_crossfire`, `other_armed_actor`, and `unknown_or_unattributed`. Do not put historical actor names such as Taliban, CPN-M, RNA, or NATO into the actor category; preserve them only in `notes` when useful.

Preserve source-native units and uncertainty. Deaths are not injuries; casualties are not silently decomposed; flows are not stocks; internal displacement is not cross-border refuge; qualitative uncertainty is not converted into invented numerical bounds; `unknown` is never coded as zero. Do not infer perpetrator from control, geography, or event type beyond what the source states. Do not convert violence-event counts into civilian harm.

Output one or more rows per task using these columns exactly:

`blind_task_id,claim_local_id,task_admissible,component,measure,value_point,value_lower,value_upper,unit,victim_class,actor_attribution,actor_attribution_certainty,date_start,date_end,temporal_precision,geographic_scope_type,geographic_scope_name_or_id,source_coverage_scope,source_access_or_reporting_limitation,verification_status,notes`

If there is no admissible claim at a task locator, output exactly one row with `claim_local_id=NONE`, `task_admissible=false`, and explain the exclusion briefly in `notes`; leave unsupported fields blank. Otherwise set `task_admissible=true` and use local claim ids such as `C01`, `C02`, etc. Do not attempt to guess what another coder may have selected.

Do not adjudicate disagreements and do not inspect any first-coder or agreement artifact after completing the packet.
