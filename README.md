# WAYMARK

**WAYMARK** is a personal media operating system for managing and tracking your anime and TV watching activity across services.

It brings supported services into one desktop application so you can search for media, track progress, manage ratings and reviews, and keep your personal library organized without switching between multiple websites.

## Current Release

**Version:** `1.1.0`
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
* Existing anime and account information
* Artwork
* Improved authentication and account connection handling
* PKCE-based OAuth authentication
* Localhost OAuth callback
* Recovery from incorrect Client IDs
* Authentication retry handling

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
* Currently Watching
* Rewatch workflows
* Improved watched-state handling
* Improved artwork
* Faster library and diary retrieval

## Features

* Unified media search
* Personal library
* Watch history
* Media details
* Guided watch workflow
* Season and episode selection
* Episode and season progress tracking
* Currently Watching
* Continue Watching
* Rewatch workflow
* Ratings
* Series, season, and episode ratings where supported
* Reviews
* Existing rating lookup
* Personal profile
* Custom display name
* Custom profile picture
* Custom background image
* Persistent personalization
* Artwork-focused dashboard
* Featured and Continue Watching carousel
* First-run account setup
* Local application data
* Windows desktop application
* Portable release — no traditional installer required

## What's New in v1.1.0

WAYMARK `1.1.0` is a major update focused on making the application faster, more complete, and more personal.

### Personalization

* Custom display name
* Custom profile picture
* Custom background image
* Persistent personalization across application restarts
* Background artwork integrated into the WAYMARK interface
* Improved profile and personalization controls

### Home & Dashboard

* Expanded home dashboard
* Featured and Continue Watching carousel
* Improved artwork presentation
* Continue Watching integration with Serializd
* Currently Watching information combined across supported services
* Faster dashboard and library loading
* Improved loading states
* Protection against stale asynchronous requests

### Watch Workflow

* More complete Watch flow
* Improved season selection
* Improved episode selection
* Better progress tracking
* Improved currently-watching state handling
* Rewatch workflow
* Ability to decide whether a show should be marked as currently watching
* Improved completion and watched-state handling
* Reduced blocking while selecting seasons and episodes

### Ratings & Reviews

* Series, season, and episode rating support where supported
* Existing rating lookup
* Rating updates
* Rating changes synchronized with watched state
* Improved review workflow
* Improved rating and review operations
* Reduced interface blocking during rating lookups

### Performance

* Reduced Serializd library N+1 requests
* Improved concurrent page retrieval
* Indexed and cached diary data
* Reduced renderer blocking
* Improved asynchronous loading
* Improved artwork loading and normalization
* Reused frontend library state
* Improved currently-watching retrieval
* Reduced unnecessary backend and service requests

### Reliability

* Improved MAL authentication and recovery
* Improved Serializd currently-watching handling
* Improved completed-show/currently-watching behavior
* Improved authentication retry and cancellation
* Improved stale request handling
* Improved packaged resource loading
* Improved stability across Watch, Rating, Review, Library, and Dashboard workflows

## First-Run Setup

When WAYMARK is launched for the first time, it guides you through account setup.

You can connect your supported services and choose the name WAYMARK should use for your personal profile.

Your profile name can later be changed from the application settings.

You can also customize your profile picture and background from the personalization controls.

Existing installations that already contain supported credentials can continue using them.

## Download

The latest Windows release is available from the GitHub Releases page.

Download:

**`WAYMARK-win32-x64-1.1.0.zip`**

Extract the ZIP and launch:

**`WAYMARK.exe`**

WAYMARK is distributed as a portable Windows application.

## Upgrade from v1.0.0

If you are upgrading from WAYMARK `1.0.0`:

1. Download `WAYMARK-win32-x64-1.1.0.zip`.
2. Extract the new release.
3. Launch `WAYMARK.exe`.
4. Continue using your existing supported service accounts.

Personal application data and credentials are stored separately from the packaged release and are not included in the release ZIP.

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

Personal application data and credentials are **not included in the public release ZIP**.

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

### Backend Architecture

The desktop application uses the following general flow:

```text
Electron Renderer
        ↓
    preload.js
        ↓
     main.js
        ↓
Authenticated Local HTTP Bridge
        ↓
 bridge_server.py
        ↓
   desktop_api.py
        ↓
   waymark_core.py
        ↓
 ┌──────┼────────┐
 ↓      ↓        ↓
MAL  Serializd  TMDB
```

The Electron renderer is responsible for the user interface, while the Python backend handles application logic, service integrations, authentication, and local data operations.

## Release Status

WAYMARK `1.1.0` is the current packaged Windows release.

The release has been tested as a standalone packaged application, including:

* Application startup
* Backend startup
* MAL authentication
* MAL library and progress workflows
* Serializd integration
* Serializd library and diary retrieval
* Dashboard artwork
* Continue Watching
* Currently Watching
* Watch workflow
* Season and episode selection
* Rewatch workflow
* Watch progress
* Watched-state handling
* Ratings
* Reviews
* Existing rating lookup
* Personalization
* Profile picture
* Display name
* Background image
* Packaged frontend assets
* Application branding
* Application restart and persistence

## Release Artifact

The current release is distributed as:

**Windows x64 Portable ZIP**

Release asset:

**`WAYMARK-win32-x64-1.1.0.zip`**

SHA-256:

```text
5E318D39A584C096A9E90D56048421BB4C5BF8EBE79265FC7056323938B30BBF
```

## Project

GitHub repository:

**Lunthra/WAYMARK**

WAYMARK is a personal project and is currently distributed as a private GitHub repository.

---

**WAYMARK**
*Your media. Your progress. Your way.*
