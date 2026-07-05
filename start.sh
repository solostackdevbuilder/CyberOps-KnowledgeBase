#!/usr/bin/env bash
# ============================================
#   CyberOps Knowledge Base - Startup Script
# ============================================
set -euo pipefail

# ------------------------------------------------
# Configuration
# ------------------------------------------------
DEFAULT_BACKEND_PORT=17000
DEFAULT_FRONTEND_PORT=17001
BACKEND_PORT=$DEFAULT_BACKEND_PORT
FRONTEND_PORT=$DEFAULT_FRONTEND_PORT
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
BACKEND_PID=""
FRONTEND_PID=""

# ------------------------------------------------
# Colors (if terminal supports them)
# ------------------------------------------------
if [ -t 1 ]; then
    GREEN='\033[0;32m'
    YELLOW='\033[1;33m'
    RED='\033[0;31m'
    CYAN='\033[0;36m'
    BOLD='\033[1m'
    NC='\033[0m'
else
    GREEN='' YELLOW='' RED='' CYAN='' BOLD='' NC=''
fi

info()  { echo -e "${BOLD}[*]${NC} $*"; }
ok()    { echo -e "${GREEN}[OK]${NC} $*"; }
warn()  { echo -e "${YELLOW}[!]${NC} $*"; }
err()   { echo -e "${RED}[ERROR]${NC} $*"; }

# ------------------------------------------------
# Cleanup handler
# ------------------------------------------------
cleanup() {
    echo ""
    info "Shutting down..."
    [ -n "$BACKEND_PID" ]  && kill "$BACKEND_PID"  2>/dev/null && wait "$BACKEND_PID"  2>/dev/null || true
    [ -n "$FRONTEND_PID" ] && kill "$FRONTEND_PID" 2>/dev/null && wait "$FRONTEND_PID" 2>/dev/null || true
    ok "All servers stopped."
    exit 0
}
trap cleanup SIGINT SIGTERM

# ------------------------------------------------
# Port utilities
# ------------------------------------------------
is_port_in_use() {
    local port=$1
    if command -v lsof &>/dev/null; then
        lsof -iTCP:"$port" -sTCP:LISTEN -t &>/dev/null
    elif command -v ss &>/dev/null; then
        ss -tlnH "sport = :$port" 2>/dev/null | grep -q .
    elif command -v netstat &>/dev/null; then
        netstat -tlnp 2>/dev/null | grep -q ":$port "
    else
        # Fallback: try connecting to the port
        (echo >/dev/tcp/localhost/"$port") 2>/dev/null
    fi
}

find_available_port() {
    local start=$1
    local end=$2
    for ((port=start; port<=end; port++)); do
        if ! is_port_in_use "$port"; then
            echo "$port"
            return 0
        fi
    done
    return 1
}

# ------------------------------------------------
# Banner
# ------------------------------------------------
echo ""
echo -e "${BOLD}============================================${NC}"
echo -e "${BOLD}  CyberOps Knowledge Base - Startup Script${NC}"
echo -e "${BOLD}============================================${NC}"
echo ""

# ------------------------------------------------
# Prerequisite checks
# ------------------------------------------------
info "Checking prerequisites..."

PYTHON_CMD=""
if command -v python3 &>/dev/null; then
    PYTHON_CMD="python3"
elif command -v python &>/dev/null; then
    PYTHON_CMD="python"
else
    err "Python is not installed or not in PATH."
    err "Please install Python 3.10+ from https://www.python.org/downloads/"
    exit 1
fi
ok "Python found: $PYTHON_CMD"

if ! command -v node &>/dev/null; then
    err "Node.js is not installed or not in PATH."
    err "Please install Node.js 18+ from https://nodejs.org/"
    exit 1
fi
ok "Node.js found: $(node --version)"

if ! command -v npm &>/dev/null; then
    err "npm is not installed or not in PATH."
    exit 1
fi
ok "npm found: $(npm --version)"
echo ""

# ------------------------------------------------
# Check backend port availability
# ------------------------------------------------
info "Checking if port $BACKEND_PORT is available for backend..."
if is_port_in_use "$BACKEND_PORT"; then
    warn "Port $BACKEND_PORT is already in use. Searching for an available port..."
    BACKEND_PORT=$(find_available_port 17002 17100) || {
        err "Could not find an available port for the backend (tried 17002-17100)."
        exit 1
    }
fi
ok "Backend will use port $BACKEND_PORT"
echo ""

# ------------------------------------------------
# Check frontend port availability
# ------------------------------------------------
info "Checking if port $FRONTEND_PORT is available for frontend..."
if is_port_in_use "$FRONTEND_PORT"; then
    warn "Port $FRONTEND_PORT is already in use. Searching for an available port..."
    FRONTEND_PORT=$(find_available_port 17101 17200) || {
        err "Could not find an available port for the frontend (tried 17101-17200)."
        exit 1
    }
fi
ok "Frontend will use port $FRONTEND_PORT"
echo ""

# ------------------------------------------------
# Setup Python virtual environment
# ------------------------------------------------
info "Checking Python virtual environment..."
if [ -d "$SCRIPT_DIR/backend/venv" ]; then
    ok "Virtual environment found."
else
    warn "Virtual environment not found. Creating one..."
    $PYTHON_CMD -m venv "$SCRIPT_DIR/backend/venv"
    ok "Virtual environment created."
    info "Installing backend dependencies..."
    # shellcheck disable=SC1091
    source "$SCRIPT_DIR/backend/venv/bin/activate"
    pip install -r "$SCRIPT_DIR/backend/requirements.txt"
    ok "Backend dependencies installed."
fi
echo ""

# ------------------------------------------------
# Setup frontend dependencies
# ------------------------------------------------
info "Checking frontend dependencies..."
if [ -d "$SCRIPT_DIR/frontend/node_modules" ]; then
    ok "Node modules found."
else
    warn "Node modules not found. Installing..."
    (cd "$SCRIPT_DIR/frontend" && npm install)
    ok "Frontend dependencies installed."
fi
echo ""

# ------------------------------------------------
# Start Backend
# ------------------------------------------------
info "Starting backend on port $BACKEND_PORT..."
(
    cd "$SCRIPT_DIR/backend"
    # shellcheck disable=SC1091
    source venv/bin/activate
    uvicorn app.main:app --reload --port "$BACKEND_PORT"
) &
BACKEND_PID=$!

# Give backend a moment to initialize
sleep 3

# ------------------------------------------------
# Start Frontend
# ------------------------------------------------
info "Starting frontend on port $FRONTEND_PORT..."
(
    cd "$SCRIPT_DIR/frontend"
    PORT=$FRONTEND_PORT BACKEND_PORT=$BACKEND_PORT npm run dev
) &
FRONTEND_PID=$!

# ------------------------------------------------
# Summary
# ------------------------------------------------
echo ""
echo -e "${BOLD}============================================${NC}"
echo -e "${BOLD}  CyberOps is starting up!${NC}"
echo -e "${BOLD}============================================${NC}"
echo ""
if [ "$BACKEND_PORT" != "$DEFAULT_BACKEND_PORT" ]; then
    echo -e "  ${YELLOW}[NOTE] Backend port changed: $DEFAULT_BACKEND_PORT -> $BACKEND_PORT${NC}"
fi
if [ "$FRONTEND_PORT" != "$DEFAULT_FRONTEND_PORT" ]; then
    echo -e "  ${YELLOW}[NOTE] Frontend port changed: $DEFAULT_FRONTEND_PORT -> $FRONTEND_PORT${NC}"
fi
echo ""
echo -e "  Frontend: ${CYAN}http://localhost:$FRONTEND_PORT${NC}"
echo -e "  Backend:  ${CYAN}http://localhost:$BACKEND_PORT${NC}"
echo -e "  API Docs: ${CYAN}http://localhost:$BACKEND_PORT/docs${NC}"
echo ""
echo -e "  Backend PID:  $BACKEND_PID"
echo -e "  Frontend PID: $FRONTEND_PID"
echo ""
echo -e "  Press ${BOLD}Ctrl+C${NC} to stop both servers."
echo -e "${BOLD}============================================${NC}"
echo ""

# Wait for both background processes
wait
