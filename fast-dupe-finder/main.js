const { invoke } = window.__TAURI__.tauri;

// DOM Elements
let pathInput, scanButton, resultsDiv, statusDiv, deleteButton;
let selectAllButFirstButton, selectAllButNewestButton, selectAllButOldestButton;

// App State
let currentGroups = [];

window.addEventListener("DOMContentLoaded", () => {
    // Query elements
    pathInput = document.querySelector("#path-input");
    scanButton = document.querySelector("#scan-button");
    resultsDiv = document.querySelector("#results");
    statusDiv = document.querySelector("#status");
    deleteButton = document.querySelector("#delete-selected-button");
    selectAllButFirstButton = document.querySelector("#select-all-but-first");
    selectAllButNewestButton = document.querySelector("#select-all-but-newest");
    selectAllButOldestButton = document.querySelector("#select-all-but-oldest");

    // Event Listeners
    scanButton.addEventListener("click", () => {
        const path = pathInput.value;
        if (!path) {
            alert("Please enter a path to scan.");
            return;
        }
        performScan(path);
    });

    deleteButton.addEventListener("click", deleteSelectedFiles);
    selectAllButFirstButton.addEventListener("click", () => selectFiles("first"));
    selectAllButNewestButton.addEventListener("click", () => selectFiles("newest"));
    selectAllButOldestButton.addEventListener("click", () => selectFiles("oldest"));
});

async function performScan(path) {
    statusDiv.textContent = "Scanning... This may take a while.";
    resultsDiv.innerHTML = "";
    scanButton.disabled = true;
    updateDeleteButtonState();

    try {
        currentGroups = await invoke("scan_directory", { path: path, minSizeStr: "1" });

        if (currentGroups.length === 0) {
            statusDiv.textContent = "Scan complete. No duplicates found.";
        } else {
            statusDiv.textContent = `Scan complete. Found ${currentGroups.length} groups of duplicates.`;
            displayResults(currentGroups);
        }
    } catch (error) {
        statusDiv.textContent = `Error: ${error}`;
    } finally {
        scanButton.disabled = false;
    }
}

function displayResults(groups) {
    resultsDiv.innerHTML = ""; // Clear previous results
    groups.forEach((group, groupIndex) => {
        const groupDiv = document.createElement("div");
        groupDiv.className = "duplicate-group";

        const header = document.createElement("h3");
        const totalSize = group.size_bytes * group.files.length;
        header.textContent = `Group ${groupIndex + 1} (${group.files.length} files, ${formatBytes(group.size_bytes)} each, Total: ${formatBytes(totalSize)})`;
        groupDiv.appendChild(header);

        const fileTable = document.createElement("table");
        fileTable.innerHTML = `
            <thead>
                <tr>
                    <th>Select</th>
                    <th>Path</th>
                    <th>Modified Date</th>
                </tr>
            </thead>
        `;
        const tbody = document.createElement("tbody");
        group.files.forEach((file, fileIndex) => {
            const tr = document.createElement("tr");
            const modifiedDate = new Date(file.modified.secs_since_epoch * 1000).toLocaleString();
            tr.innerHTML = `
                <td><input type="checkbox" class="file-checkbox" data-group-index="${groupIndex}" data-file-path="${file.path}"></td>
                <td>${file.path}</td>
                <td>${modifiedDate}</td>
            `;
            tbody.appendChild(tr);
        });
        fileTable.appendChild(tbody);
        groupDiv.appendChild(fileTable);
        resultsDiv.appendChild(groupDiv);
    });

    // Add event listener to all checkboxes to update delete button state
    document.querySelectorAll('.file-checkbox').forEach(cb => {
        cb.addEventListener('change', updateDeleteButtonState);
    });
}

function updateDeleteButtonState() {
    const anyChecked = document.querySelectorAll('.file-checkbox:checked').length > 0;
    deleteButton.disabled = !anyChecked;
}

function selectFiles(keep) {
    // Uncheck everything first
    document.querySelectorAll('.file-checkbox').forEach(cb => cb.checked = false);

    currentGroups.forEach((group, groupIndex) => {
        let filesToKeep = [];
        if (group.files.length > 1) {
            if (keep === 'first') {
                filesToKeep.push(group.files[0]);
            } else if (keep === 'newest') {
                const newest = group.files.reduce((a, b) => a.modified.secs_since_epoch > b.modified.secs_since_epoch ? a : b);
                filesToKeep.push(newest);
            } else if (keep === 'oldest') {
                const oldest = group.files.reduce((a, b) => a.modified.secs_since_epoch < b.modified.secs_since_epoch ? a : b);
                filesToKeep.push(oldest);
            }
        }

        // Check all files that are NOT in the keep list
        group.files.forEach(file => {
            if (!filesToKeep.some(keep_file => keep_file.path === file.path)) {
                const checkbox = document.querySelector(`.file-checkbox[data-file-path="${file.path}"]`);
                if (checkbox) {
                    checkbox.checked = true;
                }
            }
        });
    });

    updateDeleteButtonState();
}


async function deleteSelectedFiles() {
    const selectedPaths = Array.from(document.querySelectorAll('.file-checkbox:checked')).map(cb => cb.dataset.filePath);

    if (selectedPaths.length === 0) {
        alert("No files selected for deletion.");
        return;
    }

    if (!confirm(`Are you sure you want to delete ${selectedPaths.length} files? This action cannot be undone.`)) {
        return;
    }

    // Here we would invoke the backend.
    // For now, we'll just log it.
    statusDiv.textContent = `Attempting to delete ${selectedPaths.length} files...`;
    console.log("Files to delete:", selectedPaths);

    try {
        await invoke("delete_files", { paths: selectedPaths });
        statusDiv.textContent = `Successfully deleted ${selectedPaths.length} files. Please scan again to see updated results.`;
        resultsDiv.innerHTML = ""; // Clear results to force a rescan
        currentGroups = [];
        updateDeleteButtonState();
    } catch (error) {
        statusDiv.textContent = `Deletion error: ${error}`;
    }
}

function formatBytes(bytes, decimals = 2) {
    if (bytes === 0) return '0 Bytes';
    const k = 1024;
    const dm = decimals < 0 ? 0 : decimals;
    const sizes = ['Bytes', 'KB', 'MB', 'GB', 'TB'];
    const i = Math.floor(Math.log(bytes) / Math.log(k));
    return parseFloat((bytes / Math.pow(k, i)).toFixed(dm)) + ' ' + sizes[i];
}
