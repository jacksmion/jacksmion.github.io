use indicatif::{ProgressBar, ProgressStyle};
use rayon::prelude::*;
use std::collections::HashMap;
use std::fs::File;
use std::io::{Read, Seek, SeekFrom};
use std::path::{Path, PathBuf};
use xxhash_rust::xxh3::xxh3_64;

const PARTIAL_HASH_CHUNK_SIZE: u64 = 4096;

/// Computes a hash based on the head and tail of a file.
/// For files smaller than 2 * PARTIAL_HASH_CHUNK_SIZE, it hashes the entire content.
fn calculate_partial_hash(path: &Path) -> std::io::Result<u64> {
    let mut file = File::open(path)?;
    let file_size = file.metadata()?.len();

    if file_size < PARTIAL_HASH_CHUNK_SIZE * 2 {
        let mut contents = Vec::with_capacity(file_size as usize);
        file.read_to_end(&mut contents)?;
        Ok(xxh3_64(&contents))
    } else {
        let mut buffer = vec![0; (PARTIAL_HASH_CHUNK_SIZE * 2) as usize];

        // Read head
        file.read_exact(&mut buffer[0..PARTIAL_HASH_CHUNK_SIZE as usize])?;

        // Seek to tail and read
        file.seek(SeekFrom::End(-(PARTIAL_HASH_CHUNK_SIZE as i64)))?;
        file.read_exact(&mut buffer[PARTIAL_HASH_CHUNK_SIZE as usize..])?;

        Ok(xxh3_64(&buffer))
    }
}

pub fn group_by_partial_hash(
    groups_by_size: HashMap<u64, Vec<PathBuf>>,
) -> Vec<Vec<PathBuf>> {
    println!("Phase 2: Performing partial hash check...");

    let num_groups = groups_by_size.len();
    let pb = ProgressBar::new(num_groups as u64);
    pb.set_style(
        ProgressStyle::default_bar()
            .template("{spinner:.green} [{elapsed_precise}] [{bar:40.cyan/blue}] {pos}/{len} ({eta})")
            .unwrap()
            .progress_chars("#>-"),
    );

    let groups_by_size_vec: Vec<_> = groups_by_size.into_values().collect();

    let potential_duplicates: Vec<Vec<PathBuf>> = groups_by_size_vec
        .into_par_iter()
        .progress_with(pb)
        .flat_map(|files| {
            let mut groups_by_hash: HashMap<u64, Vec<PathBuf>> = HashMap::new();
            for file in files {
                // A file could have been deleted between the initial scan and now.
                // We'll just ignore errors for now.
                if let Ok(hash) = calculate_partial_hash(&file) {
                    groups_by_hash.entry(hash).or_default().push(file);
                }
            }

            // Filter out groups that don't have duplicates after this stage
            groups_by_hash
                .into_values()
                .filter(|group| group.len() > 1)
                .collect::<Vec<Vec<PathBuf>>>()
        })
        .collect();

    potential_duplicates
}

fn calculate_full_hash(path: &Path) -> std::io::Result<blake3::Hash> {
    let mut file = File::open(path)?;
    let mut hasher = blake3::Hasher::new();
    // Hash in chunks to be memory efficient
    std::io::copy(&mut file, &mut hasher)?;
    Ok(hasher.finalize())
}

pub fn group_by_full_hash(
    partial_hash_groups: Vec<Vec<PathBuf>>,
) -> Vec<Vec<PathBuf>> {
    println!("Phase 3: Performing full hash check...");

    let num_groups = partial_hash_groups.len();
    let pb = ProgressBar::new(num_groups as u64);
    pb.set_style(
        ProgressStyle::default_bar()
            .template("{spinner:.green} [{elapsed_precise}] [{bar:40.cyan/blue}] {pos}/{len} ({eta})")
            .unwrap()
            .progress_chars("#>-"),
    );

    let final_duplicates: Vec<Vec<PathBuf>> = partial_hash_groups
        .into_par_iter()
        .progress_with(pb)
        .flat_map(|files| {
            let mut groups_by_full_hash: HashMap<blake3::Hash, Vec<PathBuf>> = HashMap::new();
            for file in files {
                if let Ok(hash) = calculate_full_hash(&file) {
                    groups_by_full_hash.entry(hash).or_default().push(file);
                }
            }

            groups_by_full_hash
                .into_values()
                .filter(|group| group.len() > 1)
                .collect::<Vec<Vec<PathBuf>>>()
        })
        .collect();

    final_duplicates
}
