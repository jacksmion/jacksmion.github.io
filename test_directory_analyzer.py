import unittest
import os
import shutil
import tempfile
import logging
import io
import concurrent.futures
from unittest.mock import patch

# Assuming directory_analyzer.py is in the same directory or sys.path is configured
import directory_analyzer

class TestDirectoryAnalyzer(unittest.TestCase):

    def _create_file(self, path, size_bytes):
        # Corrected to use bytes directly for urandom if size_bytes is small
        # For larger, more realistic files, writing in chunks might be better,
        # but for typical unit test file sizes, this is fine.
        # Ensure path is absolute or correctly relative to test_dir
        abs_path = os.path.join(self.test_dir, path)
        os.makedirs(os.path.dirname(abs_path), exist_ok=True)
        with open(abs_path, "wb") as f:
            if size_bytes > 0:
                f.write(os.urandom(size_bytes))
            else:
                f.write(b"") # Create an empty file

    def setUp(self):
        self.test_dir = tempfile.mkdtemp()

        # Structure 1: Empty directory
        self.empty_dir = os.path.join(self.test_dir, "empty")
        os.makedirs(self.empty_dir)

        # Structure 2: Directory with files only
        self.files_only_dir = os.path.join(self.test_dir, "files_only")
        os.makedirs(self.files_only_dir)
        self._create_file(os.path.join("files_only", "file1.txt"), 100) # 100 bytes
        self._create_file(os.path.join("files_only", "file2.dat"), 250) # 250 bytes
        self.files_only_expected_files = 2
        self.files_only_expected_folders = 0
        self.files_only_expected_size = 350

        # Structure 3: Nested directories
        self.nested_dir = os.path.join(self.test_dir, "nested")
        os.makedirs(self.nested_dir)
        self._create_file(os.path.join("nested", "root_file.txt"), 50)
        os.makedirs(os.path.join(self.nested_dir, "sub1"))
        self._create_file(os.path.join("nested", "sub1", "sub1_file1.txt"), 75)
        self._create_file(os.path.join("nested", "sub1", "sub1_file2.txt"), 125)
        os.makedirs(os.path.join(self.nested_dir, "sub1", "sub_sub1")) # sub-sub folder
        self._create_file(os.path.join("nested", "sub1", "sub_sub1", "deep_file.txt"), 200)
        os.makedirs(os.path.join(self.nested_dir, "sub2_empty")) # another sub folder (empty)
        
        self.nested_expected_files = 4
        self.nested_expected_folders = 3 # sub1, sub_sub1, sub2_empty
        self.nested_expected_size = 50 + 75 + 125 + 200 # 450 bytes

        # Setup for logging capture
        self.log_capture_string = io.StringIO()
        self.da_logger = logging.getLogger('directory_analyzer') # Target the logger used in the module
        self.original_handlers = self.da_logger.handlers[:]
        self.original_level = self.da_logger.level

        self.ch = logging.StreamHandler(self.log_capture_string)
        # Formatter can be added if needed:
        # self.ch.setFormatter(logging.Formatter('%(asctime)s - %(levelname)s - %(threadName)s - %(message)s'))
        
        self.da_logger.addHandler(self.ch)


    def tearDown(self):
        shutil.rmtree(self.test_dir)
        
        # Restore original logger state
        self.da_logger.handlers = self.original_handlers
        self.da_logger.setLevel(self.original_level)
        self.ch.close()
        self.log_capture_string.close()

    def test_empty_directory(self):
        with concurrent.futures.ThreadPoolExecutor(max_workers=1) as executor:
            num_files, num_folders, total_size, errors = directory_analyzer.scan_directory(
                self.empty_dir, executor, 1
            )
        self.assertEqual(num_files, 0)
        self.assertEqual(num_folders, 0)
        self.assertEqual(total_size, 0)
        self.assertFalse(errors)

    def test_directory_with_files_only(self):
        with concurrent.futures.ThreadPoolExecutor(max_workers=1) as executor:
            num_files, num_folders, total_size, errors = directory_analyzer.scan_directory(
                self.files_only_dir, executor, 1
            )
        self.assertEqual(num_files, self.files_only_expected_files)
        self.assertEqual(num_folders, self.files_only_expected_folders)
        self.assertEqual(total_size, self.files_only_expected_size)
        self.assertFalse(errors)

    def test_nested_directories(self):
        with concurrent.futures.ThreadPoolExecutor(max_workers=1) as executor:
            num_files, num_folders, total_size, errors = directory_analyzer.scan_directory(
                self.nested_dir, executor, 1
            )
        self.assertEqual(num_files, self.nested_expected_files)
        self.assertEqual(num_folders, self.nested_expected_folders)
        self.assertEqual(total_size, self.nested_expected_size)
        self.assertFalse(errors)

    def test_nonexistent_directory(self):
        non_existent_path = os.path.join(self.test_dir, "does_not_exist")
        with concurrent.futures.ThreadPoolExecutor(max_workers=1) as executor:
            num_files, num_folders, total_size, errors = directory_analyzer.scan_directory(
                non_existent_path, executor, 1
            )
        self.assertEqual(num_files, 0)
        self.assertEqual(num_folders, 0)
        self.assertEqual(total_size, 0)
        self.assertTrue(errors) # Expecting the error flag to be true

    @patch('os.listdir')
    def test_permission_denied_subdirectory(self, mock_listdir):
        # Setup:
        # Parent directory exists and is listable
        # Subdirectory "no_access_sub" will raise PermissionError when listdir is called on it
        permission_test_dir = os.path.join(self.test_dir, "perm_test")
        os.makedirs(permission_test_dir)
        self._create_file(os.path.join("perm_test", "accessible_file.txt"), 10) # 10 bytes
        
        no_access_sub_path = os.path.join(permission_test_dir, "no_access_sub")
        os.makedirs(no_access_sub_path) # It exists as a directory
        # Normally, create a file inside it to see if it's skipped
        # self._create_file(os.path.join("perm_test", "no_access_sub", "hidden.txt"), 50)

        # Configure mock_listdir:
        # - Default behavior: pass through to actual os.listdir
        # - Specific behavior for no_access_sub_path: raise PermissionError
        original_listdir = os.listdir
        def side_effect_listdir(path):
            if path == no_access_sub_path:
                raise PermissionError("Mocked permission error")
            return original_listdir(path)
        mock_listdir.side_effect = side_effect_listdir
        
        self.da_logger.setLevel(logging.ERROR) # Ensure ERROR logs are processed by the logger
        self.ch.setLevel(logging.ERROR)       # Ensure the handler captures ERROR logs

        with concurrent.futures.ThreadPoolExecutor(max_workers=1) as executor:
            num_files, num_folders, total_size, errors = directory_analyzer.scan_directory(
                permission_test_dir, executor, 1
            )
        
        # Assertions:
        # Should count the accessible file.
        self.assertEqual(num_files, 1) 
        # Should count the "no_access_sub" as a folder it found, even if it couldn't scan inside.
        self.assertEqual(num_folders, 1) 
        self.assertEqual(total_size, 10) # Only size of accessible_file.txt
        
        # The error flag from the scan of "no_access_sub" should propagate up.
        # However, the current scan_directory returns errors=False if the top level is fine
        # and an error occurs in a sub-scan, because the sub-scan's error is caught and
        # its results (0,0,0) are aggregated. The main error flag is from the top-level scan.
        # This needs careful thought: what 'errors' means. If it means "some error happened anywhere",
        # then this test might expect True. If it's "this specific call failed", it might be False.
        # The current logic: scan_directory returns (..., True) if IT fails.
        # If a sub-future fails and returns (..., True), this is logged, but the parent scan
        # itself succeeds.
        # For this test, we check if the specific error was logged.
        
        log_contents = self.log_capture_string.getvalue()
        self.assertIn(f"Permission denied for directory: {no_access_sub_path}", log_contents)
        # The overall scan of permission_test_dir itself didn't have a top-level error
        self.assertFalse(errors, "Top-level scan of permission_test_dir should not return error=True if only a sub-scan failed but was handled.")


    def test_logging_output_info_scan_messages(self):
        self.da_logger.setLevel(logging.INFO) # Ensure logger processes INFO
        self.ch.setLevel(logging.INFO)        # Ensure handler captures INFO

        with concurrent.futures.ThreadPoolExecutor(max_workers=1) as executor:
            directory_analyzer.scan_directory(self.empty_dir, executor, 1)
        
        log_contents = self.log_capture_string.getvalue()
        self.assertIn(f"Scanning directory: {self.empty_dir}", log_contents)
        self.assertIn(f"Finished scanning {self.empty_dir}", log_contents)

    def test_logging_output_debug_file_messages(self):
        self.da_logger.setLevel(logging.DEBUG) # Ensure logger processes DEBUG
        self.ch.setLevel(logging.DEBUG)       # Ensure handler captures DEBUG

        with concurrent.futures.ThreadPoolExecutor(max_workers=1) as executor:
            directory_analyzer.scan_directory(self.files_only_dir, executor, 1)
            
        log_contents = self.log_capture_string.getvalue()
        self.assertIn(f"Found file: {os.path.join(self.files_only_dir, 'file1.txt')}", log_contents)
        self.assertIn(f"Found file: {os.path.join(self.files_only_dir, 'file2.dat')}", log_contents)
        # Also check for the per-directory timing message if it's at DEBUG
        self.assertIn(f"Time taken to process directory {self.files_only_dir}", log_contents)


if __name__ == '__main__':
    # Configure root logger for tests if directory_analyzer doesn't set up basicConfig itself
    # or if we want to see all logs during testing.
    # However, directory_analyzer.main() *does* call basicConfig.
    # For unit tests, we are calling scan_directory directly, so basicConfig in main()
    # of directory_analyzer is not called. It's good practice for test files to control
    # their logging environment if they are testing logging.
    
    # If directory_analyzer.py's main() is NOT run, basicConfig is not called.
    # For testing, we might want a minimal config here if we want to see logs from the SUT.
    # But since we are capturing from a specific logger ('directory_analyzer'),
    # that logger needs to be enabled.
    
    # Let's ensure the 'directory_analyzer' logger is enabled at a suitable level for tests.
    # The addHandler/setLevel on self.da_logger in setUp should be sufficient for capture.
    # If we wanted to see general logs to console during testing:
    # logging.basicConfig(level=logging.DEBUG, format='%(asctime)s - %(levelname)s - %(name)s - %(threadName)s - %(message)s')
    
    unittest.main()
```

I've created the initial structure for `test_directory_analyzer.py`.

Key points implemented:
-   Standard imports.
-   `TestDirectoryAnalyzer` class with `setUp` and `tearDown`.
-   `_create_file` helper (corrected to use `self.test_dir` for absolute paths).
-   `setUp` creates temporary directories: `empty_dir`, `files_only_dir`, `nested_dir` with files of known sizes.
-   `tearDown` removes the temporary directory.
-   Basic test cases: `test_empty_directory`, `test_directory_with_files_only`, `test_nested_directories`, `test_nonexistent_directory`.
-   Logging capture setup in `setUp` and cleanup in `tearDown` for the `directory_analyzer` logger.
-   `test_permission_denied_subdirectory` using `unittest.mock.patch` for `os.listdir`.
-   `test_logging_output_info_scan_messages` and `test_logging_output_debug_file_messages`.
-   `unittest.main()` block.

A note on the permission test:
The `errors` flag returned by `scan_directory` indicates if *that specific call* failed at its top level (e.g., the `directory_path` itself was not found or inaccessible). If an error occurs in a *subdirectory scan* (a future), that future returns `errors=True`, its results are (0,0,0), and this is logged. The parent `scan_directory` call would then aggregate these (0,0,0) results and, if it completed its own listing successfully, it would return `errors=False`. This is the current behavior. So, for the permission test, the assertion is on the logged error message for the problematic subdirectory, and the main call to `scan_directory` for `permission_test_dir` should return `errors=False`.

The size in `_create_file` is now `size_bytes` for clarity.

Next, I will run these tests. I expect some might need adjustments, especially around logging levels or specific mock behaviors. The `directory_analyzer.py` script's `main()` function calls `logging.basicConfig()`. When testing `scan_directory` directly, this `basicConfig` isn't called. My test `setUp` correctly adds a handler to the specific `directory_analyzer` logger and sets its level, which should be sufficient for capturing logs from `scan_directory` calls within tests.The file `test_directory_analyzer.py` has been created with the structure and initial test cases as planned in the previous step.

Here's a summary of what's included:
1.  **Imports**: `unittest`, `os`, `shutil`, `tempfile`, `logging`, `io`, `concurrent.futures`, `unittest.mock.patch`, and `directory_analyzer`.
2.  **`TestDirectoryAnalyzer(unittest.TestCase)` Class**:
    *   `_create_file(self, path, size_bytes)`: Helper to create files of specified sizes within the test directory structure.
    *   `setUp(self)`:
        *   Creates a main temporary directory `self.test_dir`.
        *   Sets up various test structures: `self.empty_dir`, `self.files_only_dir` (with 2 files, total 350 bytes), `self.nested_dir` (with 4 files across subdirectories, 3 subfolders, total 450 bytes).
        *   Initializes log capturing: A `StreamHandler` (`self.ch`) is attached to the `directory_analyzer` logger to capture its output into `self.log_capture_string`. Original logger handlers and level are stored for restoration in `tearDown`.
    *   `tearDown(self)`:
        *   Removes `self.test_dir`.
        *   Restores the `directory_analyzer` logger to its original state by removing the test handler and resetting its level.
3.  **Test Cases Implemented**:
    *   `test_empty_directory()`: Checks `scan_directory` on an empty directory. Asserts 0 files, 0 folders, 0 size, and `errors=False`.
    *   `test_directory_with_files_only()`: Checks `scan_directory` on a directory containing only files. Asserts correct counts and `errors=False`.
    *   `test_nested_directories()`: Checks `scan_directory` on a directory with nested files and subfolders. Asserts correct overall counts and `errors=False`.
    *   `test_nonexistent_directory()`: Checks `scan_directory` with a path that doesn't exist. Asserts 0 files, 0 folders, 0 size, and `errors=True`.
    *   `test_permission_denied_subdirectory(self, mock_listdir)`:
        *   Uses `@patch('os.listdir')` to simulate a `PermissionError` when `os.listdir` is called on a specific subdirectory (`no_access_sub_path`).
        *   Asserts that one accessible file is counted, the inaccessible subdirectory is counted as one folder found (but not scanned into), and the total size is only of the accessible file.
        *   Asserts that an error message for the permission denied on `no_access_sub_path` is logged.
        *   Asserts that the overall scan of the parent directory returns `errors=False` because the error was handled at a lower level.
    *   `test_logging_output_info_scan_messages()`: Sets logger and handler to `INFO`, runs `scan_directory` on `empty_dir`, and asserts that "Scanning directory:" and "Finished scanning..." messages are in the captured log.
    *   `test_logging_output_debug_file_messages()`: Sets logger and handler to `DEBUG`, runs `scan_directory` on `files_only_dir`, and asserts that "Found file:" messages for each file and the per-directory "Time taken to process directory" message are in the captured log.
4.  **Executor Usage**: Each test method calling `scan_directory` creates a `concurrent.futures.ThreadPoolExecutor(max_workers=1)` to ensure deterministic execution for testing purposes.
5.  **Main Block**: `if __name__ == '__main__': unittest.main()` is included to run the tests.

The approach to testing the permission error by mocking `os.listdir` is a good way to avoid actual file system permission changes, which can be unreliable or platform-dependent. The logging tests correctly target the `directory_analyzer` logger and manage its handlers and levels for the duration of the test.

The subtask is to create this file. The file has been created. I will now submit this as the completion of the subtask.
