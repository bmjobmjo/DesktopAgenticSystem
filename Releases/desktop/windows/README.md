# OASIS Desktop App for Windows

This folder contains the portable Windows desktop build of OASIS.

## Package

- `oasis-desktop-<version>.zip`
- extracted folder: `oasis-desktop-<version>`

## Install

This build does not use an installer.

1. Copy `oasis-desktop-<version>.zip` to the target Windows machine.
2. Extract the zip to a folder of your choice.
3. Open the extracted `oasis-desktop-<version>` folder.
4. Run `oasis-desktop-<version>.exe`

## Prerequisites

- Windows 10 or newer
- No separate Python installation required
- No Node.js installation required
- No Docker installation required

## Runtime Data

- The desktop build should use a local database at `data\office_automation.db`
- Generated files should be written under `storage\files`
- Runtime logs should be written under `runtime\logs`
- WhatsApp folder bridge exchange should use `storage\whatsapp_bridge_exchange`

## Notes

- This is a portable packaged desktop app.
- Python does not need to be installed separately for this desktop build.
- The app runtime is bundled inside the `_internal` folder.
- For a clean deployment, the build must ship a sanitized `user_config.json` and a local seed database.
- If Windows SmartScreen warns on first run, use `More info` and then `Run anyway` only if the file came from your trusted release process.

## Main Executable

- `oasis-desktop-<version>\oasis-desktop-<version>.exe`
