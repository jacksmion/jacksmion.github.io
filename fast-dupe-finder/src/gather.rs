use indicatif::{ProgressBar, ProgressStyle};
use std::collections::HashMap;
use std::path::{Path, PathBuf};
use walkdir::WalkDir;

pub fn find_files_by_size(root: &Path, min_size: u64) -> HashMap<u64, Vec<PathBuf>> {
    let mut files_by_size: HashMap<u64, Vec<PathBuf>> = HashMap::new();

    println!("Phase 1: Collecting files and grouping by size...");

    // We can't know the total number of files beforehand without walking the directory twice,
    // so we use a spinner style progress bar.
    let pb = ProgressBar::new_spinner();
    pb.set_style(
        ProgressStyle::default_spinner()
            .template("{spinner:.green} [{elapsed_precise}] {msg}")
            .unwrap(),
    );
    pb.set_message("Scanning directories...");

    let walker = WalkDir::new(root).into_iter();
    let mut file_count = 0;

    for entry in walker.filter_map(|e| e.ok()) {
        // Check if it's a file and has metadata
        if let Ok(metadata) = entry.metadata() {
            if metadata.is_file() {
                file_count += 1;
                pb.set_message(format!("Scanned {} files", file_count));

                let size = metadata.len();
                if size >= min_size {
                    files_by_size
                        .entry(size)
                        .or_default()
                        .push(entry.path().to_path_buf());
                }
            }
        }
        pb.tick();
    }

    pb.finish_with_message(format!("Scanned a total of {} files.", file_count));

    // Filter out files with unique sizes, as they cannot be duplicates.
    let duplicate_size_groups = files_by_size
        .into_iter()
        .filter(|(_, files)| files.len() > 1)
        .collect();

    duplicate_size_groups
}
