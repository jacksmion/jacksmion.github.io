import argparse
import os
import asyncio # Added
import aiofiles.os as aio_os # Added
import stat # Added
import logging
import threading 
import time

# Set up logger for this module
logger = logging.getLogger(__name__)

# TaskNameFilter removed due to persistent errors with %(taskName)s in the environment.
# Task names are still set via asyncio.create_task(..., name=...) for potential manual logging or debugging.

async def scan_directory(directory_path: str) -> tuple[int, int, int, bool]:
    dir_scan_start_time = time.monotonic()
    logger.info(f"Async scanning directory: {directory_path}")
    
    num_files_at_this_level = 0
    num_folders_at_this_level = 0 # Counts folders directly within this path, to be returned as part of this level's folder finds
    total_size_at_this_level = 0
    
    # Aggregated counts including subdirectories
    aggregated_num_files = 0
    aggregated_num_folders = 0
    aggregated_total_size = 0
    
    error_occurred_current_level = False
    any_error_in_subtasks = False

    child_tasks = []

    try:
        item_names = await aio_os.listdir(directory_path)
        for item_name in item_names:
            item_path = os.path.join(directory_path, item_name)
            try:
                # We need to stat each item to determine if it's a file or directory
                # and also to get its size if it's a file.
                # We also need to handle symlinks appropriately, typically by not following them
                # for directory structure, but potentially following them for size if that's desired.
                # For now, use lstat to not follow symlinks for type checking.
                # stat_result = await aio_os.lstat(item_path) # This was causing AttributeError
                stat_result = await asyncio.to_thread(os.lstat, item_path)
                
                if stat.S_ISREG(stat_result.st_mode): # It's a regular file
                    num_files_at_this_level += 1
                    # For size, we want the size of the file itself.
                    # If stat_result is from lstat on a symlink, st_size is size of the link.
                    # If it's a regular file, st_size is correct.
                    # To get target size for a symlink, one would need to:
                    # 1. Check if S_ISLNK(stat_result.st_mode)
                    # 2. If so, os.readlink() then await aio_os.stat() on the target.
                    # For now, this simplified version takes st_size from lstat.
                    # This is consistent with how many tools count symlink sizes vs target sizes.
                    total_size_at_this_level += stat_result.st_size
                    logger.debug(f"Found file: {item_path}, Size: {stat_result.st_size}")
                elif stat.S_ISDIR(stat_result.st_mode): # It's a directory
                    num_folders_at_this_level += 1
                    logger.debug(f"Found subdirectory: {item_path}. Creating task scan-{item_name}.")
                    child_tasks.append(asyncio.create_task(scan_directory(item_path), name=f"scan-{item_name}"))
                # Not explicitly handling other types like symlinks that are not dirs/files, block devices etc.
                # They will be ignored by this logic.

            except (FileNotFoundError, PermissionError) as item_proc_e:
                logger.warning(f"Could not process item {item_path}: {item_proc_e}")
                error_occurred_current_level = True # Error processing an item at this level

    except (FileNotFoundError, PermissionError) as list_e:
        logger.error(f"Could not list directory {directory_path}: {list_e}")
        error_occurred_current_level = True
        # Return early as we can't proceed with this directory
        dir_scan_end_time = time.monotonic()
        dir_duration = dir_scan_end_time - dir_scan_start_time
        logger.debug(f"Time taken for failed scan of {directory_path}: {dir_duration:.2f} seconds")
        return 0, 0, 0, True # num_files, num_folders, total_size, error_flag

    # Aggregation starts with what was found directly at this level
    aggregated_num_files = num_files_at_this_level
    aggregated_num_folders = num_folders_at_this_level 
    aggregated_total_size = total_size_at_this_level

    if child_tasks:
        logger.debug(f"Waiting for {len(child_tasks)} sub-scans for directory: {directory_path}")
        gathered_results = await asyncio.gather(*child_tasks, return_exceptions=True)
        logger.debug(f"Sub-scans completed for directory: {directory_path}")
        for res in gathered_results:
            if isinstance(res, Exception):
                logger.error(f"A sub-scan task failed for parent {directory_path}: {res}")
                any_error_in_subtasks = True # An error occurred in a subtask
            elif res: # res is (files, folders, size, err_flag_from_sub_scan)
                r_files, r_folders, r_size, r_err_from_sub = res
                aggregated_num_files += r_files
                aggregated_num_folders += r_folders # Add all folders found in the sub-scan
                aggregated_total_size += r_size
                if r_err_from_sub:
                    any_error_in_subtasks = True # Propagate error flag from subtask

    final_error_status = error_occurred_current_level or any_error_in_subtasks

    logger.info(f"Finished async scanning {directory_path}. Directly found: {num_files_at_this_level} files, {num_folders_at_this_level} direct subfolders. Total aggregated: {aggregated_num_files} files, {aggregated_num_folders} folders. Size of files at this level: {total_size_at_this_level} bytes. Aggregated size: {aggregated_total_size} bytes.")
    
    dir_scan_end_time = time.monotonic()
    dir_duration = dir_scan_end_time - dir_scan_start_time
    logger.debug(f"Time taken to process directory {directory_path}: {dir_duration:.2f} seconds (includes waiting for sub-scans)")
    
    return aggregated_num_files, aggregated_num_folders, aggregated_total_size, final_error_status


async def main():
    parser = argparse.ArgumentParser(description="Analyzes a directory asynchronously.")
    # Add --loglevel argument
    parser.add_argument(
        "--loglevel",
        default="INFO",
        choices=["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"],
        help="Set the logging level (default: INFO)"
    )
    parser.add_argument(
        "--directory",
        "-d",
        type=str,
        required=True,
        help="The path to the directory to be analyzed.",
    )
    # --threads argument is removed as asyncio handles concurrency differently.
    # Consider adding --concurrency-limit if needed for asyncio.Semaphore in scan_directory.
    
    args = parser.parse_args()

    # Set up logging based on command-line argument
    numeric_level = getattr(logging, args.loglevel.upper(), None)
    if not isinstance(numeric_level, int):
        # This should not happen due to choices in argparse, but as a safeguard
        raise ValueError(f"Invalid log level: {args.loglevel}")
    
    # Reverted to a simpler logging format without %(taskName)s due to environment compatibility issues.
    logging.basicConfig(level=numeric_level, 
                        format='%(asctime)s - %(levelname)s - %(threadName)s - %(message)s')
    # File handler can be added here if desired:
    # file_handler = logging.FileHandler("directory_scan_async.log")
    # formatter = logging.Formatter('%(asctime)s - %(levelname)s - %(threadName)s - %(message)s')
    # file_handler.setFormatter(formatter)
    # logging.getLogger().addHandler(file_handler) # Add to root logger or specific logger
    
    logger.info("Async Script started.")
    logger.info(f"Analyzing directory: {args.directory} (Log level: {args.loglevel.upper()})")

    overall_start_time = time.monotonic()
    analysis_start_time = time.monotonic() # Placed after initial checks

    # Initial synchronous directory validation
    if not os.path.isdir(args.directory): # os.path.isdir is sync, acceptable for initial check
        logger.error(f"Error: The path '{args.directory}' is not a valid directory or is inaccessible.")
        overall_end_time = time.monotonic()
        logger.info(f"Total script execution time: {(overall_end_time - overall_start_time):.2f} seconds.")
        logger.info("Async Script finished with errors.")
        return
    
    # A quick synchronous pre-check for root directory readability before diving into async operations
    try:
        os.listdir(args.directory)
    except PermissionError:
        logger.error(f"Error: Permission denied to list contents of root directory '{args.directory}'.")
        overall_end_time = time.monotonic()
        logger.info(f"Total script execution time: {(overall_end_time - overall_start_time):.2f} seconds.")
        logger.info("Async Script finished with errors.")
        return
    except FileNotFoundError: # Should be caught by isdir, but for safety
        logger.error(f"Error: Root directory '{args.directory}' not found after initial check (race condition?).")
        overall_end_time = time.monotonic()
        logger.info(f"Total script execution time: {(overall_end_time - overall_start_time):.2f} seconds.")
        logger.info("Async Script finished with errors.")
        return


    total_files, total_folders, total_size, errors = (0,0,0,True) # Default values

    try:
        total_files, total_folders, total_size, errors = await scan_directory(args.directory)
        
        analysis_end_time = time.monotonic()
        core_analysis_duration = analysis_end_time - analysis_start_time
        logger.info(f"Core analysis time: {core_analysis_duration:.2f} seconds.")

        size_units = ["B", "KB", "MB", "GB", "TB"]
        size_idx = 0
        readable_size = float(total_size)
        while readable_size >= 1024 and size_idx < len(size_units) - 1:
            readable_size /= 1024
            size_idx += 1
        total_size_formatted = f"{readable_size:.2f} {size_units[size_idx]}"

        # Log summary results after timing
        logger.info(f"--- Directory Analysis Summary ---")
        logger.info(f"Total files: {total_files}")
        logger.info(f"Total folders: {total_folders}")
        logger.info(f"Total size: {total_size_formatted} ({total_size} bytes)")
        if errors:
            logger.warning("Some errors occurred during the scan. Check logs for details.")

    except Exception as e:
        logger.error(f"An unexpected error occurred in main: {e}", exc_info=True)
        analysis_end_time = time.monotonic() # Ensure it's set
        core_analysis_duration = analysis_end_time - analysis_start_time
        logger.info(f"Core analysis time (ended with error): {core_analysis_duration:.2f} seconds.")
        # errors will retain its last value or True if this block is hit before scan_directory completes fully

    overall_end_time = time.monotonic()
    total_script_duration = overall_end_time - overall_start_time
    logger.info(f"Total script execution time: {total_script_duration:.2f} seconds.")
    logger.info("Async Script finished.")


if __name__ == "__main__":
    asyncio.run(main())
