import argparse
import os
import concurrent.futures
import logging
import threading # Explicitly import threading
import time

# Set up logger for this module
logger = logging.getLogger(__name__)

def scan_directory(directory_path, executor, num_threads):
    dir_scan_start_time = time.monotonic()
    logger.info(f"Scanning directory: {directory_path}")
    num_files_in_current_path = 0
    num_folders_in_current_path = 0 # Folders directly in this path
    total_size_of_files_in_current_path = 0
    sub_dir_futures = []

    try:
        for item_name in os.listdir(directory_path):
            item_path = os.path.join(directory_path, item_name)
            if os.path.isfile(item_path):
                num_files_in_current_path += 1
                try:
                    file_size = os.path.getsize(item_path)
                    total_size_of_files_in_current_path += file_size
                    logger.debug(f"Found file: {item_path}, Size: {file_size}")
                except FileNotFoundError:
                    logger.warning(f"File not found during size check: {item_path}")
                except PermissionError:
                    logger.warning(f"Permission denied for size check: {item_path}")

            elif os.path.isdir(item_path):
                num_folders_in_current_path += 1
                logger.debug(f"Found subdirectory: {item_path}. Submitting to executor.")
                future = executor.submit(scan_directory, item_path, executor, num_threads)
                sub_dir_futures.append(future)

    except FileNotFoundError:
        logger.error(f"Directory not found: {directory_path}")
        return 0, 0, 0, True # num_files, num_folders, total_size, error_flag
    except PermissionError:
        logger.error(f"Permission denied for directory: {directory_path}")
        return 0, 0, 0, True # num_files, num_folders, total_size, error_flag
    
    # Initialize aggregated counts from this level's direct findings
    total_files_aggregated = num_files_in_current_path
    total_folders_aggregated = num_folders_in_current_path # Start with folders found directly at this level
    total_size_aggregated = total_size_of_files_in_current_path

    for future in concurrent.futures.as_completed(sub_dir_futures):
        logger.debug(f"Aggregating results from a completed subdirectory future for parent: {directory_path}")
        try:
            sub_files, sub_folders, sub_size, sub_error = future.result()
            if not sub_error:
                total_files_aggregated += sub_files
                total_folders_aggregated += sub_folders # These are all folders from sub-scans
                total_size_aggregated += sub_size
        except Exception as e:
            logger.error(f"Error processing a subdirectory result for parent {directory_path}: {e}")

    logger.info(f"Finished scanning {directory_path}. Directly found: {num_files_in_current_path} files, {num_folders_in_current_path} subfolders. Size of files in this dir: {total_size_of_files_in_current_path} bytes.")
    
    dir_scan_end_time = time.monotonic()
    dir_duration = dir_scan_end_time - dir_scan_start_time
    logger.debug(f"Time taken to process directory {directory_path}: {dir_duration:.2f} seconds (includes waiting for sub-scans)")
    
    return total_files_aggregated, total_folders_aggregated, total_size_aggregated, False

def main():
    # Basic logging configuration
    logging.basicConfig(level=logging.INFO, # Set to logging.DEBUG to see per-directory times
                        format='%(asctime)s - %(levelname)s - %(threadName)s - %(message)s')

    overall_start_time = time.monotonic() # Start overall timer early
    logger.info("Script started.")
    parser = argparse.ArgumentParser(description="Analyzes a directory.")
    parser.add_argument(
        "--directory",
        "-d",
        type=str,
        required=True,
        help="The path to the directory to be analyzed.",
    )
    parser.add_argument(
        "--threads",
        "-t",
        type=int,
        default=1,
        help="The number of threads to use for scanning (default: 1).",
    )
    # Future consideration: Add --loglevel argument
    # parser.add_argument("--loglevel", default="INFO", choices=["DEBUG", "INFO", "WARNING", "ERROR"], help="Set the logging level")

    args = parser.parse_args()
    
    # # If loglevel argument is added:
    # numeric_level = getattr(logging, args.loglevel.upper(), None)
    # if not isinstance(numeric_level, int):
    #     raise ValueError(f"Invalid log level: {args.loglevel}")
    # logging.basicConfig(level=numeric_level, format='%(asctime)s - %(levelname)s - %(threadName)s - %(message)s')
    
    logger.info(f"Analyzing directory: {args.directory} with {args.threads} thread(s)")
    
    if not os.path.exists(args.directory):
        logger.error(f"The specified directory '{args.directory}' does not exist.")
        overall_end_time = time.monotonic()
        logger.info(f"Total execution time: {(overall_end_time - overall_start_time):.2f} seconds.")
        logger.info("Script finished with errors.")
        return
    if not os.path.isdir(args.directory):
        logger.error(f"The specified path '{args.directory}' is not a directory.")
        overall_end_time = time.monotonic()
        logger.info(f"Total execution time: {(overall_end_time - overall_start_time):.2f} seconds.")
        logger.info("Script finished with errors.")
        return
    try:
        os.listdir(args.directory) 
    except PermissionError:
        logger.error(f"Permission denied to access the specified directory '{args.directory}'.")
        overall_end_time = time.monotonic()
        logger.info(f"Total execution time: {(overall_end_time - overall_start_time):.2f} seconds.")
        logger.info("Script finished with errors.")
        return
    except FileNotFoundError: 
        logger.error(f"The specified directory '{args.directory}' was not found (race condition?).")
        overall_end_time = time.monotonic()
        logger.info(f"Total execution time: {(overall_end_time - overall_start_time):.2f} seconds.")
        logger.info("Script finished with errors.")
        return

    overall_num_files = 0
    overall_num_folders = 0
    overall_total_size = 0
    error_occurred = False # Initialize error_occurred

    # Start actual analysis timing more precisely here if initial checks are considered setup
    analysis_start_time = time.monotonic()

    with concurrent.futures.ThreadPoolExecutor(max_workers=args.threads) as executor:
        overall_num_files, overall_num_folders, overall_total_size, error_occurred = scan_directory(args.directory, executor, args.threads)
    
    analysis_end_time = time.monotonic() # End of actual analysis
    overall_end_time = time.monotonic() # End of overall script execution (can be same as analysis_end_time if no more code runs)
    
    # Log timing information first
    logger.info(f"Core analysis time: {(analysis_end_time - analysis_start_time):.2f} seconds.")
    logger.info(f"Total script execution time: {(overall_end_time - overall_start_time):.2f} seconds.")

    # Then log the summary of findings
    if not error_occurred or (overall_num_files > 0 or overall_num_folders > 0):
        logger.info(f"\n--- Directory Analysis Summary ---")
        logger.info(f"Total files: {overall_num_files}")
        logger.info(f"Total folders: {overall_num_folders}")
        logger.info(f"Total size: {overall_total_size} bytes")
    elif error_occurred:
        logger.info("Directory analysis completed with errors. Some parts may have been skipped. Summary might be incomplete.")
    
    logger.info("Script finished.")

if __name__ == "__main__":
    main()
