# Fast Dupe Finder

A blazingly fast, cross-platform tool for finding duplicate files on your local machine, built with Rust and Tauri.

## Features

- **High-Performance Core**: The backend is written in Rust, leveraging a multi-stage hashing algorithm for maximum speed and efficiency.
    - **Stage 1: Size Check**: Instantly dismisses files of unique sizes without reading their content.
    - **Stage 2: Partial Hash**: Uses the ultra-fast `xxHash` algorithm on the head and tail of files to quickly rule out the vast majority of non-duplicates with minimal I/O.
    - **Stage 3: Full Hash**: Employs the parallel `BLAKE3` algorithm for cryptographic-level assurance of duplication on the remaining candidates.
- **Modern GUI**: A clean and intuitive user interface built with Tauri, providing a native application feel using modern web technologies.
- **Smart Selection**: Automatically select files for deletion based on rules like "keep newest", "keep oldest", or "keep the first one in the list".
- **Safe Deletion**: A clear confirmation step before any files are permanently removed from your system.
- **Detailed View**: See file paths, modification dates, and sizes clearly grouped together.

## Prerequisites

To build this project, you will need to set up the Tauri development environment.

1.  **Rust**: Install Rust via [rustup](https://rustup.rs/).
    ```sh
    curl --proto '=https' --tlsv1.2 -sSf https://sh.rustup.rs | sh
    ```
2.  **Node.js**: Required for the web frontend and the Tauri CLI. You can install it from the [official website](https://nodejs.org/).
3.  **System Dependencies**: You will need to install specific dependencies for building Tauri applications on your operating system (e.g., `build-essential`, `libwebkit2gtk-4.0-dev` on Debian/Ubuntu). Please follow the complete instructions for your OS on the **[official Tauri guide](https://tauri.app/v1/guides/getting-started/prerequisites)**.

## Building and Running

1.  **Clone the repository:**
    ```sh
    git clone <repository-url>
    cd fast-dupe-finder
    ```
2.  **Install the Tauri CLI:**
    This is a command-line tool to help manage Tauri applications.
    ```sh
    cargo install tauri-cli
    ```
3.  **Run in Development Mode:**
    This command will build the Rust backend and start the GUI in a development window that supports hot-reloading for the frontend.
    ```sh
    cargo tauri dev
    ```
4.  **Build for Production:**
    To create a standalone, optimized executable for your platform:
    ```sh
    cargo tauri build
    ```
    The final application bundle will be located in the `src-tauri/target/release/bundle/` directory.
