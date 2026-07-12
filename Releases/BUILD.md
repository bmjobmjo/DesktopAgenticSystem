# OASIS Release Build Guide

This document explains how to build the non-Docker Windows and Ubuntu release packages for the OASIS web/API distribution.

## Output Location

Built release zips are written to:

- [Releases/windows](D:/Works/GenericAgent/DesktopAgenticSystem/Releases/windows)
- [Releases/ubuntu](D:/Works/GenericAgent/DesktopAgenticSystem/Releases/ubuntu)

The build script creates timestamped files named like:

- `oasis-release-pack-YYYYMMDD-HHMM.zip`

## Source Files Used

Main builder:

- [build_oasis_release_pack.ps1](D:/Works/GenericAgent/DesktopAgenticSystem/scripts/build_oasis_release_pack.ps1)

Release templates:

- [infra/release_pack](D:/Works/GenericAgent/DesktopAgenticSystem/infra/release_pack)

Frontend build source:

- [apps/ui_web](D:/Works/GenericAgent/DesktopAgenticSystem/apps/ui_web)

## Build Machine Prerequisites

On the machine where you build the releases, you need:

- Windows PowerShell
- Python available in `PATH`
- Node.js and npm available in `PATH`

Notes:

- The release builder runs the frontend production build before packaging.
- The target runtime does not require Node.js, but the build machine does.
- The Windows release pack now bundles a Python runtime so the target Windows machine does not need Python preinstalled.

## What The Builder Produces

Each release zip contains:

- API runtime
- DAS core runtime used by the API
- prebuilt web UI
- Windows and Ubuntu start scripts
- `instance-config.json`
- sanitized runtime settings

## Standard Build Flow

From repo root:

```powershell
cd D:\Works\GenericAgent\DesktopAgenticSystem
```

## Build Windows Release

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File .\scripts\build_oasis_release_pack.ps1 -OutputRoot .\Releases\windows
```

Result:

- a new zip in [Releases/windows](D:/Works/GenericAgent/DesktopAgenticSystem/Releases/windows)

## Build Ubuntu Release

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File .\scripts\build_oasis_release_pack.ps1 -OutputRoot .\Releases\ubuntu
```

Result:

- a new zip in [Releases/ubuntu](D:/Works/GenericAgent/DesktopAgenticSystem/Releases/ubuntu)

## Ubuntu Delivery Layout

For Ubuntu handoff, keep the installation package separate from demo or migration materials.

Recommended structure inside [Releases/ubuntu](D:/Works/GenericAgent/DesktopAgenticSystem/Releases/ubuntu):

- `oasis-release-ubuntu-...zip`
- `README.md`
- `companion/fictional-db/`
- `companion/scripts/`

Use that companion area for:

- fictional or demo SQLite databases
- one-off seed scripts
- migration helpers
- customer-specific setup notes

Do not mix those files into the extracted application folder unless the target instance explicitly needs them.

## Build Both

Run both commands one after the other:

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File .\scripts\build_oasis_release_pack.ps1 -OutputRoot .\Releases\windows
powershell -NoProfile -ExecutionPolicy Bypass -File .\scripts\build_oasis_release_pack.ps1 -OutputRoot .\Releases\ubuntu
```

## Skip Frontend Rebuild

If the UI `dist` is already current and you only want to repackage:

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File .\scripts\build_oasis_release_pack.ps1 -SkipUiBuild -OutputRoot .\Releases\windows
```

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File .\scripts\build_oasis_release_pack.ps1 -SkipUiBuild -OutputRoot .\Releases\ubuntu
```

Use this only if [apps/ui_web/dist](D:/Works/GenericAgent/DesktopAgenticSystem/apps/ui_web/dist) already reflects the latest frontend source.

## Important Packaging Behavior

The builder automatically:

- rebuilds the frontend unless `-SkipUiBuild` is used
- copies release-pack startup templates
- normalizes packaged `.sh` startup scripts to LF line endings for Linux
- generates `instance-config.json`
- generates `instance-config.example.json`
- generates sanitized `apps/das_core/settings/user_config.json`
- excludes local machine secrets, runtime DBs, model caches, logs, and WhatsApp auth state

## After Building

Check:

- latest zip exists in the expected platform folder
- corresponding platform README exists:
  - [windows/README.md](D:/Works/GenericAgent/DesktopAgenticSystem/Releases/windows/README.md)
  - [ubuntu/README.md](D:/Works/GenericAgent/DesktopAgenticSystem/Releases/ubuntu/README.md)

## Recommended Release Practice

For normal release handling:

- keep only the latest zip in each platform folder
- keep the platform `README.md`
- keep fictional/demo databases outside the main install zip
- keep helper scripts in a separate companion folder rather than the application root
- remove older zips when they are no longer needed

## Troubleshooting

If `npm` fails under PowerShell policy restrictions:

- use the existing build script as-is
- it already calls `npm.cmd` rather than `npm.ps1`

If the build machine has stale frontend cache state:

- rebuild without `-SkipUiBuild`

If you change release startup behavior:

- update [infra/release_pack](D:/Works/GenericAgent/DesktopAgenticSystem/infra/release_pack)
- rebuild both platform zips
