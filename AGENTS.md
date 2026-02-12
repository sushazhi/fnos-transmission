# AGENTS.md

This document provides guidelines for AI agents working on the transmission-fnos project.

## Project Overview

Transmission for Feiniu OS (fnOS) - a lightweight BitTorrent client package. This is a fnOS application package containing shell scripts for lifecycle management, JSON configuration files, and wizard definitions. The package is architecture-specific (ARM64 only).

## Build Commands

```bash
# Lint all code (shell scripts, JSON configs, manifest)
npm run lint

# Lint shell scripts only
npm run lint:shell

# Lint JSON configuration files only
npm run lint:json

# Lint manifest file format
npm run lint:manifest

# Build the fnOS application package
npm run package

# Clean build artifacts
npm run clean
```

## Code Style Guidelines

### Shell Scripts (Primary Language)

**Error Handling:**
- Always use `set -e` at the top of scripts
- Use `|| true` for commands that may fail but should not stop execution
- Capture and log errors to `${TRIM_TEMP_LOGFILE:-/tmp/<app>_error.log}`
- Always check exit codes: `if ! command; then ... fi`

**Formatting:**
- Indent with 4 spaces
- Shebang: `#!/bin/bash` for all shell scripts
- Use descriptive comments for functions and complex logic
- Comment in Chinese for user-facing messages (as this is a Chinese project)

**Naming Conventions:**
- Functions: `snake_case` (e.g., `start_service`, `stop_daemon`)
- Variables: `UPPER_CASE` for constants, `mixedCase` for local variables
- APP_NAME constant at top of scripts (e.g., `APP_NAME="transmission-daemon"`)
- PID files: `${APP_NAME}.pid`
- Log files: `${APP_NAME}.log`

**Structure:**
- Put `set -e` and error logging at top
- Define constants (paths, names) next
- Define functions
- Main logic with `case "$1" in ...)` for CLI-style scripts

**Example Template:**
```bash
#!/bin/bash
# cmd/script_name - Brief description

set -e

APP_NAME="transmission-daemon"
ERROR_LOG="${TRIM_TEMP_LOGFILE:-/tmp/${APP_NAME}_error.log}"
# ... more constants ...

function my_function() {
    # Implementation with error checking
    if ! command; then
        echo "Error: message" > "$ERROR_LOG"
        return 1
    fi
}

# ... more functions ...

case "$1" in
    start)
        my_function
        ;;
    *)
        echo "Usage: $0 {start|stop|restart|status}"
        exit 1
        ;;
esac
```

### JSON Configuration Files

**Location:** `config/privilege`, `config/resource`

**Formatting:**
- 4-space indentation
- Trailing commas NOT allowed
- Use double quotes for all keys and string values
- Validate with: `python3 -m json.tool <filename>`

**Structure:**
- `config/privilege`: Defines network ports and mount permissions
- `config/resource`: Defines data share mappings

**Example:**
```json
{
    "privilege": {
        "network": {
            "service": ["9091"]
        },
        "mount": {
            "read-write": ["/vol1/1000/downloads"],
            "read-only": []
        }
    }
}
```

### Manifest File

**Location:** `manifest` (key=value format, not JSON)

**Required Fields:**
```
appname = <lowercase_name>
version = <semantic_version>
display_name = <human_readable>
desc = <html_description>
platform = arm
source = thirdparty
maintainer = <upstream_project>
maintainer_url = <upstream_url>
distributor = <your_name>
distributor_url = <your_repo>
ctl_stop = true|false
service_port = <port>
```

**Validation:**
```bash
grep -E '^(appname|version|display_name|desc|platform|source) = ' manifest
```

### Wizard Files

**Location:** `wizard/install`, `wizard/uninstall`, `wizard/upgrade`

**Format:** JSON array of wizard steps

**Keys:**
- `stepTitle`: Step title (supports emoji)
- `items`: Array of UI elements
- `type`: Element type (tips, input, select, etc.)
- `helpText`: Help content (supports HTML tags like `<b>`, `<br>`, `<a>`)

**Example:**
```json
[
  {
    "stepTitle": "🚀 Welcome",
    "items": [
      {
        "type": "tips",
        "helpText": "✨ <b>Feature description</b>"
      }
    ]
  }
]
```

## fnOS Environment Variables

When working with fnOS app lifecycle scripts, be aware of these variables:

- `TRIM_APPDEST`: Application installation directory
- `TRIM_PKGVAR`: Package variable data directory (persistent data)
- `TRIM_PKGTMP`: Package temporary directory
- `TRIM_TEMP_LOGFILE`: Temporary log file path
- `TRIM_SERVICE_PORT`: Service port (from manifest)
- `wizard_data_action`: User preference from wizard (keep/delete)

## fnOS App Lifecycle

Standard lifecycle scripts in `cmd/`:

1. **install_init**: Pre-installation setup
2. **install_callback**: Post-installation tasks (set permissions, show info)
3. **uninstall_init**: Pre-uninstallation cleanup
4. **uninstall_callback**: Post-uninstallation cleanup
5. **upgrade_init**: Pre-upgrade backup/data handling
6. **upgrade_callback**: Post-upgrade restore
7. **main**: Main service lifecycle (start/stop/restart/status)

All lifecycle scripts should handle missing environment variables gracefully and provide helpful error messages.

## Import/Dependency Management

This project has no external npm dependencies. The binary (`transmission-daemon`) is bundled from third-party sources.

## Testing Notes

- No unit tests currently configured
- Manual testing via fnOS app center
- Linting validates shell script syntax and JSON validity
- Test lifecycle commands manually:
  ```bash
  ./cmd/main start
  ./cmd/main stop
  ./cmd/main status
  ./cmd/main restart
  ```

## Important File Locations

```
/
├── cmd/                 # Shell scripts for app lifecycle
│   ├── main            # Primary service control script
│   ├── install_init    # Pre-install setup
│   ├── install_callback # Post-install tasks
│   ├── upgrade_init    # Pre-upgrade backup
│   ├── upgrade_callback # Post-upgrade restore
│   ├── uninstall_init  # Pre-uninstall cleanup
│   └── uninstall_callback # Post-uninstall cleanup
├── config/             # JSON configuration
│   ├── privilege       # Network/mount permissions
│   └── resource        # Data share mappings
├── wizard/             # Installation wizard UI
│   ├── install         # Installation wizard steps
│   ├── upgrade         # Upgrade wizard steps
│   └── uninstall       # Uninstall wizard steps
├── manifest            # App metadata (key=value)
└── package.json        # Build scripts and metadata
```

## Common Tasks

### Adding a New Lifecycle Script
1. Create script in `cmd/` with `#!/bin/bash` and `set -e`
2. Follow naming convention: `{action}_init` or `{action}_callback`
3. Use error logging: `ERROR_LOG="${TRIM_TEMP_LOGFILE:-/tmp/${APP_NAME}_error.log}"`
4. Test with lint commands
5. Update wizard if UI needed

### Modifying Configuration
1. Validate JSON with `python3 -m json.tool`
2. Run `npm run lint:json` to verify
3. Update manifest/service_port if changing ports

### Updating Version
1. Update `version` in `manifest`
2. Update `version` in `package.json`
3. Update `README.md` if displayed version exists
4. Run `npm run lint` to verify all validations pass
