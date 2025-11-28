# S-Mapper

S-Mapper is a versatile and user-friendly application designed for remapping keyboard and mouse inputs. It provides a graphical user interface to configure complex mappings, such as binding multi-click mouse events to specific keyboard shortcuts or remapping keyboard keys, with the ability to target these mappings to specific applications.

## Features

- **Mouse-to-Keyboard Mapping**: Map single or multi-click mouse button events to keyboard presses, including support for modifier keys like `Ctrl`, `Alt`, and `Shift`.
- **Keyboard-to-Keyboard Remapping**: Remap one keyboard key to another, including combinations with modifier keys.
- **Application-Specific Mappings**: All mappings can be configured to be active only when a specific window is in the foreground, allowing for application-specific hotkeys.
- **Clipboard IP Ping Monitor**: A utility that monitors the clipboard for IP addresses and automatically pings them when the active window matches a user-defined target. The results are displayed as a color-coded status indicator.
- **System Tray Integration**: The application can be minimized to the system tray for unobtrusive background operation.
- **Persistent Configuration**: Mappings are saved to a configuration file (`mappings.ini`) and are automatically reloaded on application startup.
- **Dark Mode UI**: A modern, dark-themed user interface for comfortable use in various lighting conditions.
- **Low-Level Suppression (Optional)**: For advanced users, S-Mapper can optionally use a low-level keyboard hook to suppress original key presses, preventing double inputs. This feature requires the "full" build with the `keyboard` package included.

## Usage

1. **Launch the application**: Run the `s_mapper.py` script or the compiled executable.
2. **Configure Mappings**:
   - **For Mouse Mappings**:
     - Select a mouse button from the dropdown list.
     - Enter the number of consecutive presses required to trigger the mapping.
     - Choose a target keyboard key and an optional modifier.
     - Specify the target window by either typing a partial name or selecting from a list of active windows.
   - **For Keyboard Mappings**:
     - Select a source keyboard key.
     - Choose a target keyboard key and an optional modifier.
     - Specify the target window.
3. **Add and Remove Mappings**:
   - Click "Add Mapping" to save the current configuration to the list.
   - Select a mapping from the list and click "Remove Selected" to delete it.
4. **Clipboard IP Ping Monitor**:
   - Enter a partial window title in the "Target Window Contains" field.
   - Click "Start Monitoring". When an IP address is copied to the clipboard while the target window is active, a ping will be sent automatically.
5. **System Tray**:
   - Minimizing the application window will send it to the system tray.
   - Right-click the tray icon to show the window or exit the application.

## Configuration

Mappings are stored in a `mappings.ini` file located in the user's local application data folder (`%LOCALAPPDATA%\S-Mapper` on Windows). This file can be manually edited, but it is recommended to use the in-app interface to manage mappings.

## Dependencies

- **PyQt6**: For the graphical user interface.
- **pynput**: For listening to mouse and keyboard events.
- **pygetwindow**: For identifying active windows.
- **keyboard** (optional): For low-level keyboard hooks and suppression.

## License

This project is licensed under the MIT License. See the `LICENSE` file for details.
