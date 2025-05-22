import unittest
import os
import shutil
import tempfile
import logging
import io
import asyncio # Added
from unittest.mock import patch, AsyncMock # Added AsyncMock

# Assuming directory_analyzer.py is in the same directory or sys.path is configured
import directory_analyzer
# Import aio_os to mock it by its imported name in directory_analyzer
from directory_analyzer import aio_os 

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
        num_files, num_folders, total_size, errors = asyncio.run(
            directory_analyzer.scan_directory(self.empty_dir)
        )
        self.assertEqual(num_files, 0)
        self.assertEqual(num_folders, 0)
        self.assertEqual(total_size, 0)
        self.assertFalse(errors)

    def test_directory_with_files_only(self):
        num_files, num_folders, total_size, errors = asyncio.run(
            directory_analyzer.scan_directory(self.files_only_dir)
        )
        self.assertEqual(num_files, self.files_only_expected_files)
        self.assertEqual(num_folders, self.files_only_expected_folders)
        self.assertEqual(total_size, self.files_only_expected_size)
        self.assertFalse(errors)

    def test_nested_directories(self):
        num_files, num_folders, total_size, errors = asyncio.run(
            directory_analyzer.scan_directory(self.nested_dir)
        )
        self.assertEqual(num_files, self.nested_expected_files)
        self.assertEqual(num_folders, self.nested_expected_folders)
        self.assertEqual(total_size, self.nested_expected_size)
        self.assertFalse(errors)

    def test_nonexistent_directory(self):
        non_existent_path = os.path.join(self.test_dir, "does_not_exist")
        num_files, num_folders, total_size, errors = asyncio.run(
            directory_analyzer.scan_directory(non_existent_path)
        )
        self.assertEqual(num_files, 0)
        self.assertEqual(num_folders, 0)
        self.assertEqual(total_size, 0)
        self.assertTrue(errors) # Expecting the error flag to be true

    # Patch 'aiofiles.os.listdir' as used in directory_analyzer.py (imported as aio_os)
    # Note: The actual import in directory_analyzer.py is `import aiofiles.os as aio_os`
    # So we need to patch `directory_analyzer.aio_os.listdir`
    @patch('directory_analyzer.aio_os.listdir', new_callable=AsyncMock)
    async def _run_permission_denied_test(self, mock_aio_listdir):
        permission_test_dir = os.path.join(self.test_dir, "perm_test")
        os.makedirs(permission_test_dir)
        accessible_file_path = os.path.join(permission_test_dir, "accessible_file.txt")
        self._create_file(accessible_file_path, 10) # Path relative to self.test_dir for _create_file

        no_access_sub_path = os.path.join(permission_test_dir, "no_access_sub")
        # We don't need to os.makedirs(no_access_sub_path) if listdir for parent is mocked,
        # but it helps to conceptualize. If listdir for parent *is* called, then it must exist.
        # For this test, listdir on "no_access_sub_path" itself will raise the error.
        
        # Store original os.listdir to use it for the accessible directory
        original_os_listdir = os.listdir

        async def side_effect_aio_listdir(path):
            if path == permission_test_dir:
                # For the parent directory, list its actual contents (accessible_file.txt, no_access_sub)
                # This requires knowing what should be "seen" by listdir.
                # Let's assume it sees "accessible_file.txt" and "no_access_sub" (as a name).
                return ["accessible_file.txt", "no_access_sub"]
            elif path == no_access_sub_path:
                raise PermissionError("Mocked permission error for aio_os.listdir")
            # Fallback for other paths if any (e.g. during _create_file if it uses listdir, though it doesn't)
            # This part might not be strictly necessary if the test is tightly controlled.
            return await asyncio.to_thread(original_os_listdir, path)
        
        mock_aio_listdir.side_effect = side_effect_aio_listdir

        # Mock asyncio.to_thread for os.lstat
        # We need to make sure lstat works for accessible_file.txt and no_access_sub
        # and then perhaps for items inside no_access_sub if listdir didn't fail for it.
        original_os_lstat = os.lstat
        async def mock_lstat_effect(path):
            if path == os.path.join(permission_test_dir, "accessible_file.txt"):
                # Return a stat object for a file
                s = os.stat_result((0o100644, 0, 0, 0, 0, 0, 10, 0, 0, 0)) # Regular file, 10 bytes
                return s
            elif path == os.path.join(permission_test_dir, "no_access_sub"):
                 # Return a stat object for a directory
                s = os.stat_result((0o040755, 0, 0, 0, 0, 0, 0, 0, 0, 0)) # Directory
                return s
            return await asyncio.to_thread(original_os_lstat, path)

        with patch('asyncio.to_thread', new_callable=AsyncMock) as mock_async_to_thread:
            # Ensure that the mock_async_to_thread correctly handles different functions passed to asyncio.to_thread
            # The lambda should check `func` before deciding which mock effect to apply.
            async def to_thread_side_effect(func_to_run, *args, **kwargs):
                if func_to_run == os.lstat:
                    return await mock_lstat_effect(args[0]) # args[0] should be the path
                # Add more conditions here if other functions are wrapped by to_thread and need mocking
                else: # Default behavior for other functions wrapped by to_thread
                    return await asyncio.get_event_loop().run_in_executor(None, func_to_run, *args) # Simulate actual to_thread
            mock_async_to_thread.side_effect = to_thread_side_effect


            self.da_logger.setLevel(logging.ERROR)
            self.ch.setLevel(logging.ERROR)

            num_files, num_folders, total_size, errors = await directory_analyzer.scan_directory(
                permission_test_dir
            )

        self.assertEqual(num_files, 1, "Should count the accessible file.")
        self.assertEqual(num_folders, 1, "Should count 'no_access_sub' as a folder found, even if not scannable.")
        self.assertEqual(total_size, 10, "Total size should only be of accessible_file.txt.")
        
        log_contents = self.log_capture_string.getvalue()
        # Adjusting the assertion to match the actual log output format more closely.
        # The log includes the error message after the path, separated by a colon and space.
        self.assertIn(f"Could not list directory {no_access_sub_path}: ", log_contents)
        # The overall scan of permission_test_dir itself *did not* fail at its top level.
        # An error occurred in a sub-task (scanning no_access_sub_path).
        # The 'errors' flag returned by scan_directory indicates if *any* error occurred.
        self.assertTrue(errors, "The 'errors' flag should be True as a sub-scan failed.")

    def test_permission_denied_subdirectory(self):
        asyncio.run(self._run_permission_denied_test())


    def test_logging_output_info_scan_messages(self):
        self.da_logger.setLevel(logging.INFO) # Ensure logger processes INFO
        self.ch.setLevel(logging.INFO)        # Ensure handler captures INFO

        asyncio.run(directory_analyzer.scan_directory(self.empty_dir))
        
        log_contents = self.log_capture_string.getvalue()
        self.assertIn(f"Async scanning directory: {self.empty_dir}", log_contents) # Message changed
        self.assertIn(f"Finished async scanning {self.empty_dir}", log_contents) # Message changed

    def test_logging_output_debug_file_messages(self):
        self.da_logger.setLevel(logging.DEBUG) # Ensure logger processes DEBUG
        self.ch.setLevel(logging.DEBUG)       # Ensure handler captures DEBUG

        asyncio.run(directory_analyzer.scan_directory(self.files_only_dir))
            
        log_contents = self.log_capture_string.getvalue()
        self.assertIn(f"Found file: {os.path.join(self.files_only_dir, 'file1.txt')}", log_contents)
        self.assertIn(f"Found file: {os.path.join(self.files_only_dir, 'file2.dat')}", log_contents)
        # Also check for the per-directory timing message if it's at DEBUG
        self.assertIn(f"Time taken to process directory {self.files_only_dir}", log_contents)


if __name__ == '__main__':
    # No specific logging.basicConfig needed here for tests usually,
    # as setUp configures the specific 'directory_analyzer' logger for capture.
    # If run with `python -m unittest test_directory_analyzer.py`, unittest's own
    # test runner handles setup.
    unittest.main()
