#![cfg_attr(not(debug_assertions), windows_subsystem = "windows")]

use std::path::PathBuf;

mod gather;
mod hasher;

use std::time::SystemTime;

#[derive(serde::Serialize, Clone)]
struct FileEntry {
    path: PathBuf,
    modified: SystemTime,
}

#[derive(serde::Serialize, Clone)]
struct DuplicateGroup {
    files: Vec<FileEntry>,
    size_bytes: u64,
}

/// Parses a size string (e.g., "10M", "1G") into a u64 number of bytes.
fn parse_size(size_str: &str) -> Result<u64, String> {
    let lower = size_str.to_lowercase();
    let (num_str, suffix) = lower.trim().split_at(
        lower
            .trim()
            .find(|c: char| !c.is_digit(10) && c != '.')
            .unwrap_or(lower.trim().len()),
    );

    let num: f64 = num_str
        .parse()
        .map_err(|_| format!("Invalid size number: {}", num_str))?;

    let suffix = suffix.trim();

    let multiplier = match suffix {
        "" | "b" => 1.0,
        "k" | "kb" => 1024.0,
        "m" | "mb" => 1024.0 * 1024.0,
        "g" | "gb" => 1024.0 * 1024.0 * 1024.0,
        "t" | "tb" => 1024.0 * 1024.0 * 1024.0 * 1024.0,
        _ => return Err(format!("Invalid size suffix: {}", suffix)),
    };

    Ok((num * multiplier) as u64)
}

#[tauri::command]
fn delete_files(paths: Vec<String>) -> Result<(), String> {
    let mut errors = Vec::new();
    for path in paths {
        if let Err(e) = std::fs::remove_file(&path) {
            errors.push(format!("Failed to delete {}: {}", path, e));
        }
    }

    if errors.is_empty() {
        Ok(())
    } else {
        Err(errors.join("\n"))
    }
}

#[tauri::command]
fn scan_directory(path: String, min_size_str: String) -> Result<Vec<DuplicateGroup>, String> {
    let path = PathBuf::from(path);
    if !path.is_dir() {
        return Err("Provided path is not a directory.".to_string());
    }

    let min_size = parse_size(&min_size_str).map_err(|e| e.to_string())?;

    let size_groups = gather::find_files_by_size(&path, min_size);
    let partial_hash_groups = hasher::group_by_partial_hash(size_groups);
    let duplicate_groups = hasher::group_by_full_hash(partial_hash_groups);

    let result = duplicate_groups
        .into_iter()
        .map(|group| {
            let size_bytes = group.first().and_then(|p| p.metadata().ok()).map_or(0, |m| m.len());
            let file_entries: Vec<FileEntry> = group.into_iter().map(|path| {
                let metadata = path.metadata().ok();
                let modified = metadata.and_then(|m| m.modified().ok()).unwrap_or(SystemTime::UNIX_EPOCH);
                FileEntry { path, modified }
            }).collect();

            DuplicateGroup { files: file_entries, size_bytes }
        })
        .collect();

    Ok(result)
}

fn main() {
    tauri::Builder::default()
        .invoke_handler(tauri::generate_handler![scan_directory, delete_files])
        .run(tauri::generate_context!())
        .expect("error while running tauri application");
}
