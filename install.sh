#!/usr/bin/env bash
set -euo pipefail

# ─────────────────────────────────────────────────────────────
# Silicon Stemcell – Universal Installer (Mac / Linux)
# curl -fsSL https://raw.githubusercontent.com/unlikefraction/silicon-stemcell/main/install.sh | bash
# ─────────────────────────────────────────────────────────────

REPO_URL="https://github.com/unlikefraction/silicon-stemcell.git"
REPO_ZIP="https://github.com/unlikefraction/silicon-stemcell/archive/refs/heads/main.zip"
REGISTRY_DIR="$HOME/.silicon"
REGISTRY_FILE="$REGISTRY_DIR/registry.json"
BIN_DIR="$REGISTRY_DIR/bin"
CLI_SCRIPT="$BIN_DIR/silicon"

# ── Colors & helpers ──────────────────────────────────────────

RED='\033[0;31m'; GREEN='\033[0;32m'; YELLOW='\033[1;33m'
BLUE='\033[0;34m'; CYAN='\033[0;36m'; BOLD='\033[1m'
DIM='\033[2m'; RESET='\033[0m'

info()    { printf "${BLUE}→${RESET} %s\n" "$*"; }
success() { printf "${GREEN}✓${RESET} %s\n" "$*"; }
warn()    { printf "${YELLOW}⚠${RESET} %s\n" "$*"; }
error()   { printf "${RED}✗${RESET} %s\n" "$*"; }
header()  { printf "\n${BOLD}${CYAN}── %s ──${RESET}\n\n" "$*"; }
ask()     { printf "${BOLD}? %s${RESET} " "$1"; }

confirm() {
    ask "$1 [Y/n]"
    read -r ans </dev/tty
    case "$ans" in
        [nN]*) return 1 ;;
        *) return 0 ;;
    esac
}

# If piped (curl | bash), we need /dev/tty for user input
read_input() {
    local prompt="$1" default="${2:-}"
    if [ -n "$default" ]; then
        printf "${BOLD}? %s [%s]:${RESET} " "$prompt" "$default" >&2
    else
        printf "${BOLD}? %s:${RESET} " "$prompt" >&2
    fi
    read -r val </dev/tty
    if [ -z "$val" ] && [ -n "$default" ]; then
        val="$default"
    fi
    echo "$val"
}

read_secret() {
    local prompt="$1"
    printf "${BOLD}? %s:${RESET} " "$prompt" >&2
    local val=""
    local char=""
    while IFS= read -r -s -n1 char </dev/tty; do
        if [[ -z "$char" ]]; then
            break
        elif [[ "$char" == $'\x7f' ]] || [[ "$char" == $'\b' ]]; then
            if [[ -n "$val" ]]; then
                val="${val%?}"
                printf "\b \b" >&2
            fi
        else
            val="${val}${char}"
            printf "*" >&2
        fi
    done
    printf "\n" >&2
    echo "$val"
}

# ── Banner ────────────────────────────────────────────────────

clear 2>/dev/null || true
printf "${BOLD}${CYAN}"
cat << 'BANNER'

  ███████╗██╗██╗     ██╗ ██████╗ ██████╗ ███╗   ██╗
  ██╔════╝██║██║     ██║██╔════╝██╔═══██╗████╗  ██║
  ███████╗██║██║     ██║██║     ██║   ██║██╔██╗ ██║
  ╚════██║██║██║     ██║██║     ██║   ██║██║╚██╗██║
  ███████║██║███████╗██║╚██████╗╚██████╔╝██║ ╚████║
  ╚══════╝╚═╝╚══════╝╚═╝ ╚═════╝ ╚═════╝ ╚═╝  ╚═══╝
                                        stemcell

BANNER
printf "${RESET}"
echo ""
info "Universal installer for Silicon – your autonomous AI agent"
echo ""

# ═════════════════════════════════════════════════════════════
# STEP 1: System checks
# ═════════════════════════════════════════════════════════════

header "Step 1 · System Checks"

# Detect OS
OS="unknown"
case "$(uname -s)" in
    Darwin*) OS="mac" ;;
    Linux*)  OS="linux" ;;
    *)       OS="unknown" ;;
esac

if [ "$OS" = "unknown" ]; then
    error "Unsupported operating system: $(uname -s)"
    error "This installer supports macOS and Linux. For Windows, use install.ps1"
    exit 1
fi

success "Operating system: $(uname -s) ($(uname -m))"

# Check sudo/admin
if [ "$EUID" -eq 0 ] 2>/dev/null || [ "$(id -u)" -eq 0 ]; then
    warn "Running as root. Some tools will be installed system-wide."
else
    info "Running as normal user. You may be prompted for sudo if needed."
fi

# Check disk space (need at least 500MB)
if command -v df &>/dev/null; then
    if [ "$OS" = "mac" ]; then
        avail_kb=$(df -k "$HOME" | tail -1 | awk '{print $4}')
    else
        avail_kb=$(df -k "$HOME" | tail -1 | awk '{print $4}')
    fi
    avail_mb=$((avail_kb / 1024))
    if [ "$avail_mb" -lt 500 ]; then
        error "Low disk space: ${avail_mb}MB available. Need at least 500MB."
        exit 1
    fi
    success "Disk space: ${avail_mb}MB available"
fi

# ═════════════════════════════════════════════════════════════
# STEP 2: Prerequisites
# ═════════════════════════════════════════════════════════════

header "Step 2 · Prerequisites"

# ── Python 3.9+ ───────────────────────────────────────────────

install_python() {
    if [ "$OS" = "mac" ]; then
        if command -v brew &>/dev/null; then
            info "Installing Python via Homebrew..."
            brew install python3
        else
            error "Homebrew not found. Install Python 3.9+ manually from https://python.org/downloads"
            error "Or install Homebrew first: /bin/bash -c \"\$(curl -fsSL https://raw.githubusercontent.com/Homebrew/install/HEAD/install.sh)\""
            exit 1
        fi
    else
        if command -v apt-get &>/dev/null; then
            info "Installing Python via apt..."
            sudo apt-get update -qq && sudo apt-get install -y python3 python3-pip python3-venv
        elif command -v dnf &>/dev/null; then
            info "Installing Python via dnf..."
            sudo dnf install -y python3 python3-pip
        elif command -v yum &>/dev/null; then
            info "Installing Python via yum..."
            sudo yum install -y python3 python3-pip
        elif command -v pacman &>/dev/null; then
            info "Installing Python via pacman..."
            sudo pacman -S --noconfirm python python-pip
        else
            error "No supported package manager found. Install Python 3.9+ manually."
            exit 1
        fi
    fi
}

PYTHON_CMD=""
for cmd in python3 python; do
    if command -v "$cmd" &>/dev/null; then
        ver=$("$cmd" --version 2>&1 | grep -oE '[0-9]+\.[0-9]+' | head -1)
        major=$(echo "$ver" | cut -d. -f1)
        minor=$(echo "$ver" | cut -d. -f2)
        if [ "$major" -ge 3 ] && [ "$minor" -ge 9 ]; then
            PYTHON_CMD="$cmd"
            break
        fi
    fi
done

if [ -n "$PYTHON_CMD" ]; then
    success "Python: $($PYTHON_CMD --version) ($PYTHON_CMD)"
else
    warn "Python 3.9+ not found"
    if confirm "Install Python?"; then
        install_python
        # Re-check
        for cmd in python3 python; do
            if command -v "$cmd" &>/dev/null; then
                ver=$("$cmd" --version 2>&1 | grep -oE '[0-9]+\.[0-9]+' | head -1)
                major=$(echo "$ver" | cut -d. -f1)
                minor=$(echo "$ver" | cut -d. -f2)
                if [ "$major" -ge 3 ] && [ "$minor" -ge 9 ]; then
                    PYTHON_CMD="$cmd"
                    break
                fi
            fi
        done
        if [ -z "$PYTHON_CMD" ]; then
            error "Python installation failed. Install Python 3.9+ manually and re-run."
            exit 1
        fi
        success "Python installed: $($PYTHON_CMD --version)"
    else
        error "Python 3.9+ is required. Aborting."
        exit 1
    fi
fi

# ── Node.js / npm ─────────────────────────────────────────────

install_node() {
    if [ "$OS" = "mac" ]; then
        if command -v brew &>/dev/null; then
            info "Installing Node.js via Homebrew..."
            brew install node
        else
            error "Install Node.js from https://nodejs.org or install Homebrew first."
            exit 1
        fi
    else
        if command -v apt-get &>/dev/null; then
            info "Installing Node.js via apt..."
            # Use NodeSource for a recent version
            if ! command -v curl &>/dev/null; then
                sudo apt-get install -y curl
            fi
            curl -fsSL https://deb.nodesource.com/setup_lts.x | sudo -E bash -
            sudo apt-get install -y nodejs
        elif command -v dnf &>/dev/null; then
            sudo dnf install -y nodejs npm
        elif command -v yum &>/dev/null; then
            sudo yum install -y nodejs npm
        elif command -v pacman &>/dev/null; then
            sudo pacman -S --noconfirm nodejs npm
        else
            error "Install Node.js from https://nodejs.org manually."
            exit 1
        fi
    fi
}

if command -v node &>/dev/null && command -v npm &>/dev/null; then
    success "Node.js: $(node --version)"
else
    warn "Node.js / npm not found (needed for Claude Code CLI & silicon-browser)"
    if confirm "Install Node.js?"; then
        install_node
        if command -v node &>/dev/null; then
            success "Node.js installed: $(node --version)"
        else
            error "Node.js installation failed. Install from https://nodejs.org and re-run."
            exit 1
        fi
    else
        error "Node.js is required for Claude Code CLI. Aborting."
        exit 1
    fi
fi

# ── Claude Code CLI ───────────────────────────────────────────

if command -v claude &>/dev/null; then
    success "Claude Code CLI: installed"
else
    warn "Claude Code CLI not found"
    if confirm "Install Claude Code CLI via npm?"; then
        info "Installing @anthropic-ai/claude-code globally..."
        npm install -g @anthropic-ai/claude-code
        if command -v claude &>/dev/null; then
            success "Claude Code CLI installed"
        else
            error "Claude Code CLI installation failed."
            error "Try manually: npm install -g @anthropic-ai/claude-code"
            exit 1
        fi
    else
        error "Claude Code CLI is required. Aborting."
        exit 1
    fi
fi

# ── silicon-browser ───────────────────────────────────────────

if command -v silicon-browser &>/dev/null; then
    success "silicon-browser: installed"
else
    warn "silicon-browser not found"
    if confirm "Install silicon-browser via npm?"; then
        info "Installing silicon-browser globally..."
        npm install -g silicon-browser
        if command -v silicon-browser &>/dev/null; then
            success "silicon-browser installed"
        else
            warn "silicon-browser install may have failed. Browser workers may not work."
            warn "Try manually: npm install -g silicon-browser"
        fi
    else
        warn "Skipping silicon-browser. Browser workers will not be available."
    fi
fi

# ═════════════════════════════════════════════════════════════
# STEP 3: Download the repo
# ═════════════════════════════════════════════════════════════

header "Step 3 · Download Silicon"

DEFAULT_DIR="$(pwd)/silicon"
printf "  Silicon will be installed to: ${BOLD}%s${RESET}\n\n" "$DEFAULT_DIR"
printf "  ${BOLD}1)${RESET} Yes, install here\n"
printf "  ${BOLD}2)${RESET} Choose a different directory\n"
printf "  ${BOLD}3)${RESET} Don't install\n\n"
ask "Your choice [1]:"
read -r dir_choice </dev/tty
dir_choice="${dir_choice:-1}"

case "$dir_choice" in
    1)
        INSTALL_DIR="$DEFAULT_DIR"
        ;;
    2)
        INSTALL_DIR=$(read_input "Install directory" "$HOME/silicon")
        INSTALL_DIR="${INSTALL_DIR/#\~/$HOME}"
        ;;
    3)
        error "Aborting."
        exit 0
        ;;
    *)
        INSTALL_DIR="$DEFAULT_DIR"
        ;;
esac

printf "\n${DIM}  Name this instance (useful if you run multiple silicons on this machine).${RESET}\n" >&2
INSTANCE_NAME=$(read_input "Instance name" "silicon")

SKIP_CLONE=false
if [ -d "$INSTALL_DIR" ]; then
    if [ -f "$INSTALL_DIR/main.py" ] && [ -f "$INSTALL_DIR/config.py" ]; then
        warn "Silicon already exists at $INSTALL_DIR"
        if confirm "Use existing installation? (No will overwrite)"; then
            success "Using existing installation at $INSTALL_DIR"
            SKIP_CLONE=true
        else
            warn "Backing up existing to ${INSTALL_DIR}.bak.$(date +%s)"
            mv "$INSTALL_DIR" "${INSTALL_DIR}.bak.$(date +%s)"
        fi
    else
        warn "Directory $INSTALL_DIR exists but doesn't look like a silicon installation."
        if ! confirm "Continue and clone into it?"; then
            error "Aborting."
            exit 1
        fi
    fi
fi

if [ "$SKIP_CLONE" = "false" ]; then
    info "Downloading Silicon to $INSTALL_DIR..."
    if command -v git &>/dev/null; then
        info "Cloning via git..."
        git clone "$REPO_URL" "$INSTALL_DIR"
        success "Cloned to $INSTALL_DIR"
    elif command -v curl &>/dev/null; then
        info "git not found. Downloading ZIP via curl..."
        TMP_ZIP=$(mktemp /tmp/silicon-XXXXXX.zip)
        TMP_DIR=$(mktemp -d /tmp/silicon-extract-XXXXXX)
        curl -fsSL "$REPO_ZIP" -o "$TMP_ZIP"
        unzip -q "$TMP_ZIP" -d "$TMP_DIR"
        mv "$TMP_DIR"/silicon-stemcell-main "$INSTALL_DIR"
        rm -rf "$TMP_ZIP" "$TMP_DIR"
        success "Downloaded and extracted to $INSTALL_DIR"
    elif command -v wget &>/dev/null; then
        info "git not found. Downloading ZIP via wget..."
        TMP_ZIP=$(mktemp /tmp/silicon-XXXXXX.zip)
        TMP_DIR=$(mktemp -d /tmp/silicon-extract-XXXXXX)
        wget -q "$REPO_ZIP" -O "$TMP_ZIP"
        unzip -q "$TMP_ZIP" -d "$TMP_DIR"
        mv "$TMP_DIR"/silicon-stemcell-main "$INSTALL_DIR"
        rm -rf "$TMP_ZIP" "$TMP_DIR"
        success "Downloaded and extracted to $INSTALL_DIR"
    else
        error "No git, curl, or wget found. Cannot download Silicon."
        exit 1
    fi
fi

# ── pip packages ──────────────────────────────────────────────

if [ -f "$INSTALL_DIR/requirements.txt" ]; then
    info "Installing Python dependencies..."
    "$PYTHON_CMD" -m pip install -r "$INSTALL_DIR/requirements.txt" --quiet 2>/dev/null || \
        "$PYTHON_CMD" -m pip install -r "$INSTALL_DIR/requirements.txt" --quiet --user
    success "Python dependencies installed"
fi

# ═════════════════════════════════════════════════════════════
# STEP 4: Configure
# ═════════════════════════════════════════════════════════════

header "Step 4 · Configure"

ENV_FILE="$INSTALL_DIR/env.py"

# Check if already configured
ALREADY_CONFIGURED=false
if [ -f "$ENV_FILE" ]; then
    if grep -q 'TELEGRAM_BOT_TOKEN = ""' "$ENV_FILE" 2>/dev/null || grep -q "TELEGRAM_BOT_TOKEN = ''" "$ENV_FILE" 2>/dev/null; then
        ALREADY_CONFIGURED=false
    else
        token_val=$(grep 'TELEGRAM_BOT_TOKEN' "$ENV_FILE" 2>/dev/null | head -1)
        if [ -n "$token_val" ] && ! echo "$token_val" | grep -q '""'; then
            ALREADY_CONFIGURED=true
        fi
    fi
fi

if [ "$ALREADY_CONFIGURED" = "true" ]; then
    success "Already configured (env.py has tokens)"
    if confirm "Reconfigure?"; then
        ALREADY_CONFIGURED=false
    fi
fi

if [ "$ALREADY_CONFIGURED" = "false" ]; then
    echo ""
    info "You need a Telegram bot token to use Silicon."
    printf "${DIM}  1. Open Telegram and search for @BotFather${RESET}\n"
    printf "${DIM}  2. Send /newbot and follow the prompts${RESET}\n"
    printf "${DIM}  3. Copy the token BotFather gives you${RESET}\n"
    echo ""

    TELEGRAM_TOKEN=$(read_secret "Telegram bot token")
    if [ -z "$TELEGRAM_TOKEN" ]; then
        error "Telegram bot token is required."
        exit 1
    fi

    echo ""
    info "OpenAI API key (for voice transcription & TTS)."
    info "Press Enter to skip – voice features will be disabled."
    OPENAI_KEY=$(read_secret "OpenAI API key (optional)")

    cat > "$ENV_FILE" << ENVEOF
TELEGRAM_BOT_TOKEN = "$TELEGRAM_TOKEN"
OPENAI_API_KEY = "$OPENAI_KEY"
ENVEOF

    success "Configuration saved to $ENV_FILE"
fi

# ═════════════════════════════════════════════════════════════
# STEP 5: Silicon registry
# ═════════════════════════════════════════════════════════════

header "Step 5 · Registry"

mkdir -p "$REGISTRY_DIR"
mkdir -p "$BIN_DIR"

# Initialize registry if it doesn't exist
if [ ! -f "$REGISTRY_FILE" ]; then
    echo '{"installations": []}' > "$REGISTRY_FILE"
    success "Created registry at $REGISTRY_FILE"
fi

# Check if this installation is already registered
ABS_INSTALL_DIR=$(cd "$INSTALL_DIR" 2>/dev/null && pwd || echo "$INSTALL_DIR")
ALREADY_REGISTERED=false

if command -v "$PYTHON_CMD" &>/dev/null; then
    ALREADY_REGISTERED=$("$PYTHON_CMD" -c "
import json, sys
with open('$REGISTRY_FILE') as f:
    reg = json.load(f)
for inst in reg.get('installations', []):
    if inst.get('path') == '$ABS_INSTALL_DIR' or inst.get('name') == '$INSTANCE_NAME':
        print('true')
        sys.exit(0)
print('false')
" 2>/dev/null || echo "false")
fi

if [ "$ALREADY_REGISTERED" = "true" ]; then
    success "Instance '$INSTANCE_NAME' already registered"
else
    # Add to registry
    "$PYTHON_CMD" -c "
import json, os
from datetime import datetime
reg_path = '$REGISTRY_FILE'
with open(reg_path) as f:
    reg = json.load(f)
reg['installations'].append({
    'name': '$INSTANCE_NAME',
    'path': '$ABS_INSTALL_DIR',
    'created_at': datetime.now().isoformat(),
    'pid_file': os.path.join('$ABS_INSTALL_DIR', '.silicon.pid')
})
with open(reg_path, 'w') as f:
    json.dump(reg, f, indent=2)
"
    success "Registered '$INSTANCE_NAME' at $ABS_INSTALL_DIR"
fi

# ═════════════════════════════════════════════════════════════
# STEP 6: Create CLI
# ═════════════════════════════════════════════════════════════

header "Step 6 · CLI Setup"

cat > "$CLI_SCRIPT" << 'CLIEOF'
#!/usr/bin/env bash
# Silicon CLI – manages silicon installations

REGISTRY_DIR="$HOME/.silicon"
REGISTRY_FILE="$REGISTRY_DIR/registry.json"

RED='\033[0;31m'; GREEN='\033[0;32m'; YELLOW='\033[1;33m'
BLUE='\033[0;34m'; CYAN='\033[0;36m'; BOLD='\033[1m'
DIM='\033[2m'; RESET='\033[0m'

error() { printf "${RED}✗${RESET} %s\n" "$*"; }
info()  { printf "${BLUE}→${RESET} %s\n" "$*"; }
success() { printf "${GREEN}✓${RESET} %s\n" "$*"; }
warn()  { printf "${YELLOW}⚠${RESET} %s\n" "$*"; }

# Find python
PYTHON_CMD=""
for cmd in python3 python; do
    if command -v "$cmd" &>/dev/null; then
        PYTHON_CMD="$cmd"
        break
    fi
done

if [ -z "$PYTHON_CMD" ]; then
    error "Python not found"
    exit 1
fi

# ── Registry helpers ──────────────────────────────────────────

get_installations() {
    "$PYTHON_CMD" -c "
import json
with open('$REGISTRY_FILE') as f:
    reg = json.load(f)
for i, inst in enumerate(reg.get('installations', [])):
    print(f\"{i}|{inst['name']}|{inst['path']}|{inst.get('pid_file', '')}\")
" 2>/dev/null
}

get_count() {
    "$PYTHON_CMD" -c "
import json
with open('$REGISTRY_FILE') as f:
    reg = json.load(f)
print(len(reg.get('installations', [])))
" 2>/dev/null
}

is_running() {
    local pid_file="$1"
    if [ -f "$pid_file" ]; then
        local pid
        pid=$(cat "$pid_file" 2>/dev/null)
        if [ -n "$pid" ] && kill -0 "$pid" 2>/dev/null; then
            echo "running"
            return 0
        fi
    fi
    echo "stopped"
    return 1
}

get_pid() {
    local pid_file="$1"
    if [ -f "$pid_file" ]; then
        cat "$pid_file" 2>/dev/null
    fi
}

# Find installation by current directory or name
find_installation() {
    local search="${1:-}"
    local cwd
    cwd=$(pwd)

    while IFS='|' read -r idx name path pid_file; do
        if [ -n "$search" ]; then
            if [ "$name" = "$search" ]; then
                echo "$idx|$name|$path|$pid_file"
                return 0
            fi
        else
            # Check if cwd is inside this installation
            case "$cwd" in
                "$path"*) echo "$idx|$name|$path|$pid_file"; return 0 ;;
            esac
        fi
    done <<< "$(get_installations)"
    return 1
}

# Pick an installation (interactive)
pick_installation() {
    local count
    count=$(get_count)
    if [ -z "$count" ] || [ "$count" -eq 0 ]; then
        error "No silicon installations found. Run 'silicon install' first." >&2
        exit 1
    elif [ "$count" -eq 1 ]; then
        get_installations | head -1
        return 0
    fi

    printf "\n${BOLD}Select a silicon instance:${RESET}\n\n" >&2
    while IFS='|' read -r idx name path pid_file; do
        local status
        status=$(is_running "$pid_file")
        local status_color
        if [ "$status" = "running" ]; then
            status_color="${GREEN}● running${RESET}"
        else
            status_color="${DIM}○ stopped${RESET}"
        fi
        printf "  ${BOLD}%d)${RESET} %-20s %b  ${DIM}%s${RESET}\n" "$((idx + 1))" "$name" "$status_color" "$path" >&2
    done <<< "$(get_installations)"

    echo "" >&2
    printf "${BOLD}? Choice [1]:${RESET} " >&2
    read -r choice
    choice="${choice:-1}"
    local target_idx=$((choice - 1))

    while IFS='|' read -r idx name path pid_file; do
        if [ "$idx" -eq "$target_idx" ]; then
            echo "$idx|$name|$path|$pid_file"
            return 0
        fi
    done <<< "$(get_installations)"

    error "Invalid choice"
    exit 1
}

# ── Commands ──────────────────────────────────────────────────

cmd_list() {
    local count
    count=$(get_count)
    if [ "$count" -eq 0 ]; then
        info "No silicon installations found."
        info "Run 'silicon install' to set up a new instance."
        return
    fi

    printf "\n${BOLD}${CYAN}Silicon Installations${RESET}\n\n"
    printf "  ${DIM}%-4s %-20s %-10s %s${RESET}\n" "#" "NAME" "STATUS" "PATH"
    printf "  ${DIM}%-4s %-20s %-10s %s${RESET}\n" "---" "----" "------" "----"

    while IFS='|' read -r idx name path pid_file; do
        local status status_display pid_info
        status=$(is_running "$pid_file")
        if [ "$status" = "running" ]; then
            local pid
            pid=$(get_pid "$pid_file")
            status_display="${GREEN}● running${RESET}"
            pid_info=" ${DIM}(PID $pid)${RESET}"
        else
            status_display="${DIM}○ stopped${RESET}"
            pid_info=""
        fi
        printf "  %-4s %-20s %b%b  ${DIM}%s${RESET}\n" "$((idx + 1))" "$name" "$status_display" "$pid_info" "$path"
    done <<< "$(get_installations)"
    echo ""
}

cmd_start() {
    local target="$1"
    local inst

    if [ -n "$target" ]; then
        inst=$(find_installation "$target") || { error "Silicon '$target' not found"; exit 1; }
    else
        inst=$(find_installation) || inst=$(pick_installation)
    fi

    IFS='|' read -r idx name path pid_file <<< "$inst"

    if [ "$(is_running "$pid_file")" = "running" ]; then
        local pid
        pid=$(get_pid "$pid_file")
        warn "'$name' is already running (PID $pid)"
        return
    fi

    info "Starting '$name'..."
    cd "$path"

    # Start in background
    nohup "$PYTHON_CMD" -u main.py > "$path/.silicon.log" 2>&1 &
    local new_pid=$!
    echo "$new_pid" > "$pid_file"

    # Brief wait to check it didn't crash immediately
    sleep 1
    if kill -0 "$new_pid" 2>/dev/null; then
        success "'$name' started (PID $new_pid)"
        info "Logs: $path/.silicon.log"
    else
        error "'$name' failed to start. Check logs: $path/.silicon.log"
        rm -f "$pid_file"
    fi
}

cmd_stop() {
    local target="$1"
    local inst

    if [ -n "$target" ]; then
        inst=$(find_installation "$target") || { error "Silicon '$target' not found"; exit 1; }
    else
        inst=$(find_installation) || inst=$(pick_installation)
    fi

    IFS='|' read -r idx name path pid_file <<< "$inst"

    if [ "$(is_running "$pid_file")" != "running" ]; then
        warn "'$name' is not running"
        rm -f "$pid_file"
        return
    fi

    local pid
    pid=$(get_pid "$pid_file")
    info "Stopping '$name' (PID $pid)..."
    kill "$pid" 2>/dev/null

    # Wait for graceful shutdown
    for i in $(seq 1 10); do
        if ! kill -0 "$pid" 2>/dev/null; then
            break
        fi
        sleep 0.5
    done

    # Force kill if still running
    if kill -0 "$pid" 2>/dev/null; then
        warn "Force stopping..."
        kill -9 "$pid" 2>/dev/null
    fi

    rm -f "$pid_file"
    success "'$name' stopped"
}

cmd_status() {
    local target="$1"

    if [ -n "$target" ]; then
        local inst
        inst=$(find_installation "$target") || { cmd_list; return; }
        IFS='|' read -r idx name path pid_file <<< "$inst"
        local status
        status=$(is_running "$pid_file")
        if [ "$status" = "running" ]; then
            local pid
            pid=$(get_pid "$pid_file")
            printf "\n${BOLD}$name${RESET} ${GREEN}● running${RESET} (PID $pid)\n"
            printf "${DIM}  Path: $path${RESET}\n\n"
        else
            printf "\n${BOLD}$name${RESET} ${DIM}○ stopped${RESET}\n"
            printf "${DIM}  Path: $path${RESET}\n\n"
        fi
    else
        local inst
        inst=$(find_installation 2>/dev/null) && {
            IFS='|' read -r idx name path pid_file <<< "$inst"
            local status
            status=$(is_running "$pid_file")
            if [ "$status" = "running" ]; then
                local pid
                pid=$(get_pid "$pid_file")
                printf "\n${BOLD}$name${RESET} ${GREEN}● running${RESET} (PID $pid)\n"
                printf "${DIM}  Path: $path${RESET}\n\n"
            else
                printf "\n${BOLD}$name${RESET} ${DIM}○ stopped${RESET}\n"
                printf "${DIM}  Path: $path${RESET}\n\n"
            fi
        } || cmd_list
    fi
}

cmd_browser() {
    local target="$1"
    local inst

    if [ -n "$target" ]; then
        inst=$(find_installation "$target") || { error "Silicon '$target' not found"; exit 1; }
    else
        inst=$(find_installation) || inst=$(pick_installation)
    fi

    IFS='|' read -r idx name path pid_file <<< "$inst"

    info "Opening browser for '$name'..."
    cd "$path"
    "$PYTHON_CMD" main.py browser
}

cmd_update() {
    # Update the silicon CLI script (not the instances themselves)
    info "Updating silicon CLI..."
    local script_url="https://raw.githubusercontent.com/unlikefraction/silicon-stemcell/main/install.sh"
    local tmp_script
    tmp_script=$(mktemp /tmp/silicon-update-XXXXXX.sh)

    if command -v curl &>/dev/null; then
        curl -fsSL "$script_url" -o "$tmp_script"
    elif command -v wget &>/dev/null; then
        wget -q "$script_url" -O "$tmp_script"
    else
        error "Need curl or wget to update"
        rm -f "$tmp_script"
        exit 1
    fi

    # Extract just the CLI script portion (between CLIEOF markers)
    local cli_path="$HOME/.silicon/bin/silicon"
    local new_cli
    new_cli=$(mktemp /tmp/silicon-cli-XXXXXX)

    sed -n "/^cat > .*CLI_SCRIPT.*<< 'CLIEOF'/,/^CLIEOF$/p" "$tmp_script" | sed '1d;$d' > "$new_cli"

    if [ -s "$new_cli" ]; then
        cp "$new_cli" "$cli_path"
        chmod +x "$cli_path"
        success "CLI updated to latest version"
    else
        error "Failed to extract CLI from installer. Try: silicon install"
    fi

    rm -f "$tmp_script" "$new_cli"
}

cmd_debug() {
    local target="$1"
    local inst

    if [ -n "$target" ]; then
        inst=$(find_installation "$target") || { error "Silicon '$target' not found"; exit 1; }
    else
        inst=$(find_installation) || inst=$(pick_installation)
    fi

    IFS='|' read -r idx name path pid_file <<< "$inst"

    if [ "$(is_running "$pid_file")" != "running" ]; then
        error "'$name' is not running. Start it first with: silicon start $name"
        exit 1
    fi

    local log_file="$path/.silicon.log"
    if [ ! -f "$log_file" ]; then
        error "No log file found at $log_file"
        exit 1
    fi

    local pid
    pid=$(get_pid "$pid_file")
    printf "\n${BOLD}${CYAN}Debugging '$name'${RESET} (PID $pid)\n"
    printf "${DIM}  Log: $log_file${RESET}\n"
    printf "${DIM}  Press Ctrl+C to detach${RESET}\n\n"

    tail -f "$log_file"
}

cmd_attach() {
    local target_dir="${1:-$(pwd)}"

    # Resolve to absolute path
    target_dir=$(cd "$target_dir" 2>/dev/null && pwd || echo "$target_dir")

    # Check if it's a silicon directory
    if [ ! -f "$target_dir/main.py" ] || [ ! -f "$target_dir/config.py" ]; then
        error "This doesn't look like a silicon directory."
        info "Expected main.py and config.py in: $target_dir"
        info "Navigate to a silicon directory and try again, or pass the path:"
        info "  silicon attach /path/to/silicon"
        return 1
    fi

    if [ ! -d "$target_dir/prompts" ] || [ ! -d "$target_dir/core" ]; then
        error "Missing prompts/ or core/ directory. Not a valid silicon."
        return 1
    fi

    # Check if already registered
    while IFS='|' read -r idx name path pid_file; do
        if [ "$path" = "$target_dir" ]; then
            warn "This silicon is already registered as '$name'"
            return 0
        fi
    done <<< "$(get_installations)"

    success "Found a silicon at: $target_dir"

    # Ask for name
    printf "\n${DIM}  Give this instance a name so you can tell it apart from others.${RESET}\n"
    local dir_basename
    dir_basename=$(basename "$target_dir")
    printf "${BOLD}? Instance name [%s]:${RESET} " "$dir_basename"
    read -r instance_name
    instance_name="${instance_name:-$dir_basename}"

    # Check if name already taken
    while IFS='|' read -r idx name path pid_file; do
        if [ "$name" = "$instance_name" ]; then
            error "Name '$instance_name' is already taken. Pick a different one."
            return 1
        fi
    done <<< "$(get_installations)"

    # Detect if running
    local is_currently_running=false
    local detected_pid=""

    # Check for existing .silicon.pid
    if [ -f "$target_dir/.silicon.pid" ]; then
        local pid
        pid=$(cat "$target_dir/.silicon.pid" 2>/dev/null)
        if [ -n "$pid" ] && kill -0 "$pid" 2>/dev/null; then
            is_currently_running=true
            detected_pid="$pid"
        fi
    fi

    # Also try to find python main.py running from that dir
    if [ "$is_currently_running" = false ]; then
        detected_pid=$(ps aux | grep "[p]ython.*main.py" | grep "$target_dir" | awk '{print $2}' | head -1)
        if [ -n "$detected_pid" ] && kill -0 "$detected_pid" 2>/dev/null; then
            is_currently_running=true
        fi
    fi

    local pid_file="$target_dir/.silicon.pid"

    if [ "$is_currently_running" = true ]; then
        success "Detected running instance (PID $detected_pid)"
        # Write PID file so we can track it
        echo "$detected_pid" > "$pid_file"
    else
        info "Instance is not currently running."
    fi

    # Register it
    "$PYTHON_CMD" -c "
import json, os
reg_file = '$REGISTRY_FILE'
if os.path.exists(reg_file):
    with open(reg_file) as f:
        reg = json.load(f)
else:
    reg = {'installations': []}

reg['installations'].append({
    'name': '$instance_name',
    'path': '$target_dir',
    'pid_file': '$pid_file'
})

with open(reg_file, 'w') as f:
    json.dump(reg, f, indent=2)
"

    success "Attached '$instance_name' at $target_dir"

    if [ "$is_currently_running" = true ]; then
        printf "\n  ${BOLD}%s${RESET} ${GREEN}● running${RESET} (PID %s)\n\n" "$instance_name" "$detected_pid"
    else
        printf "\n  ${BOLD}%s${RESET} ${DIM}○ stopped${RESET}\n" "$instance_name"
        printf "  Start it with: ${BOLD}silicon start %s${RESET}\n\n" "$instance_name"
    fi
}

cmd_install() {
    # Re-run the installer
    local script_url="https://raw.githubusercontent.com/unlikefraction/silicon-stemcell/main/install.sh"
    if command -v curl &>/dev/null; then
        curl -fsSL "$script_url" | bash
    elif command -v wget &>/dev/null; then
        wget -qO- "$script_url" | bash
    else
        error "Need curl or wget to re-run installer"
        exit 1
    fi
}

cmd_new() {
    local target_dir
    target_dir=$(pwd)

    echo ""
    printf "  ${BOLD}${CYAN}New Silicon.${RESET} Let's bring one to life.\n\n"

    # ── 1. System checks ──────────────────────────────────────
    printf "  ${BOLD}${CYAN}── Step 1 · System Checks ──${RESET}\n\n"

    # Detect OS
    local SYS_OS="unknown"
    case "$(uname -s)" in
        Darwin*) SYS_OS="mac" ;;
        Linux*)  SYS_OS="linux" ;;
        *)       SYS_OS="unknown" ;;
    esac

    if [ "$SYS_OS" = "unknown" ]; then
        error "Unsupported operating system: $(uname -s)"
        error "Silicon supports macOS and Linux."
        return 1
    fi
    success "Operating system: $(uname -s) ($(uname -m))"

    # Check disk space (need at least 500MB)
    if command -v df &>/dev/null; then
        local avail_kb avail_mb
        avail_kb=$(df -k "$HOME" | tail -1 | awk '{print $4}')
        avail_mb=$((avail_kb / 1024))
        if [ "$avail_mb" -lt 500 ]; then
            error "Low disk space: ${avail_mb}MB available. Need at least 500MB."
            return 1
        fi
        success "Disk space: ${avail_mb}MB available"
    fi

    # ── 2. Prerequisites ──────────────────────────────────────
    echo ""
    printf "  ${BOLD}${CYAN}── Step 2 · Prerequisites ──${RESET}\n\n"

    # ── Python 3.9+ ───────────────────────────────────────────
    local NEW_PYTHON_CMD=""
    for cmd in python3 python; do
        if command -v "$cmd" &>/dev/null; then
            local ver major minor
            ver=$("$cmd" --version 2>&1 | grep -oE '[0-9]+\.[0-9]+' | head -1)
            major=$(echo "$ver" | cut -d. -f1)
            minor=$(echo "$ver" | cut -d. -f2)
            if [ "$major" -ge 3 ] && [ "$minor" -ge 9 ]; then
                NEW_PYTHON_CMD="$cmd"
                break
            fi
        fi
    done

    if [ -n "$NEW_PYTHON_CMD" ]; then
        success "Python: $($NEW_PYTHON_CMD --version) ($NEW_PYTHON_CMD)"
    else
        warn "Python 3.9+ not found"
        printf "${BOLD}? Install Python? [Y/n]:${RESET} "
        read -r py_ans
        case "$py_ans" in
            [nN]*)
                error "Python 3.9+ is required. Aborting."
                return 1
                ;;
            *)
                if [ "$SYS_OS" = "mac" ]; then
                    if command -v brew &>/dev/null; then
                        info "Installing Python via Homebrew..."
                        brew install python3
                    else
                        error "Homebrew not found. Install Python 3.9+ manually from https://python.org/downloads"
                        return 1
                    fi
                else
                    if command -v apt-get &>/dev/null; then
                        info "Installing Python via apt..."
                        sudo apt-get update -qq && sudo apt-get install -y python3 python3-pip python3-venv
                    elif command -v dnf &>/dev/null; then
                        sudo dnf install -y python3 python3-pip
                    elif command -v yum &>/dev/null; then
                        sudo yum install -y python3 python3-pip
                    elif command -v pacman &>/dev/null; then
                        sudo pacman -S --noconfirm python python-pip
                    else
                        error "No supported package manager found. Install Python 3.9+ manually."
                        return 1
                    fi
                fi
                # Re-check
                for cmd in python3 python; do
                    if command -v "$cmd" &>/dev/null; then
                        ver=$("$cmd" --version 2>&1 | grep -oE '[0-9]+\.[0-9]+' | head -1)
                        major=$(echo "$ver" | cut -d. -f1)
                        minor=$(echo "$ver" | cut -d. -f2)
                        if [ "$major" -ge 3 ] && [ "$minor" -ge 9 ]; then
                            NEW_PYTHON_CMD="$cmd"
                            break
                        fi
                    fi
                done
                if [ -z "$NEW_PYTHON_CMD" ]; then
                    error "Python installation failed. Install Python 3.9+ manually and re-run."
                    return 1
                fi
                success "Python installed: $($NEW_PYTHON_CMD --version)"
                ;;
        esac
    fi

    # ── Node.js / npm ─────────────────────────────────────────
    if command -v node &>/dev/null && command -v npm &>/dev/null; then
        success "Node.js: $(node --version)"
    else
        warn "Node.js / npm not found (needed for Claude Code CLI & silicon-browser)"
        printf "${BOLD}? Install Node.js? [Y/n]:${RESET} "
        read -r node_ans
        case "$node_ans" in
            [nN]*)
                error "Node.js is required for Claude Code CLI. Aborting."
                return 1
                ;;
            *)
                if [ "$SYS_OS" = "mac" ]; then
                    if command -v brew &>/dev/null; then
                        info "Installing Node.js via Homebrew..."
                        brew install node
                    else
                        error "Install Node.js from https://nodejs.org or install Homebrew first."
                        return 1
                    fi
                else
                    if command -v apt-get &>/dev/null; then
                        info "Installing Node.js via apt..."
                        if ! command -v curl &>/dev/null; then
                            sudo apt-get install -y curl
                        fi
                        curl -fsSL https://deb.nodesource.com/setup_lts.x | sudo -E bash -
                        sudo apt-get install -y nodejs
                    elif command -v dnf &>/dev/null; then
                        sudo dnf install -y nodejs npm
                    elif command -v yum &>/dev/null; then
                        sudo yum install -y nodejs npm
                    elif command -v pacman &>/dev/null; then
                        sudo pacman -S --noconfirm nodejs npm
                    else
                        error "Install Node.js from https://nodejs.org manually."
                        return 1
                    fi
                fi
                if command -v node &>/dev/null; then
                    success "Node.js installed: $(node --version)"
                else
                    error "Node.js installation failed. Install from https://nodejs.org and re-run."
                    return 1
                fi
                ;;
        esac
    fi

    # ── Claude Code CLI ───────────────────────────────────────
    if command -v claude &>/dev/null; then
        local claude_version
        claude_version=$(claude --version 2>/dev/null | head -1 || echo "unknown")
        success "Claude Code CLI: ${claude_version}"
    else
        warn "Claude Code CLI not found"
        printf "${BOLD}? Install Claude Code CLI via npm? [Y/n]:${RESET} "
        read -r claude_ans
        case "$claude_ans" in
            [nN]*)
                error "Claude Code CLI is required. Aborting."
                return 1
                ;;
            *)
                info "Installing @anthropic-ai/claude-code globally..."
                npm install -g @anthropic-ai/claude-code
                if command -v claude &>/dev/null; then
                    success "Claude Code CLI installed"
                else
                    error "Claude Code CLI installation failed."
                    error "Try manually: npm install -g @anthropic-ai/claude-code"
                    return 1
                fi
                ;;
        esac
    fi

    # ── silicon-browser ───────────────────────────────────────
    if command -v silicon-browser &>/dev/null; then
        success "silicon-browser: installed"
    else
        warn "silicon-browser not found"
        printf "${BOLD}? Install silicon-browser via npm? [Y/n]:${RESET} "
        read -r browser_ans
        case "$browser_ans" in
            [nN]*)
                warn "Skipping silicon-browser. Browser workers will not be available."
                ;;
            *)
                info "Installing silicon-browser globally..."
                npm install -g silicon-browser
                if command -v silicon-browser &>/dev/null; then
                    success "silicon-browser installed"
                else
                    warn "silicon-browser install may have failed. Browser workers may not work."
                    warn "Try manually: npm install -g silicon-browser"
                fi
                ;;
        esac
    fi

    # ── 3. Check if silicon already exists ─────────────────────
    echo ""
    printf "  ${BOLD}${CYAN}── Step 3 · Download Silicon ──${RESET}\n\n"

    if [ -f "$target_dir/main.py" ] && [ -d "$target_dir/prompts" ] && [ -f "$target_dir/config.py" ]; then
        warn "There's already a Silicon here."
        printf "  ${DIM}%s${RESET}\n\n" "$target_dir"
        printf "${BOLD}? Overwrite and reinitialize? [y/N]:${RESET} "
        read -r reinit_ans
        case "$reinit_ans" in
            [yY]*) info "Alright, reinitializing." ;;
            *)
                info "Use 'silicon start' to fire it up."
                return 0
                ;;
        esac
    fi

    # ── 4. Clone the repo ──────────────────────────────────────
    local SILICON_REPO="https://github.com/unlikefraction/silicon.git"
    local SILICON_ZIP="https://github.com/unlikefraction/silicon/archive/refs/heads/main.zip"
    local needs_clone=true

    if [ -f "$target_dir/main.py" ] && [ -f "$target_dir/config.py" ]; then
        needs_clone=false
    fi

    if [ "$needs_clone" = true ]; then
        # Check if directory is empty (besides hidden files like .DS_Store)
        local file_count
        file_count=$(find "$target_dir" -maxdepth 1 -not -name '.*' -not -path "$target_dir" | wc -l | tr -d ' ')

        if [ "$file_count" -gt 0 ]; then
            error "This directory isn't empty. Run 'silicon new' in an empty directory."
            printf "  ${DIM}Try: mkdir my-silicon && cd my-silicon && silicon new${RESET}\n\n"
            return 1
        fi

        if command -v git &>/dev/null; then
            info "Cloning Silicon..."
            if ! git clone "$SILICON_REPO" . 2>/dev/null; then
                error "Failed to clone. Check your internet connection and try again."
                return 1
            fi
            success "Silicon cloned"
        elif command -v curl &>/dev/null; then
            info "git not found. Downloading ZIP via curl..."
            local TMP_ZIP TMP_DIR
            TMP_ZIP=$(mktemp /tmp/silicon-XXXXXX.zip)
            TMP_DIR=$(mktemp -d /tmp/silicon-extract-XXXXXX)
            curl -fsSL "$SILICON_ZIP" -o "$TMP_ZIP"
            unzip -q "$TMP_ZIP" -d "$TMP_DIR"
            cp -a "$TMP_DIR"/silicon-main/. "$target_dir/"
            rm -rf "$TMP_ZIP" "$TMP_DIR"
            success "Downloaded and extracted"
        elif command -v wget &>/dev/null; then
            info "git not found. Downloading ZIP via wget..."
            local TMP_ZIP TMP_DIR
            TMP_ZIP=$(mktemp /tmp/silicon-XXXXXX.zip)
            TMP_DIR=$(mktemp -d /tmp/silicon-extract-XXXXXX)
            wget -q "$SILICON_ZIP" -O "$TMP_ZIP"
            unzip -q "$TMP_ZIP" -d "$TMP_DIR"
            cp -a "$TMP_DIR"/silicon-main/. "$target_dir/"
            rm -rf "$TMP_ZIP" "$TMP_DIR"
            success "Downloaded and extracted"
        else
            error "No git, curl, or wget found. Cannot download Silicon."
            return 1
        fi
    fi

    # ── 5. Install pip dependencies ────────────────────────────
    if [ -f "$target_dir/requirements.txt" ]; then
        info "Installing Python dependencies..."
        "$NEW_PYTHON_CMD" -m pip install -r "$target_dir/requirements.txt" --quiet 2>/dev/null || \
            "$NEW_PYTHON_CMD" -m pip install -r "$target_dir/requirements.txt" --quiet --user 2>/dev/null
        success "Python dependencies installed"
    fi

    # ── 6. Configure ───────────────────────────────────────────
    echo ""
    printf "  ${BOLD}${CYAN}── Step 4 · Configure ──${RESET}\n\n"

    printf "  ${BOLD}Telegram Bot Token${RESET} ${DIM}(required)${RESET}\n"
    printf "  ${DIM}This is how Silicon talks to you. Don't have a bot yet?${RESET}\n"
    printf "  ${DIM}Open Telegram > @BotFather > /newbot > copy the token. 30 seconds.${RESET}\n\n"

    printf "${BOLD}? Bot token:${RESET} "
    local telegram_token=""
    local char=""
    while IFS= read -r -s -n1 char; do
        if [[ -z "$char" ]]; then
            break
        elif [[ "$char" == $'\x7f' ]] || [[ "$char" == $'\b' ]]; then
            if [[ -n "$telegram_token" ]]; then
                telegram_token="${telegram_token%?}"
                printf "\b \b"
            fi
        else
            telegram_token="${telegram_token}${char}"
            printf "*"
        fi
    done
    printf "\n"

    if [ -z "$telegram_token" ]; then
        error "Can't skip this one. Silicon needs Telegram to reach you."
        return 1
    fi
    success "Got it"

    echo ""
    printf "  ${BOLD}OpenAI API Key${RESET} ${DIM}(optional — for voice messages)${RESET}\n"
    printf "  ${DIM}Used for speech-to-text and TTS. Press Enter to skip.${RESET}\n\n"

    printf "${BOLD}? OpenAI key:${RESET} "
    local openai_key=""
    while IFS= read -r -s -n1 char; do
        if [[ -z "$char" ]]; then
            break
        elif [[ "$char" == $'\x7f' ]] || [[ "$char" == $'\b' ]]; then
            if [[ -n "$openai_key" ]]; then
                openai_key="${openai_key%?}"
                printf "\b \b"
            fi
        else
            openai_key="${openai_key}${char}"
            printf "*"
        fi
    done
    printf "\n"

    if [ -n "$openai_key" ]; then
        success "Got it"
    else
        info "Skipped — no voice features"
    fi

    # Write env.py
    cat > "$target_dir/env.py" << ENVEOF
TELEGRAM_BOT_TOKEN = "$telegram_token"
OPENAI_API_KEY = "$openai_key"
ENVEOF
    success "env.py written"

    # ── 7. Register ────────────────────────────────────────────
    echo ""
    printf "  ${BOLD}${CYAN}── Step 5 · Registry ──${RESET}\n\n"

    local instance_name
    instance_name=$(basename "$target_dir")
    local abs_dir
    abs_dir=$(cd "$target_dir" 2>/dev/null && pwd || echo "$target_dir")
    local pid_file="$abs_dir/.silicon.pid"

    mkdir -p "$REGISTRY_DIR"
    if [ ! -f "$REGISTRY_FILE" ]; then
        echo '{"installations": []}' > "$REGISTRY_FILE"
    fi

    local already_registered
    already_registered=$("$NEW_PYTHON_CMD" -c "
import json
with open('$REGISTRY_FILE') as f:
    reg = json.load(f)
for inst in reg.get('installations', []):
    if inst.get('path') == '$abs_dir':
        print('true')
        exit(0)
print('false')
" 2>/dev/null || echo "false")

    if [ "$already_registered" != "true" ]; then
        "$NEW_PYTHON_CMD" -c "
import json
from datetime import datetime
with open('$REGISTRY_FILE') as f:
    reg = json.load(f)
reg['installations'].append({
    'name': '$instance_name',
    'path': '$abs_dir',
    'created_at': datetime.now().isoformat(),
    'pid_file': '$pid_file'
})
with open('$REGISTRY_FILE', 'w') as f:
    json.dump(reg, f, indent=2)
"
    fi
    success "Registered as '$instance_name'"

    # ── Done ───────────────────────────────────────────────────
    echo ""
    printf "  ${GREEN}${BOLD}Silicon is alive.${RESET}\n\n"
    printf "  ${BOLD}Location:${RESET}  %s\n" "$abs_dir"
    printf "  ${BOLD}Instance:${RESET}  %s\n\n" "$instance_name"
    printf "  Run ${BOLD}silicon start${RESET} to boot it up.\n"
    printf "  Then message your bot on Telegram — first person to say hi becomes the carbon.\n\n"
}

cmd_help() {
    printf "\n${BOLD}${CYAN}silicon${RESET} – manage your silicon instances\n\n"
    printf "${BOLD}Usage:${RESET}\n"
    printf "  silicon                     Show status or list instances\n"
    printf "  silicon new                 Create a new Silicon in the current directory\n"
    printf "  silicon start [name]        Start a silicon instance\n"
    printf "  silicon stop [name]         Stop a running instance\n"
    printf "  silicon status [name]       Show instance status\n"
    printf "  silicon browser [name]      Open headed browser for login\n"
    printf "  silicon debug [name]        Attach to running instance (live logs)\n"
    printf "  silicon attach [path]       Register an existing silicon instance\n"
    printf "  silicon list                List all instances\n"
    printf "  silicon script update       Update the silicon CLI script\n"
    printf "  silicon install             Install a new instance\n"
    printf "  silicon help                Show this help\n"
    echo ""
}

# ── Fuzzy command matching ───────────────────────────────────

suggest_command() {
    local input="$1"
    local commands="start stop status browser debug attach list install new help script"
    local best_match=""
    local best_score=999

    for cmd in $commands; do
        # Simple Levenshtein-like: count chars in common
        local score=0
        local i=0
        local input_len=${#input}
        local cmd_len=${#cmd}

        # Length difference penalty
        local len_diff=$((input_len - cmd_len))
        [ "$len_diff" -lt 0 ] && len_diff=$((-len_diff))

        # Check prefix match
        if [[ "$cmd" == "$input"* ]] || [[ "$input" == "$cmd"* ]]; then
            score=$len_diff
        else
            # Character overlap score
            local common=0
            for ((i=0; i<input_len && i<cmd_len; i++)); do
                if [ "${input:$i:1}" = "${cmd:$i:1}" ]; then
                    common=$((common + 1))
                fi
            done
            local max_len=$cmd_len
            [ "$input_len" -gt "$max_len" ] && max_len=$input_len
            score=$((max_len - common + len_diff))
        fi

        if [ "$score" -lt "$best_score" ]; then
            best_score=$score
            best_match=$cmd
        fi
    done

    # Only suggest if reasonably close (score <= 3)
    if [ "$best_score" -le 3 ] && [ -n "$best_match" ]; then
        printf "\n${YELLOW}Did you mean?${RESET}\n"
        printf "  silicon %s\n\n" "$best_match"
    fi
}

# ── Main dispatch ─────────────────────────────────────────────

CMD="${1:-}"
ARG="${2:-}"

case "$CMD" in
    start)   cmd_start "$ARG" ;;
    stop)    cmd_stop "$ARG" ;;
    status)  cmd_status "$ARG" ;;
    browser) cmd_browser "$ARG" ;;
    debug)   cmd_debug "$ARG" ;;
    attach)  cmd_attach "$ARG" ;;
    list|ls) cmd_list ;;
    script)
        case "$ARG" in
            update) cmd_update ;;
            *) error "Unknown script command: $ARG. Did you mean: silicon script update?"; exit 1 ;;
        esac
        ;;
    new)     cmd_new ;;
    install) cmd_install ;;
    help|-h|--help) cmd_help ;;
    "")      cmd_status "" ;;
    *)
        error "Unknown command: $CMD"
        suggest_command "$CMD"
        ;;
esac
CLIEOF

chmod +x "$CLI_SCRIPT"
success "CLI created at $CLI_SCRIPT"

# ── Add to PATH ───────────────────────────────────────────────

add_to_path() {
    local shell_rc=""
    local current_shell
    current_shell=$(basename "${SHELL:-/bin/bash}")

    case "$current_shell" in
        zsh)  shell_rc="$HOME/.zshrc" ;;
        bash)
            if [ -f "$HOME/.bash_profile" ]; then
                shell_rc="$HOME/.bash_profile"
            else
                shell_rc="$HOME/.bashrc"
            fi
            ;;
        *)    shell_rc="$HOME/.profile" ;;
    esac

    local path_line="export PATH=\"$BIN_DIR:\$PATH\""

    # Check if already in PATH
    if echo "$PATH" | tr ':' '\n' | grep -qx "$BIN_DIR"; then
        success "CLI already in PATH"
        return
    fi

    # Check if already in rc file
    if [ -f "$shell_rc" ] && grep -qF "$BIN_DIR" "$shell_rc" 2>/dev/null; then
        success "PATH entry already in $shell_rc"
        # Still export for current session
        export PATH="$BIN_DIR:$PATH"
        return
    fi

    echo "" >> "$shell_rc"
    echo "# Silicon CLI" >> "$shell_rc"
    echo "$path_line" >> "$shell_rc"
    export PATH="$BIN_DIR:$PATH"
    success "Added to PATH via $shell_rc"
}

add_to_path

# ═════════════════════════════════════════════════════════════
# STEP 7: Summary
# ═════════════════════════════════════════════════════════════

header "Installation Complete"

printf "${GREEN}"
cat << 'DONE'
  ╔══════════════════════════════════════════╗
  ║     Silicon is ready to go! 🚀          ║
  ╚══════════════════════════════════════════╝
DONE
printf "${RESET}\n"

printf "  ${BOLD}Instance:${RESET}  %s\n" "$INSTANCE_NAME"
printf "  ${BOLD}Location:${RESET}  %s\n" "$ABS_INSTALL_DIR"
printf "  ${BOLD}Registry:${RESET}  %s\n" "$REGISTRY_FILE"
printf "  ${BOLD}CLI:${RESET}       %s\n" "$CLI_SCRIPT"
echo ""
printf "  ${BOLD}${CYAN}Quick start:${RESET}\n"
printf "    ${DIM}# Start a new terminal (or run: source ~/.zshrc)${RESET}\n"
printf "    silicon start          ${DIM}# Start silicon${RESET}\n"
printf "    silicon debug           ${DIM}# Attach to live logs${RESET}\n"
printf "    silicon browser        ${DIM}# Login to services${RESET}\n"
printf "    silicon stop           ${DIM}# Stop silicon${RESET}\n"
printf "    silicon list           ${DIM}# See all instances${RESET}\n"
printf "    silicon script update  ${DIM}# Update CLI to latest${RESET}\n"
echo ""
printf "  ${BOLD}${CYAN}All commands:${RESET}\n"
printf "    silicon help\n"
echo ""
