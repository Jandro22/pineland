//! Columnar-output seam.
//!
//! Checkpoints use the dense binary format.  The dependency-free writer emits
//! deterministic JSONL row groups.  Hosts that need native columnar storage
//! can enable the `parquet` feature; that writer stores one canonical UTF-8
//! JSON row per Parquet record, preserving the exact row values without
//! coupling the runtime to a dynamic Arrow schema.
use pineland_core::json::JsonValue;
use std::io;
use std::path::Path;

pub fn write_row_group(path: impl AsRef<Path>, rows: &[JsonValue]) -> io::Result<()> {
    super::write_jsonl(path, rows)
}

#[cfg(feature = "parquet")]
pub fn write_parquet_row_group(path: impl AsRef<Path>, rows: &[JsonValue]) -> io::Result<()> {
    use parquet::data_type::{ByteArray, ByteArrayType};
    use parquet::file::writer::SerializedFileWriter;
    use parquet::schema::parser::parse_message_type;
    use std::fs::{self, File};
    use std::sync::Arc;
    use std::time::{SystemTime, UNIX_EPOCH};

    let path = path.as_ref();
    if let Some(parent) = path.parent() {
        fs::create_dir_all(parent)?;
    }
    let nonce = SystemTime::now()
        .duration_since(UNIX_EPOCH)
        .unwrap_or_default()
        .as_nanos();
    let temp = path.with_extension(format!("tmp-{nonce}.parquet"));
    let file = File::create(&temp)?;
    let sync_file = file.try_clone()?;
    let schema = Arc::new(
        parse_message_type("message pineland_rows { REQUIRED BINARY json (UTF8); }")
            .map_err(parquet_to_io)?,
    );
    let mut writer =
        SerializedFileWriter::new(file, schema, Default::default()).map_err(parquet_to_io)?;
    let mut row_group = writer.next_row_group().map_err(parquet_to_io)?;
    let values = rows
        .iter()
        .map(|row| ByteArray::from(row.to_compact().into_bytes()))
        .collect::<Vec<_>>();
    let mut column = row_group
        .next_column()
        .map_err(parquet_to_io)?
        .ok_or_else(|| io::Error::other("Parquet schema produced no columns"))?;
    column
        .typed::<ByteArrayType>()
        .write_batch(&values, None, None)
        .map_err(parquet_to_io)?;
    column.close().map_err(parquet_to_io)?;
    row_group.close().map_err(parquet_to_io)?;
    writer.close().map_err(parquet_to_io)?;
    sync_file.sync_all()?;
    super::replace_file(&temp, path)
}

#[cfg(feature = "parquet")]
fn parquet_to_io(error: parquet::errors::ParquetError) -> io::Error {
    io::Error::other(error.to_string())
}

#[cfg(all(test, feature = "parquet"))]
mod tests {
    use super::write_parquet_row_group;
    use pineland_core::json::JsonValue;
    use std::fs;
    use std::time::{SystemTime, UNIX_EPOCH};

    #[test]
    fn writes_a_real_parquet_row_group() {
        let nonce = SystemTime::now()
            .duration_since(UNIX_EPOCH)
            .unwrap_or_default()
            .as_nanos();
        let path = std::env::temp_dir().join(format!(
            "pineland-native-parquet-{}-{nonce}.parquet",
            std::process::id()
        ));
        let rows = [JsonValue::string(r#"{"time":1,"kind":"activity"}"#)];
        write_parquet_row_group(&path, &rows).unwrap();
        let bytes = fs::read(&path).unwrap();
        assert!(bytes.len() > 8);
        assert_eq!(&bytes[..4], b"PAR1");
        assert_eq!(&bytes[bytes.len() - 4..], b"PAR1");
        fs::remove_file(path).unwrap();
    }
}
