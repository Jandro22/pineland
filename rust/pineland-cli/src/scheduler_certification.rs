//! Cross-language scheduler ordering certificate.

use super::Arguments;
use pineland_core::json::JsonValue;
use pineland_core::scheduler::{EventPayload, ScheduledEvent, Scheduler};
use pineland_core::sha256;

const BULK_EVENTS: usize = 12_000;
const PREFIX_EVENTS: usize = 64;
const KINDS: [&str; 22] = [
    "patrol",
    "contact_scan",
    "command",
    "force_movement",
    "logistics",
    "information",
    "beliefs",
    "physical_refresh",
    "social_influence",
    "mobility",
    "recruitment",
    "organization_ecology",
    "governance",
    "economy",
    "political_order",
    "foreign_affairs",
    "peace_process",
    "recording_noise",
    "checkpoint",
    "organized_action",
    "contact",
    "custom",
];

pub(crate) fn certify_scheduler(_arguments: &Arguments) -> Result<(), String> {
    let mut scheduler = Scheduler::new();
    let initial_count = KINDS.len() + BULK_EVENTS;
    for (index, kind) in KINDS.iter().enumerate() {
        schedule_kind(
            &mut scheduler,
            if index % 3 == 0 {
                0.0
            } else {
                (index % 5) as f64 * 0.25
            },
            10 + ((index * 11) % 17) as u16,
            kind,
        )?;
    }
    for index in 0..BULK_EVENTS {
        schedule_kind(
            &mut scheduler,
            ((index * 37) % 251) as f64 / 4.0,
            10 + ((index * 11 + 5) % 17) as u16,
            KINDS[(index * 7 + 3) % KINDS.len()],
        )?;
    }

    let mut digest_material = Vec::with_capacity((initial_count * 3) * 26);
    let mut prefix = JsonValue::Array(Vec::with_capacity(PREFIX_EVENTS));
    let mut popped = 0usize;
    while let Some(event) = scheduler.pop_next() {
        append_event_signature(&mut digest_material, &event);
        if popped < PREFIX_EVENTS {
            if let JsonValue::Array(values) = &mut prefix {
                values.push(event_json(&event));
            }
        }
        if event.sequence < initial_count as u64 {
            for branch in 0..2usize {
                let child_kind =
                    KINDS[((event.sequence as usize * 5) + branch * 7 + 3) % KINDS.len()];
                let offset = if branch == 0 && event.sequence % 5 == 0 {
                    0.0
                } else {
                    (branch + 1) as f64 * 0.125
                };
                let child_priority = 10
                    + ((event.priority as usize + branch * 3 + event.sequence as usize) % 17)
                        as u16;
                schedule_kind(
                    &mut scheduler,
                    event.time + offset,
                    child_priority,
                    child_kind,
                )?;
            }
        }
        popped += 1;
    }

    let mut result = JsonValue::object();
    result.insert(
        "schema",
        JsonValue::string("pineland-scheduler-certification-v1"),
    );
    result.insert("initial_events", JsonValue::integer(initial_count as u64));
    result.insert(
        "scheduled_events",
        JsonValue::integer((initial_count * 3) as u64),
    );
    result.insert("popped_events", JsonValue::integer(popped as u64));
    result.insert("next_sequence", JsonValue::integer(scheduler.next_sequence));
    result.insert("processed", JsonValue::integer(scheduler.processed));
    result.insert("pending", JsonValue::integer(scheduler.len() as u64));
    result.insert(
        "ordering_key",
        JsonValue::string("(time, priority, sequence)"),
    );
    result.insert(
        "pop_digest",
        JsonValue::string(sha256::digest_hex(&digest_material)),
    );
    result.insert("prefix", prefix);
    println!("{}", result.to_pretty());
    Ok(())
}

fn schedule_kind(
    scheduler: &mut Scheduler,
    time: f64,
    priority: u16,
    kind: &str,
) -> Result<(), String> {
    scheduler
        .schedule(time, priority, payload_for_kind(kind))
        .map(|_| ())
        .map_err(|error| error.to_string())
}

fn payload_for_kind(kind: &str) -> EventPayload {
    match kind {
        "patrol" => EventPayload::Patrol {
            patrol: 0u32.into(),
        },
        "contact_scan" => EventPayload::ContactScan,
        "command" => EventPayload::Command,
        "force_movement" => EventPayload::ForceMovement,
        "logistics" => EventPayload::Logistics,
        "information" => EventPayload::Information,
        "beliefs" => EventPayload::Beliefs,
        "physical_refresh" => EventPayload::PhysicalRefresh,
        "social_influence" => EventPayload::SocialInfluence,
        "mobility" => EventPayload::Mobility,
        "recruitment" => EventPayload::Recruitment,
        "organization_ecology" => EventPayload::OrganizationEcology,
        "governance" => EventPayload::Governance,
        "economy" => EventPayload::Economy,
        "political_order" => EventPayload::PoliticalOrder,
        "foreign_affairs" => EventPayload::ForeignAffairs,
        "peace_process" => EventPayload::PeaceProcess,
        "recording_noise" => EventPayload::RecordingNoise,
        "checkpoint" => EventPayload::Checkpoint,
        "organized_action" => EventPayload::OrganizedAction {
            organization: 0u32.into(),
            locality: 0u32.into(),
        },
        "contact" => EventPayload::Contact {
            first: 0u32.into(),
            second: 1u32.into(),
            locality: 0u32.into(),
            microzone: 0u32.into(),
        },
        "custom" => EventPayload::Custom { code: 99, value: 0 },
        _ => unreachable!("unknown scheduler certification event kind {kind}"),
    }
}

fn append_event_signature(buffer: &mut Vec<u8>, event: &ScheduledEvent) {
    buffer.extend_from_slice(&event.time.to_bits().to_le_bytes());
    buffer.extend_from_slice(&event.priority.to_le_bytes());
    buffer.extend_from_slice(&event.sequence.to_le_bytes());
    buffer.extend_from_slice(&event.payload.code().to_le_bytes());
}

fn event_json(event: &ScheduledEvent) -> JsonValue {
    let mut value = JsonValue::object();
    value.insert("time_bits", JsonValue::integer(event.time.to_bits()));
    value.insert("priority", JsonValue::integer(event.priority as u64));
    value.insert("sequence", JsonValue::integer(event.sequence));
    value.insert("kind", JsonValue::string(event.payload.kind()));
    value.insert("code", JsonValue::integer(event.payload.code() as u64));
    value
}
