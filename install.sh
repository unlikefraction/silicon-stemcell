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
    warn "Node.js / npm not found (needed for Claude Code CLI & agent-browser)"
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

# ── agent-browser ─────────────────────────────────────────────

if command -v agent-browser &>/dev/null; then
    success "agent-browser: installed"
else
    warn "agent-browser not found"
    if confirm "Install agent-browser via npm?"; then
        info "Installing @anthropic-ai/agent-browser globally..."
        npm install -g @anthropic-ai/agent-browser
        if command -v agent-browser &>/dev/null; then
            success "agent-browser installed"
        else
            warn "agent-browser install may have failed. Browser workers may not work."
            warn "Try manually: npm install -g @anthropic-ai/agent-browser"
        fi
    else
        warn "Skipping agent-browser. Browser workers will not be available."
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

    printf "\n${BOLD}${CYAN}"
    cat << 'NEWBANNER'
  ╔══════════════════════════════════════════╗
  ║     New Silicon Instance                ║
  ╚══════════════════════════════════════════╝
NEWBANNER
    printf "${RESET}\n"

    # Check if Silicon already exists here
    if [ -f "$target_dir/main.py" ] && [ -f "$target_dir/config.py" ] && [ -d "$target_dir/prompts" ]; then
        warn "There's already a Silicon living here."
        printf "  ${DIM}Found: main.py, config.py, prompts/ at %s${RESET}\n\n" "$target_dir"

        printf "${BOLD}? Reinitialize this Silicon? This will overwrite config files. [y/N]:${RESET} "
        read -r reinit_ans
        case "$reinit_ans" in
            [yY]*) info "Alright, let's reconfigure this one." ;;
            *)
                info "Smart move. Use 'silicon start' to fire it up if it's ready."
                return 0
                ;;
        esac
        echo ""
    fi

    # ── Step 1: Your name ──────────────────────────────────────
    printf "  ${BOLD}Let's get you set up.${RESET}\n\n"
    printf "${BOLD}? What's your name?:${RESET} "
    read -r carbon_name
    if [ -z "$carbon_name" ]; then
        error "Need a name. Silicon doesn't serve ghosts."
        return 1
    fi

    # Derive a carbon_id from the name (lowercase, no spaces)
    local carbon_id
    carbon_id=$(echo "$carbon_name" | tr '[:upper:]' '[:lower:]' | tr ' ' '_' | tr -cd 'a-z0-9_')

    printf "  ${DIM}Cool. You'll be known as ${BOLD}%s${RESET}${DIM} (carbon_id: %s)${RESET}\n\n" "$carbon_name" "$carbon_id"

    # ── Step 2: Telegram bot token ─────────────────────────────
    printf "  ${BOLD}Telegram Bot Token${RESET}\n"
    printf "  ${DIM}Silicon talks to you through Telegram. You need a bot.${RESET}\n"
    printf "  ${DIM}Don't have one? Takes 30 seconds:${RESET}\n"
    printf "    ${DIM}1. Open Telegram, find ${BOLD}@BotFather${RESET}\n"
    printf "    ${DIM}2. Send ${BOLD}/newbot${RESET}${DIM}, pick a name and username${RESET}\n"
    printf "    ${DIM}3. Copy the token it gives you${RESET}\n\n"

    printf "${BOLD}? Telegram bot token:${RESET} "
    # Read with masking
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
        error "Bot token is required. Silicon needs Telegram to reach you."
        return 1
    fi
    success "Bot token saved"
    echo ""

    # ── Step 3: Telegram user ID ───────────────────────────────
    printf "  ${BOLD}Your Telegram User ID${RESET}\n"
    printf "  ${DIM}This is how Silicon knows which Telegram user is you.${RESET}\n"
    printf "  ${DIM}Don't know yours? Easy:${RESET}\n"
    printf "    ${DIM}1. Open Telegram, find ${BOLD}@userinfobot${RESET}\n"
    printf "    ${DIM}2. Send it any message${RESET}\n"
    printf "    ${DIM}3. It replies with your user ID (a number)${RESET}\n\n"

    printf "${BOLD}? Your Telegram user ID:${RESET} "
    read -r telegram_userid

    if [ -z "$telegram_userid" ]; then
        error "User ID is required. Silicon needs to know who the boss is."
        return 1
    fi

    # Validate it's a number
    if ! [[ "$telegram_userid" =~ ^[0-9]+$ ]]; then
        error "That doesn't look like a Telegram user ID. It should be a number."
        return 1
    fi
    success "User ID locked in"
    echo ""

    # ── Step 4: Anthropic API key ──────────────────────────────
    printf "  ${BOLD}Anthropic API Key${RESET}\n"
    printf "  ${DIM}Silicon's brain runs on Claude. You need an API key.${RESET}\n"
    printf "  ${DIM}Get one at: ${BOLD}console.anthropic.com${RESET}\n\n"

    printf "${BOLD}? Anthropic API key:${RESET} "
    local anthropic_key=""
    while IFS= read -r -s -n1 char; do
        if [[ -z "$char" ]]; then
            break
        elif [[ "$char" == $'\x7f' ]] || [[ "$char" == $'\b' ]]; then
            if [[ -n "$anthropic_key" ]]; then
                anthropic_key="${anthropic_key%?}"
                printf "\b \b"
            fi
        else
            anthropic_key="${anthropic_key}${char}"
            printf "*"
        fi
    done
    printf "\n"

    if [ -z "$anthropic_key" ]; then
        error "API key is required. No brain, no Silicon."
        return 1
    fi
    success "API key saved"
    echo ""

    # ── Step 5: OpenAI key (optional) ──────────────────────────
    printf "  ${BOLD}OpenAI API Key ${DIM}(optional)${RESET}\n"
    printf "  ${DIM}For voice message transcription & text-to-speech.${RESET}\n"
    printf "  ${DIM}Press Enter to skip — voice features will be disabled.${RESET}\n\n"

    printf "${BOLD}? OpenAI API key (optional):${RESET} "
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
        success "OpenAI key saved"
    else
        info "Skipped. Voice features disabled."
    fi
    echo ""

    # ── Step 6: Clone / setup directory ────────────────────────
    local REPO_URL="https://github.com/unlikefraction/silicon-stemcell.git"
    local REPO_ZIP="https://github.com/unlikefraction/silicon-stemcell/archive/refs/heads/main.zip"
    local needs_clone=true

    if [ -f "$target_dir/main.py" ] && [ -f "$target_dir/config.py" ]; then
        needs_clone=false
        info "Using existing Silicon files at $target_dir"
    fi

    if [ "$needs_clone" = true ]; then
        info "Downloading Silicon..."
        if command -v git &>/dev/null; then
            git clone "$REPO_URL" "$target_dir/silicon-new-tmp" 2>/dev/null
            # Move contents (not the .git, we'll keep it)
            shopt -s dotglob 2>/dev/null
            mv "$target_dir/silicon-new-tmp"/* "$target_dir/" 2>/dev/null
            mv "$target_dir/silicon-new-tmp"/.[!.]* "$target_dir/" 2>/dev/null
            rmdir "$target_dir/silicon-new-tmp" 2>/dev/null
            shopt -u dotglob 2>/dev/null
            success "Downloaded via git"
        elif command -v curl &>/dev/null; then
            local tmp_zip
            tmp_zip=$(mktemp /tmp/silicon-XXXXXX.zip)
            local tmp_dir
            tmp_dir=$(mktemp -d /tmp/silicon-extract-XXXXXX)
            curl -fsSL "$REPO_ZIP" -o "$tmp_zip"
            unzip -q "$tmp_zip" -d "$tmp_dir"
            cp -R "$tmp_dir"/silicon-stemcell-main/* "$target_dir/"
            cp -R "$tmp_dir"/silicon-stemcell-main/.[!.]* "$target_dir/" 2>/dev/null
            rm -rf "$tmp_zip" "$tmp_dir"
            success "Downloaded via curl"
        else
            error "Need git or curl to download Silicon."
            return 1
        fi
    fi

    # ── Step 7: Write config files ─────────────────────────────
    info "Writing config files..."

    # env.py
    cat > "$target_dir/env.py" << ENVEOF
TELEGRAM_BOT_TOKEN = "$telegram_token"
OPENAI_API_KEY = "$openai_key"
ENVEOF

    # Set ANTHROPIC_API_KEY in a .env file for Claude CLI
    echo "ANTHROPIC_API_KEY=$anthropic_key" > "$target_dir/.env"

    # contacts.json — pre-register the carbon as central
    "$PYTHON_CMD" -c "
import json
contacts = {
    'last_update_id': 0,
    'contacts': {
        '$carbon_id': {
            'name': '$carbon_name',
            'carbon_id': '$carbon_id',
            'telegram_userid': $telegram_userid,
            'trust_level': 'ultimate',
            'is_central_carbon': True,
            'relation': '',
            'description': '',
            'timezone': ''
        }
    }
}
with open('$target_dir/core/telegram/contacts.json', 'w') as f:
    json.dump(contacts, f, indent=2)
"
    # Also write the backup
    cp "$target_dir/core/telegram/contacts.json" "$target_dir/core/telegram/contacts_backup.json" 2>/dev/null

    success "Config files written"

    # ── Step 8: Install pip packages ───────────────────────────
    if [ -f "$target_dir/requirements.txt" ]; then
        info "Installing Python dependencies..."
        "$PYTHON_CMD" -m pip install -r "$target_dir/requirements.txt" --quiet 2>/dev/null || \
            "$PYTHON_CMD" -m pip install -r "$target_dir/requirements.txt" --quiet --user 2>/dev/null
        success "Dependencies installed"
    fi

    # ── Step 9: Instance name & registry ───────────────────────
    local dir_basename
    dir_basename=$(basename "$target_dir")
    printf "\n${DIM}  Give this instance a name (useful if you run multiple silicons).${RESET}\n"
    printf "${BOLD}? Instance name [%s]:${RESET} " "$dir_basename"
    read -r instance_name
    instance_name="${instance_name:-$dir_basename}"

    local abs_dir
    abs_dir=$(cd "$target_dir" 2>/dev/null && pwd || echo "$target_dir")
    local pid_file="$abs_dir/.silicon.pid"

    mkdir -p "$REGISTRY_DIR"

    if [ ! -f "$REGISTRY_FILE" ]; then
        echo '{"installations": []}' > "$REGISTRY_FILE"
    fi

    # Check if already registered
    local already_registered
    already_registered=$("$PYTHON_CMD" -c "
import json
with open('$REGISTRY_FILE') as f:
    reg = json.load(f)
for inst in reg.get('installations', []):
    if inst.get('path') == '$abs_dir' or inst.get('name') == '$instance_name':
        print('true')
        exit(0)
print('false')
" 2>/dev/null || echo "false")

    if [ "$already_registered" = "true" ]; then
        success "Instance already registered"
    else
        "$PYTHON_CMD" -c "
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
        success "Registered '$instance_name'"
    fi

    # ── Done! ──────────────────────────────────────────────────
    printf "\n${GREEN}"
    cat << 'DONEBANNER'
  ╔══════════════════════════════════════════╗
  ║     Silicon is ready. Let's go.         ║
  ╚══════════════════════════════════════════╝
DONEBANNER
    printf "${RESET}\n"

    printf "  ${BOLD}Carbon:${RESET}    %s (%s)\n" "$carbon_name" "$carbon_id"
    printf "  ${BOLD}Instance:${RESET}  %s\n" "$instance_name"
    printf "  ${BOLD}Location:${RESET}  %s\n" "$abs_dir"
    echo ""
    printf "  ${BOLD}${CYAN}Next up:${RESET}\n"
    printf "    ${BOLD}silicon start${RESET}   ${DIM}# Boot it up${RESET}\n"
    printf "    ${DIM}Then message your bot on Telegram. Silicon takes it from there.${RESET}\n"
    echo ""
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
