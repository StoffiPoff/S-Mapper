# S-Mapper

S-Mapper is a versatile and user-friendly tool for Windows that allows you to remap mouse and keyboard inputs to other keyboard commands. The application is designed to be highly configurable, allowing you to create custom mappings that are active only in specific applications.

Built with Python and PyQt6, S-Mapper runs quietly in the system tray and provides an intuitive interface for managing your key maps.

![S-Mapper Screenshot](S-Mapper-logo%20-%20256.png)

## Features

*   **Mouse-to-Keyboard Mapping:**
    *   Map single, double, or triple clicks of any mouse button (left, right, middle, x1, x2) to a specific keyboard key.
    *   Optionally add modifier keys (Ctrl, Alt, Shift) to the output.
*   **Keyboard-to-Keyboard Mapping:**
    *   Remap one keyboard key to another.
    *   Optionally add modifier keys (Ctrl, Alt, Shift) to the output.
*   **Targeted Window Mapping:**
    *   Apply mappings only when a specific application window is active.
    *   Select the target window from a list of active windows or specify it by a partial name match.
*   **Clipboard IP Ping Monitor:**
    *   A utility feature that monitors the clipboard for IP addresses.
    *   When an IP address is copied to the clipboard while a target window is active, it automatically sends a ping and displays the result (success or failure) as a temporary overlay near the cursor.
*   **System Tray Integration:**
    *   The application minimizes to the system tray for unobtrusive operation.
    *   A simple right-click menu allows you to show the app or exit.
*   **Dark Mode Interface:**
    *   A sleek and modern dark mode UI.

## How It Works

The application runs listeners for mouse and keyboard events in the background. When an input event matches a configured mapping, S-Mapper checks if the currently active window's title matches the target window for that mapping. If it does, the application simulates the corresponding keyboard output.

All configurations are saved in a `mappings.ini` file in the application's directory, which is loaded on startup.

## Usage

1.  **Launch the Application:** Run `s_mapper.exe`. The main window will appear, and an icon will be added to your system tray.

2.  **Create a New Mapping:**
    *   **Choose a Trigger:**
        *   **For Mouse:** Select a **Mouse Button** and specify the **Number of Presses** (e.g., 2 for a double-click).
        *   **For Keyboard:** Select a **Source Keyboard Key**.
        *   *Note:* You can only choose one trigger type at a time (either mouse or keyboard). The unused fields will be disabled.
    *   **Define the Output:**
        *   Select the **Target Keyboard Key**.
        *   Optionally, add a **Modifier Key** (e.g., `ctrl + alt`).
    *   **Set the Target Window:**
        *   Choose **"Free Text (Partial Match)"** and type a part of the target window's title (e.g., "Notepad").
        *   Or, choose **"Select from Active Windows"** and pick an application from the dropdown list. You can refresh the list with the "Refresh Windows" button.
    *   **Add the Mapping:** Click the **"Add Mapping"** button. Your new mapping will appear in the list.

3.  **Manage Mappings:**
    *   To remove a mapping, select it from the list and click **"Remove Selected"**.
    *   The **"Clear Fields"** button will reset all the input fields.

4.  **Minimize to Tray:** When you minimize the application, it will hide from the taskbar and run in the system tray. You can restore it by left-clicking the tray icon or using the right-click menu.

## Configuration File (`mappings.ini`)

The `mappings.ini` file stores your mappings. While it's managed by the application, you can view it to see how your configurations are saved. Each mapping is a section, like `[Mapping 1]`, with details about its type, trigger, output, and target window.

## License

This project is licensed under the MIT License. See the `LICENSE` file for details.

## Optional: improved suppression on Windows

S-Mapper can optionally use the `keyboard` Python package to perform low-level
suppression of mapped source keys on Windows. This prevents the original key
event from being delivered to the OS (so only your mapped target is seen), and
is more robust than attempting to delete characters with backspace.

Notes:
- Install the package in your app environment: `pip install keyboard` (the
    repository's virtual environment is used during development).
- The `keyboard` library exposes a global keyboard hook. On some systems, this
    may require additional privileges — see the `keyboard` project's docs if you
    run into permissions issues.
- If the `keyboard` package is not installed, S-Mapper will fall back to the
    original behavior (no suppression) so mappings still function, but the source
    key may still be delivered to the target application.

UI toggle:
- S-Mapper now includes a UI checkbox (shown when the `keyboard` package is
    available) that enables or disables the low-level suppression at runtime.
    When disabled, the app uses the older pynput-based path (no suppression).
    When enabled, the app installs per-source key hooks that suppress the
    original event only when the active window matches your mapping. If the
    mapping does not match the active window the original key is re-sent
    immediately so normal behavior continues.

Performance: cached active window title
- To further reduce latency, S-Mapper caches the active window title on the
    GUI thread and updates it periodically (100ms). The low-level keyboard hook
    Behavior with modifiers:
    - By default S-Mapper will not intercept a remapped key while any modifier
        key is held (Ctrl/Alt/Shift/Win/Meta). This avoids changing hotkey behavior
        like Ctrl+C becoming Ctrl+D when mapping `c -> d`. When a modifier is held
        the original keypress is re-sent immediately and no mapping is applied.
    reads this cached title under a small lock instead of calling `pygetwindow`
    on every keypress. This significantly reduces work inside the hook and
    lowers end-to-end latency for remapped keys.

Two recommended distribution variants
----------------------------------

If you plan to ship S-Mapper to users, you may want to produce two distinct
release variants so the app works well both for users who can run elevated and
for those who cannot or prefer a lower-privilege build:

- **Full build (Power-user / elevated)**
    - Includes the `keyboard` package (and any native/CTypes bits it needs) so
        low-level suppression can be used. This variant is intended for users who
        run with elevated privileges and want the cleanest suppression behavior.
    - When packaging as an MSIX, ensure the Appx manifest allows the binary to
        run with full trust (runFullTrust) and test behavior in AppContainer vs
        full-trust contexts. Many low-level hooks are blocked by UWP/AppContainer
        policies, so this package may need different installer/manifest settings.
    - Optionally recommend users run the packaged app "as administrator" if the
        keyboard hooks require administrative privileges on their setup.

- **Lite build (non-elevated / sandbox-safe)**
    - Does not include the `keyboard` package and avoids requiring elevated
        privileges. This variant still supports all mapping features via the
        high-level `pynput` listeners — however, suppression of original key
        events may not be perfect and some targeted behavior could be less
        consistent than the full build.
    - Use this when you need the app to run inside AppContainer or without
        administrative approval.

Packaging & CI notes
--------------------
- Produce two MSIX/installer artifacts (for example `S-Mapper-full.msix` and
    `S-Mapper-lite.msix`). The difference is the presence/absence of the
    `keyboard` package in the payload and any manifest flags controlling
    runFullTrust/elevation. Test both artifacts on a clean VM to ensure they
    behave as expected.
- When using PyInstaller to produce a single EXE packaging, ensure the
    environment used by PyInstaller includes or excludes `keyboard` depending on
    which build you want.
- Document for end users when elevation is required and how to choose the right
    build for their needs.
