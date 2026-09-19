# WAYMARK

**WAYMARK** is a personal media operating system for managing and tracking your anime and TV watching activity across services.

It brings supported services into one desktop application so you can search for media, track progress, manage ratings and reviews, and keep your personal library organized without switching between multiple websites.

## Current Release

**Version:** `1.0.0`
**Platform:** Windows x64
**Release format:** Portable ZIP

## Supported Services

### MyAnimeList

WAYMARK currently supports:

* Anime search
* Personal anime library
* Watch progress
* Status updates
* Ratings
* Reading existing anime information and account data

### Serializd

WAYMARK currently supports:

* TV/show search
* Show and season information
* Watch history
* Episode progress
* Season and episode ratings
* Series ratings
* Season, episode, and series reviews
* Review editing and deletion
* Personal library/history integration

## Features

* Unified media search
* Personal library
* Watch history
* Media details
* Guided watch workflow
* Episode and season progress tracking
* Ratings
* Reviews
* Personal profile
* First-run account setup
* Local application data
* Windows desktop application
* Portable release — no traditional installer required

## First-Run Setup

When WAYMARK is launched for the first time, it guides you through account setup.

You can connect your supported services and choose the name WAYMARK should use for your personal profile.

Your profile name can later be changed from the application settings.

Existing installations that already contain supported credentials can continue using them.

## Download

The latest Windows release is available from the GitHub Releases page.

Download:

**`WAYMARK-win32-x64-1.0.0.zip`**

Extract the ZIP and launch:

**`WAYMARK.exe`**

WAYMARK is distributed as a portable Windows application in this release.

## Privacy and Local Data

WAYMARK is designed as a personal application.

Local runtime data and credentials are kept outside the committed source tree and are intentionally excluded from Git version control.

Sensitive files such as:

* authentication credentials
* access tokens
* PKCE verification data
* local runtime data
* generated builds
* packaged release archives

are not intended to be committed to the repository.

WAYMARK also keeps user-specific application data in the local application data area on Windows.

## Running From Source

### Requirements

The development environment currently uses:

* Python 3.14+
* Node.js
* npm
* Electron
* PyInstaller

### Backend

The backend can be built using:

```powershell
powershell -ExecutionPolicy Bypass -File ".\packaging\build_backend.ps1"
```

The resulting backend executable is generated under:

```text
dist\WAYMARK-backend.exe
```

### Desktop Application

The Electron desktop application is located under:

```text
app\desktop
```

Install its dependencies:

```powershell
npm install
```

Run the development application with:

```powershell
npm start
```

Create the Windows portable ZIP with:

```powershell
npm run make
```

The generated ZIP is placed under:

```text
app\desktop\out\make\zip\win32\x64\
```

## Project Structure

```text
WAYMARK/
├── app/
│   ├── backend/
│   │   ├── core/
│   │   ├── services/
│   │   └── data/
│   ├── frontend/
│   └── desktop/
├── packaging/
├── tests/
├── build/
└── dist/
```

The application is organized into a Python backend, web-based frontend, and Electron desktop shell.

## Release Status

WAYMARK `1.0.0` represents the first packaged Windows release of the application.

The release has been tested as a standalone packaged application, including:

* Application startup
* Backend startup
* MAL integration
* Serializd integration
* Watch progress
* Ratings
* Reviews
* Personal profile
* Packaged frontend assets
* Application branding

## Project

GitHub repository:

**Lunthra/WAYMARK**

WAYMARK is a personal project and is currently distributed as a private GitHub repository.

---

**WAYMARK**
*Your media. Your progress. Your way.*
