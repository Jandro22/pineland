//! Deterministic asynchronous event scheduler.

use crate::ids::{FormationId, LocalityId, MicrozoneId, OrganizationId, PatrolId};
use std::cmp::Ordering;
use std::collections::BinaryHeap;
use std::fmt;

#[derive(Clone, Debug, PartialEq)]
pub enum EventPayload {
    Patrol {
        patrol: PatrolId,
    },
    ContactScan,
    Command,
    ForceMovement,
    Logistics,
    Information,
    Beliefs,
    PhysicalRefresh,
    SocialInfluence,
    Mobility,
    Recruitment,
    OrganizationEcology,
    Governance,
    /// Post-parity endogenous government capacity production: security-force
    /// recruitment/training, administrative rebuilding, and police/intelligence
    /// penetration of clandestine organizations.
    StateRegeneration,
    Economy,
    PoliticalOrder,
    ForeignAffairs,
    PeaceProcess,
    RecordingNoise,
    Checkpoint,
    OrganizedAction {
        organization: OrganizationId,
        locality: LocalityId,
    },
    Contact {
        first: FormationId,
        second: FormationId,
        locality: LocalityId,
        microzone: MicrozoneId,
    },
    Custom {
        code: u16,
        value: u64,
    },
}

impl EventPayload {
    pub fn kind(&self) -> &'static str {
        match self {
            Self::Patrol { .. } => "patrol",
            Self::ContactScan => "contact_scan",
            Self::Command => "command",
            Self::ForceMovement => "force_movement",
            Self::Logistics => "logistics",
            Self::Information => "information",
            Self::Beliefs => "beliefs",
            Self::PhysicalRefresh => "physical_refresh",
            Self::SocialInfluence => "social_influence",
            Self::Mobility => "mobility",
            Self::Recruitment => "recruitment",
            Self::OrganizationEcology => "organization_ecology",
            Self::Governance => "governance",
            Self::StateRegeneration => "state_regeneration",
            Self::Economy => "economy",
            Self::PoliticalOrder => "political_order",
            Self::ForeignAffairs => "foreign_affairs",
            Self::PeaceProcess => "peace_process",
            Self::RecordingNoise => "recording_noise",
            Self::Checkpoint => "checkpoint",
            Self::OrganizedAction { .. } => "organized_action",
            Self::Contact { .. } => "contact",
            Self::Custom { .. } => "custom",
        }
    }

    pub fn code(&self) -> u16 {
        match self {
            Self::Patrol { .. } => 1,
            Self::ContactScan => 2,
            Self::Command => 3,
            Self::ForceMovement => 4,
            Self::Logistics => 5,
            Self::Information => 6,
            Self::Beliefs => 7,
            Self::PhysicalRefresh => 8,
            Self::SocialInfluence => 9,
            Self::Mobility => 10,
            Self::Recruitment => 11,
            Self::OrganizationEcology => 12,
            Self::Governance => 13,
            Self::Economy => 14,
            Self::PoliticalOrder => 15,
            Self::ForeignAffairs => 16,
            Self::PeaceProcess => 17,
            Self::RecordingNoise => 18,
            Self::Checkpoint => 19,
            Self::OrganizedAction { .. } => 20,
            Self::Contact { .. } => 21,
            Self::StateRegeneration => 22,
            Self::Custom { code, .. } => *code,
        }
    }
}

#[derive(Clone, Debug, PartialEq)]
pub struct ScheduledEvent {
    pub time: f64,
    pub priority: u16,
    pub sequence: u64,
    /// Python's recurring payload carries the elapsed interval separately
    /// from the event timestamp.  Keeping it explicit avoids inferring a
    /// zero-length t=0 boundary from time alone and preserves restart
    /// semantics across burn-in and checkpoints.
    pub elapsed_days: f64,
    pub payload: EventPayload,
}

#[derive(Clone, Debug, PartialEq)]
pub enum SchedulerError {
    NonFiniteTime(f64),
    InvalidElapsedDays(f64),
    SequenceOverflow,
}

impl fmt::Display for SchedulerError {
    fn fmt(&self, formatter: &mut fmt::Formatter<'_>) -> fmt::Result {
        match self {
            Self::NonFiniteTime(time) => write!(formatter, "event time must be finite, got {time}"),
            Self::InvalidElapsedDays(days) => {
                write!(
                    formatter,
                    "event elapsed days must be finite and non-negative, got {days}"
                )
            }
            Self::SequenceOverflow => formatter.write_str("event sequence overflow"),
        }
    }
}

impl std::error::Error for SchedulerError {}

#[derive(Clone, Debug)]
struct HeapEvent(ScheduledEvent);

impl PartialEq for HeapEvent {
    fn eq(&self, other: &Self) -> bool {
        self.0.time.to_bits() == other.0.time.to_bits()
            && self.0.priority == other.0.priority
            && self.0.sequence == other.0.sequence
    }
}

impl Eq for HeapEvent {}

impl Ord for HeapEvent {
    fn cmp(&self, other: &Self) -> Ordering {
        // BinaryHeap is a max-heap.  Reverse each scientific ordering key so
        // the smallest (time, priority, sequence) is popped first.
        other
            .0
            .time
            .total_cmp(&self.0.time)
            .then_with(|| other.0.priority.cmp(&self.0.priority))
            .then_with(|| other.0.sequence.cmp(&self.0.sequence))
    }
}

impl PartialOrd for HeapEvent {
    fn partial_cmp(&self, other: &Self) -> Option<Ordering> {
        Some(self.cmp(other))
    }
}

#[derive(Clone, Debug, Default)]
pub struct Scheduler {
    heap: BinaryHeap<HeapEvent>,
    pub next_sequence: u64,
    pub processed: u64,
}

impl PartialEq for Scheduler {
    fn eq(&self, other: &Self) -> bool {
        self.next_sequence == other.next_sequence
            && self.processed == other.processed
            && self.events_sorted() == other.events_sorted()
    }
}

impl Scheduler {
    pub fn new() -> Self {
        Self {
            heap: BinaryHeap::new(),
            next_sequence: 0,
            processed: 0,
        }
    }

    pub fn schedule(
        &mut self,
        time: f64,
        priority: u16,
        payload: EventPayload,
    ) -> Result<u64, SchedulerError> {
        self.schedule_with_elapsed(time, priority, 0.0, payload)
    }

    pub fn schedule_with_elapsed(
        &mut self,
        time: f64,
        priority: u16,
        elapsed_days: f64,
        payload: EventPayload,
    ) -> Result<u64, SchedulerError> {
        if !time.is_finite() {
            return Err(SchedulerError::NonFiniteTime(time));
        }
        if !elapsed_days.is_finite() || elapsed_days < 0.0 {
            return Err(SchedulerError::InvalidElapsedDays(elapsed_days));
        }
        let sequence = self.next_sequence;
        self.next_sequence = self
            .next_sequence
            .checked_add(1)
            .ok_or(SchedulerError::SequenceOverflow)?;
        self.heap.push(HeapEvent(ScheduledEvent {
            time,
            priority,
            sequence,
            elapsed_days,
            payload,
        }));
        Ok(sequence)
    }

    pub fn push_with_sequence(&mut self, event: ScheduledEvent) -> Result<(), SchedulerError> {
        if !event.time.is_finite() {
            return Err(SchedulerError::NonFiniteTime(event.time));
        }
        self.next_sequence = self.next_sequence.max(event.sequence.saturating_add(1));
        self.heap.push(HeapEvent(event));
        Ok(())
    }

    pub fn pop_next(&mut self) -> Option<ScheduledEvent> {
        let event = self.heap.pop().map(|item| item.0);
        if event.is_some() {
            self.processed = self.processed.saturating_add(1);
        }
        event
    }

    pub fn peek(&self) -> Option<&ScheduledEvent> {
        self.heap.peek().map(|item| &item.0)
    }

    pub fn len(&self) -> usize {
        self.heap.len()
    }

    pub fn is_empty(&self) -> bool {
        self.heap.is_empty()
    }

    pub fn clear(&mut self) {
        self.heap.clear();
    }

    /// Shift all pending events by a fixed calendar offset while preserving
    /// their explicit sequence numbers.  Burn-in uses this to reuse the
    /// initialized event calendar at negative analytical time without
    /// reconstructing payloads through a dynamic representation.
    pub fn shift_times(&mut self, offset: f64) -> Result<(), SchedulerError> {
        if !offset.is_finite() {
            return Err(SchedulerError::NonFiniteTime(offset));
        }
        let mut events = self.events_sorted();
        self.heap.clear();
        for event in &mut events {
            event.time += offset;
            if !event.time.is_finite() {
                return Err(SchedulerError::NonFiniteTime(event.time));
            }
        }
        for event in events {
            self.push_with_sequence(event)?;
        }
        Ok(())
    }

    pub fn drain_until(&mut self, until: f64) -> Result<Vec<ScheduledEvent>, SchedulerError> {
        if !until.is_finite() {
            return Err(SchedulerError::NonFiniteTime(until));
        }
        let mut events = Vec::new();
        while self.peek().is_some_and(|event| event.time <= until) {
            if let Some(event) = self.pop_next() {
                events.push(event);
            }
        }
        Ok(events)
    }

    pub fn events_sorted(&self) -> Vec<ScheduledEvent> {
        let mut events: Vec<ScheduledEvent> = self.heap.iter().map(|item| item.0.clone()).collect();
        events.sort_by(|a, b| {
            a.time
                .total_cmp(&b.time)
                .then_with(|| a.priority.cmp(&b.priority))
                .then_with(|| a.sequence.cmp(&b.sequence))
        });
        events
    }
}

#[cfg(test)]
mod tests {
    use super::{EventPayload, Scheduler};

    #[test]
    fn orders_by_time_priority_and_insertion() {
        let mut scheduler = Scheduler::new();
        scheduler.schedule(2.0, 0, EventPayload::Economy).unwrap();
        scheduler.schedule(1.0, 20, EventPayload::Command).unwrap();
        scheduler
            .schedule(
                1.0,
                10,
                EventPayload::Patrol {
                    patrol: 0u32.into(),
                },
            )
            .unwrap();
        assert_eq!(scheduler.pop_next().unwrap().payload.kind(), "patrol");
        assert_eq!(scheduler.pop_next().unwrap().payload.kind(), "command");
        assert_eq!(scheduler.pop_next().unwrap().payload.kind(), "economy");
    }

    #[test]
    fn rejects_nan() {
        let mut scheduler = Scheduler::new();
        assert!(scheduler
            .schedule(f64::NAN, 0, EventPayload::Economy)
            .is_err());
    }
}
