# Nepal control/presence second-coder protocol v1

Work only from `nepal_second_coder_packet_v1.csv` and the linked sources. Do **not** inspect the first-coder staging file or blind key until your coding is final.

For each row, independently decide whether the source supports a dated, actor-specific control/presence observable in the target district. The target district and sampling window identify the preregistered search cell; they are not a required answer. If the source does not support an admissible observation, write `NOT_ADMISSIBLE` in `observable` and explain why.

Allowed observables are: `government_armed_presence`, `maoist_armed_presence`, `government_administrative_presence`, `maoist_shadow_governance`, `checkpoint_or_patrol_presence`, `security_post_or_garrison_presence`, `territorial_access_constraint`, `territorial_control_claim`.

Do not infer control from violence, fatalities, attack occurrence, non-reporting, or presumed political support. Preserve the narrowest spatial and temporal scope directly supported by the source. Do not carry an observation forward/backward. Use `HIGH`, `MEDIUM`, or `LOW` confidence and explain the basis briefly.

Fill every `coder_*`, actor/observable/value/scope/confidence field plus your coder name/identifier. Return the completed CSV without consulting the first-pass codes. Adjudication occurs only after both codings are locked.
