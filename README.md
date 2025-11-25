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
