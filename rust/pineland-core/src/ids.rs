//! Stable numeric identifiers used inside hot execution paths.

use std::fmt;

macro_rules! id_type {
    ($name:ident) => {
        #[derive(Clone, Copy, Debug, Default, PartialEq, Eq, Hash, PartialOrd, Ord)]
        #[repr(transparent)]
        pub struct $name(pub u32);

        impl $name {
            pub const INVALID: Self = Self(u32::MAX);

            pub const fn new(value: u32) -> Self {
                Self(value)
            }

            pub const fn get(self) -> u32 {
                self.0
            }
        }

        impl From<u32> for $name {
            fn from(value: u32) -> Self {
                Self(value)
            }
        }

        impl From<usize> for $name {
            fn from(value: usize) -> Self {
                Self(value as u32)
            }
        }

        impl From<$name> for u32 {
            fn from(value: $name) -> Self {
                value.0
            }
        }

        impl fmt::Display for $name {
            fn fmt(&self, formatter: &mut fmt::Formatter<'_>) -> fmt::Result {
                write!(formatter, "{}", self.0)
            }
        }
    };
}

id_type!(OrganizationId);
id_type!(DistrictId);
id_type!(LocalityId);
id_type!(MicrozoneId);
id_type!(FormationId);
id_type!(PatrolId);
id_type!(SecurityPostId);
id_type!(PersonId);
id_type!(HouseholdId);
id_type!(ObservationId);
id_type!(EventId);
id_type!(BeliefId);
id_type!(BranchId);

#[derive(Clone, Debug, Default, PartialEq, Eq)]
pub struct IdTable {
    values: Vec<String>,
}

impl IdTable {
    pub fn new() -> Self {
        Self::default()
    }

    pub fn with_values(values: impl IntoIterator<Item = impl Into<String>>) -> Self {
        let mut table = Self::new();
        for value in values {
            table.intern(value);
        }
        table
    }

    pub fn intern(&mut self, value: impl Into<String>) -> u32 {
        let value = value.into();
        if let Some(index) = self.values.iter().position(|item| item == &value) {
            return index as u32;
        }
        let index = self.values.len() as u32;
        self.values.push(value);
        index
    }

    pub fn get(&self, id: u32) -> Option<&str> {
        self.values.get(id as usize).map(String::as_str)
    }

    pub fn id(&self, value: &str) -> Option<u32> {
        self.values
            .iter()
            .position(|item| item == value)
            .map(|i| i as u32)
    }

    pub fn len(&self) -> usize {
        self.values.len()
    }

    pub fn is_empty(&self) -> bool {
        self.values.is_empty()
    }

    pub fn values(&self) -> &[String] {
        &self.values
    }
}
