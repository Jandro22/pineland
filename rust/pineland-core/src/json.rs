//! A small deterministic JSON implementation.
//!
//! Pineland's runtime intentionally keeps the simulation core dependency-free.
//! This parser is not intended to replace a general JSON ecosystem; it is a
//! strict RFC 8259 reader/writer with the object/array accessors needed by the
//! native CLI and checkpoint/provenance manifests.

use std::collections::BTreeMap;
use std::fmt;

#[derive(Clone, Debug, PartialEq)]
pub enum JsonValue {
    Null,
    Bool(bool),
    Number(f64),
    /// An integer kept in its exact form when it was read from JSON.
    ///
    /// Configuration seeds, lineage counters, and checkpoint boundaries are
    /// allowed to use the full unsigned 64-bit range.  Storing an integer
    /// token as `f64` would silently round values above 2^53 before the
    /// caller could validate or hash the configuration.
    Integer(i128),
    String(String),
    Array(Vec<JsonValue>),
    Object(BTreeMap<String, JsonValue>),
}

impl JsonValue {
    pub fn object() -> Self {
        Self::Object(BTreeMap::new())
    }

    pub fn array() -> Self {
        Self::Array(Vec::new())
    }

    pub fn string(value: impl Into<String>) -> Self {
        Self::String(value.into())
    }

    pub fn number(value: impl Into<f64>) -> Self {
        Self::Number(value.into())
    }

    pub fn integer(value: impl Into<i128>) -> Self {
        Self::Integer(value.into())
    }

    pub fn get(&self, key: &str) -> Option<&Self> {
        match self {
            Self::Object(values) => values.get(key),
            _ => None,
        }
    }

    pub fn get_mut(&mut self, key: &str) -> Option<&mut Self> {
        match self {
            Self::Object(values) => values.get_mut(key),
            _ => None,
        }
    }

    pub fn insert(&mut self, key: impl Into<String>, value: Self) {
        if let Self::Object(values) = self {
            values.insert(key.into(), value);
        }
    }

    pub fn push(&mut self, value: Self) {
        if let Self::Array(values) = self {
            values.push(value);
        }
    }

    pub fn as_object(&self) -> Option<&BTreeMap<String, Self>> {
        match self {
            Self::Object(values) => Some(values),
            _ => None,
        }
    }

    pub fn as_array(&self) -> Option<&[Self]> {
        match self {
            Self::Array(values) => Some(values),
            _ => None,
        }
    }

    pub fn as_str(&self) -> Option<&str> {
        match self {
            Self::String(value) => Some(value),
            _ => None,
        }
    }

    pub fn as_f64(&self) -> Option<f64> {
        match self {
            Self::Number(value) if value.is_finite() => Some(*value),
            Self::Integer(value) => {
                let converted = *value as f64;
                converted.is_finite().then_some(converted)
            }
            _ => None,
        }
    }

    pub fn as_u64(&self) -> Option<u64> {
        match self {
            Self::Integer(value) => u64::try_from(*value).ok(),
            Self::Number(value) if value.is_finite() && *value >= 0.0 && value.fract() == 0.0 => {
                // The exact integer representation is preferred above.  For
                // programmatically-created f64 values, retain the historic
                // accessor behavior while rejecting rounded overflow.
                (*value < 2.0f64.powi(64)).then_some(*value as u64)
            }
            _ => None,
        }
    }

    pub fn as_usize(&self) -> Option<usize> {
        self.as_u64().and_then(|value| usize::try_from(value).ok())
    }

    pub fn as_bool(&self) -> Option<bool> {
        match self {
            Self::Bool(value) => Some(*value),
            _ => None,
        }
    }

    pub fn to_compact(&self) -> String {
        let mut output = String::new();
        write_json(self, &mut output, false, 0);
        output
    }

    pub fn to_pretty(&self) -> String {
        let mut output = String::new();
        write_json(self, &mut output, true, 0);
        output.push('\n');
        output
    }
}

impl fmt::Display for JsonValue {
    fn fmt(&self, formatter: &mut fmt::Formatter<'_>) -> fmt::Result {
        formatter.write_str(&self.to_compact())
    }
}

#[derive(Clone, Debug, PartialEq, Eq)]
pub struct JsonError {
    pub position: usize,
    pub message: String,
}

impl JsonError {
    fn new(position: usize, message: impl Into<String>) -> Self {
        Self {
            position,
            message: message.into(),
        }
    }
}

impl fmt::Display for JsonError {
    fn fmt(&self, formatter: &mut fmt::Formatter<'_>) -> fmt::Result {
        write!(
            formatter,
            "JSON error at byte {}: {}",
            self.position, self.message
        )
    }
}

impl std::error::Error for JsonError {}

pub fn parse(input: &str) -> Result<JsonValue, JsonError> {
    let mut parser = Parser {
        input: input.as_bytes(),
        position: 0,
    };
    let value = parser.value()?;
    parser.whitespace();
    if parser.position != parser.input.len() {
        return Err(JsonError::new(parser.position, "trailing characters"));
    }
    Ok(value)
}

struct Parser<'a> {
    input: &'a [u8],
    position: usize,
}

impl<'a> Parser<'a> {
    fn peek(&self) -> Option<u8> {
        self.input.get(self.position).copied()
    }

    fn take(&mut self) -> Option<u8> {
        let value = self.peek()?;
        self.position += 1;
        Some(value)
    }

    fn whitespace(&mut self) {
        while matches!(self.peek(), Some(b' ' | b'\n' | b'\r' | b'\t')) {
            self.position += 1;
        }
    }

    fn value(&mut self) -> Result<JsonValue, JsonError> {
        self.whitespace();
        match self.peek() {
            Some(b'n') => self.literal(b"null", JsonValue::Null),
            Some(b't') => self.literal(b"true", JsonValue::Bool(true)),
            Some(b'f') => self.literal(b"false", JsonValue::Bool(false)),
            Some(b'"') => Ok(JsonValue::String(self.string()?)),
            Some(b'[') => self.array(),
            Some(b'{') => self.object(),
            Some(b'-' | b'0'..=b'9') => self.number(),
            Some(_) => Err(JsonError::new(self.position, "unexpected value")),
            None => Err(JsonError::new(self.position, "unexpected end of input")),
        }
    }

    fn literal(&mut self, expected: &[u8], value: JsonValue) -> Result<JsonValue, JsonError> {
        let start = self.position;
        for byte in expected {
            if self.take() != Some(*byte) {
                return Err(JsonError::new(start, "invalid literal"));
            }
        }
        Ok(value)
    }

    fn number(&mut self) -> Result<JsonValue, JsonError> {
        let start = self.position;
        let mut is_integer = true;
        if self.peek() == Some(b'-') {
            self.position += 1;
        }
        match self.peek() {
            Some(b'0') => self.position += 1,
            Some(b'1'..=b'9') => {
                while matches!(self.peek(), Some(b'0'..=b'9')) {
                    self.position += 1;
                }
            }
            _ => return Err(JsonError::new(start, "invalid number")),
        }
        if self.peek() == Some(b'.') {
            is_integer = false;
            self.position += 1;
            let fraction_start = self.position;
            while matches!(self.peek(), Some(b'0'..=b'9')) {
                self.position += 1;
            }
            if self.position == fraction_start {
                return Err(JsonError::new(
                    start,
                    "number needs digits after decimal point",
                ));
            }
        }
        if matches!(self.peek(), Some(b'e' | b'E')) {
            is_integer = false;
            self.position += 1;
            if matches!(self.peek(), Some(b'+' | b'-')) {
                self.position += 1;
            }
            let exponent_start = self.position;
            while matches!(self.peek(), Some(b'0'..=b'9')) {
                self.position += 1;
            }
            if self.position == exponent_start {
                return Err(JsonError::new(start, "number needs exponent digits"));
            }
        }
        let text = std::str::from_utf8(&self.input[start..self.position])
            .map_err(|_| JsonError::new(start, "invalid number bytes"))?;
        if is_integer {
            let value = text
                .parse::<i128>()
                .map_err(|_| JsonError::new(start, "integer is outside supported range"))?;
            return Ok(JsonValue::Integer(value));
        }
        let value = text
            .parse::<f64>()
            .map_err(|_| JsonError::new(start, "number is outside supported range"))?;
        if !value.is_finite() {
            return Err(JsonError::new(start, "JSON numbers must be finite"));
        }
        Ok(JsonValue::Number(value))
    }

    fn string(&mut self) -> Result<String, JsonError> {
        let start = self.position;
        if self.take() != Some(b'"') {
            return Err(JsonError::new(start, "expected string"));
        }
        let mut result = String::new();
        loop {
            let byte = self
                .take()
                .ok_or_else(|| JsonError::new(self.position, "unterminated string"))?;
            match byte {
                b'"' => return Ok(result),
                b'\\' => {
                    let escape_position = self.position - 1;
                    let escaped = self
                        .take()
                        .ok_or_else(|| JsonError::new(self.position, "unterminated escape"))?;
                    match escaped {
                        b'"' => result.push('"'),
                        b'\\' => result.push('\\'),
                        b'/' => result.push('/'),
                        b'b' => result.push('\u{0008}'),
                        b'f' => result.push('\u{000c}'),
                        b'n' => result.push('\n'),
                        b'r' => result.push('\r'),
                        b't' => result.push('\t'),
                        b'u' => {
                            let code = self.hex_quad()?;
                            if (0xD800..=0xDBFF).contains(&code) {
                                let save = self.position;
                                if self.take() == Some(b'\\') && self.take() == Some(b'u') {
                                    let low = self.hex_quad()?;
                                    if (0xDC00..=0xDFFF).contains(&low) {
                                        let combined = 0x1_0000
                                            + (((code - 0xD800) as u32) << 10)
                                            + (low - 0xDC00) as u32;
                                        if let Some(character) = char::from_u32(combined) {
                                            result.push(character);
                                        }
                                    } else {
                                        return Err(JsonError::new(
                                            escape_position,
                                            "invalid low surrogate",
                                        ));
                                    }
                                } else {
                                    self.position = save;
                                    return Err(JsonError::new(
                                        escape_position,
                                        "high surrogate must be followed by a low surrogate",
                                    ));
                                }
                            } else if (0xDC00..=0xDFFF).contains(&code) {
                                return Err(JsonError::new(
                                    escape_position,
                                    "unexpected low surrogate",
                                ));
                            } else if let Some(character) = char::from_u32(code as u32) {
                                result.push(character);
                            } else {
                                return Err(JsonError::new(
                                    escape_position,
                                    "invalid unicode escape",
                                ));
                            }
                        }
                        _ => return Err(JsonError::new(escape_position, "invalid escape")),
                    }
                }
                0x00..=0x1F => {
                    return Err(JsonError::new(
                        self.position - 1,
                        "control character in string",
                    ))
                }
                byte => {
                    let begin = self.position - 1;
                    let width = utf8_width(byte)
                        .ok_or_else(|| JsonError::new(begin, "invalid UTF-8 in string"))?;
                    for _ in 1..width {
                        if !matches!(self.take(), Some(0x80..=0xBF)) {
                            return Err(JsonError::new(begin, "invalid UTF-8 continuation"));
                        }
                    }
                    let text = std::str::from_utf8(&self.input[begin..self.position])
                        .map_err(|_| JsonError::new(begin, "invalid UTF-8 in string"))?;
                    result.push_str(text);
                }
            }
        }
    }

    fn hex_quad(&mut self) -> Result<u16, JsonError> {
        let start = self.position;
        let mut value = 0u16;
        for _ in 0..4 {
            let byte = self
                .take()
                .ok_or_else(|| JsonError::new(self.position, "short unicode escape"))?;
            let digit = match byte {
                b'0'..=b'9' => byte - b'0',
                b'a'..=b'f' => byte - b'a' + 10,
                b'A'..=b'F' => byte - b'A' + 10,
                _ => return Err(JsonError::new(start, "invalid unicode escape")),
            } as u16;
            value = (value << 4) | digit;
        }
        Ok(value)
    }

    fn array(&mut self) -> Result<JsonValue, JsonError> {
        self.position += 1;
        let mut values = Vec::new();
        self.whitespace();
        if self.peek() == Some(b']') {
            self.position += 1;
            return Ok(JsonValue::Array(values));
        }
        loop {
            values.push(self.value()?);
            self.whitespace();
            match self.take() {
                Some(b',') => {
                    self.whitespace();
                    if self.peek() == Some(b']') {
                        return Err(JsonError::new(self.position, "trailing comma in array"));
                    }
                }
                Some(b']') => return Ok(JsonValue::Array(values)),
                _ => {
                    return Err(JsonError::new(
                        self.position,
                        "expected comma or closing array",
                    ))
                }
            }
        }
    }

    fn object(&mut self) -> Result<JsonValue, JsonError> {
        self.position += 1;
        let mut values = BTreeMap::new();
        self.whitespace();
        if self.peek() == Some(b'}') {
            self.position += 1;
            return Ok(JsonValue::Object(values));
        }
        loop {
            self.whitespace();
            if self.peek() != Some(b'"') {
                return Err(JsonError::new(self.position, "object keys must be strings"));
            }
            let key = self.string()?;
            self.whitespace();
            if self.take() != Some(b':') {
                return Err(JsonError::new(
                    self.position,
                    "expected colon after object key",
                ));
            }
            let value = self.value()?;
            if values.insert(key, value).is_some() {
                return Err(JsonError::new(self.position, "duplicate object key"));
            }
            self.whitespace();
            match self.take() {
                Some(b',') => {
                    self.whitespace();
                    if self.peek() == Some(b'}') {
                        return Err(JsonError::new(self.position, "trailing comma in object"));
                    }
                }
                Some(b'}') => return Ok(JsonValue::Object(values)),
                _ => {
                    return Err(JsonError::new(
                        self.position,
                        "expected comma or closing object",
                    ))
                }
            }
        }
    }
}

fn utf8_width(byte: u8) -> Option<usize> {
    match byte {
        0x00..=0x7F => Some(1),
        0xC2..=0xDF => Some(2),
        0xE0..=0xEF => Some(3),
        0xF0..=0xF4 => Some(4),
        _ => None,
    }
}

fn write_json(value: &JsonValue, output: &mut String, pretty: bool, depth: usize) {
    match value {
        JsonValue::Null => output.push_str("null"),
        JsonValue::Bool(value) => output.push_str(if *value { "true" } else { "false" }),
        JsonValue::Number(value) => {
            if value.is_finite() {
                if *value == 0.0 {
                    output.push('0');
                } else {
                    output.push_str(&value.to_string());
                }
            } else {
                output.push_str("null");
            }
        }
        JsonValue::Integer(value) => output.push_str(&value.to_string()),
        JsonValue::String(value) => write_string(value, output),
        JsonValue::Array(values) => {
            output.push('[');
            for (index, value) in values.iter().enumerate() {
                if index > 0 {
                    output.push(',');
                }
                if pretty {
                    output.push('\n');
                    indent(output, depth + 1);
                }
                write_json(value, output, pretty, depth + 1);
            }
            if pretty && !values.is_empty() {
                output.push('\n');
                indent(output, depth);
            }
            output.push(']');
        }
        JsonValue::Object(values) => {
            output.push('{');
            for (index, (key, value)) in values.iter().enumerate() {
                if index > 0 {
                    output.push(',');
                }
                if pretty {
                    output.push('\n');
                    indent(output, depth + 1);
                }
                write_string(key, output);
                output.push(':');
                if pretty {
                    output.push(' ');
                }
                write_json(value, output, pretty, depth + 1);
            }
            if pretty && !values.is_empty() {
                output.push('\n');
                indent(output, depth);
            }
            output.push('}');
        }
    }
}

fn indent(output: &mut String, depth: usize) {
    for _ in 0..depth {
        output.push_str("  ");
    }
}

fn write_string(value: &str, output: &mut String) {
    output.push('"');
    for character in value.chars() {
        match character {
            '"' => output.push_str("\\\""),
            '\\' => output.push_str("\\\\"),
            '\u{0008}' => output.push_str("\\b"),
            '\u{000c}' => output.push_str("\\f"),
            '\n' => output.push_str("\\n"),
            '\r' => output.push_str("\\r"),
            '\t' => output.push_str("\\t"),
            character if character <= '\u{001F}' => {
                output.push_str(&format!("\\u{:04x}", character as u32));
            }
            character => output.push(character),
        }
    }
    output.push('"');
}

#[cfg(test)]
mod tests {
    use super::{parse, JsonValue};

    #[test]
    fn integer_tokens_are_exact_and_decimal_tokens_remain_f64() {
        let value = parse(r#"{"n":18446744073709551615,"x":1.25}"#).unwrap();
        assert_eq!(value.get("n").and_then(JsonValue::as_u64), Some(u64::MAX));
        assert_eq!(value.get("x").and_then(JsonValue::as_f64), Some(1.25));
        assert_eq!(value.to_compact(), r#"{"n":18446744073709551615,"x":1.25}"#);
        assert_eq!(JsonValue::number(2.0f64.powi(64)).as_u64(), None);
    }

    #[test]
    fn duplicate_keys_and_trailing_commas_are_rejected() {
        assert!(parse(r#"{"x":1,"x":2}"#).is_err());
        assert!(parse(r#"[1,]"#).is_err());
        assert!(parse(r#"{"x":1,}"#).is_err());
    }
}
