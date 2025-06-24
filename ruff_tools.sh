#!/usr/bin/env bash
# Semantic commands for ruff linting operations
# Source this file: source ./ruff_tools.sh

# Color codes for output
RED='\033[0;31m'
GREEN='\033[0;32m'
BLUE='\033[0;34m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

# Default error file location
RUFF_ERROR_FILE=".ruff_errors.jsonl"

# Analysis Commands
ruff_analyze() {
    local target="${1:-.}"
    echo -e "${BLUE}Analyzing $target with ruff...${NC}"
    uv run ruff check "$target" --output-format=json-lines -o "$RUFF_ERROR_FILE"
    local count=$(wc -l < "$RUFF_ERROR_FILE")
    echo -e "${YELLOW}Found $count total errors. Results saved to $RUFF_ERROR_FILE${NC}"
}

ruff_summary() {
    if [[ ! -f "$RUFF_ERROR_FILE" ]]; then
        echo -e "${RED}No error file found. Run ruff_analyze first.${NC}"
        return 1
    fi
    echo -e "${BLUE}Error Summary by Type:${NC}"
    cat "$RUFF_ERROR_FILE" | jq -r '.code' | sort | uniq -c | sort -nr | head -20
}

ruff_by_file() {
    if [[ ! -f "$RUFF_ERROR_FILE" ]]; then
        echo -e "${RED}No error file found. Run ruff_analyze first.${NC}"
        return 1
    fi
    echo -e "${BLUE}Errors by File:${NC}"
    cat "$RUFF_ERROR_FILE" | jq -r '.filename' | sed "s|$PWD/||" | sort | uniq -c | sort -nr
}

ruff_hot_files() {
    if [[ ! -f "$RUFF_ERROR_FILE" ]]; then
        echo -e "${RED}No error file found. Run ruff_analyze first.${NC}"
        return 1
    fi
    echo -e "${BLUE}Top 10 Files with Most Errors:${NC}"
    cat "$RUFF_ERROR_FILE" | jq -r '.filename' | sed "s|$PWD/||" | sort | uniq -c | sort -nr | head -10
}

ruff_show() {
    local error_code="${1}"
    if [[ -z "$error_code" ]]; then
        echo -e "${RED}Usage: ruff_show ERROR_CODE${NC}"
        echo "Example: ruff_show ANN201"
        return 1
    fi
    if [[ ! -f "$RUFF_ERROR_FILE" ]]; then
        echo -e "${RED}No error file found. Run ruff_analyze first.${NC}"
        return 1
    fi
    echo -e "${BLUE}Examples of $error_code errors:${NC}"
    cat "$RUFF_ERROR_FILE" | jq -r "select(.code == \"$error_code\") | [.filename, .location.row, .message] | @tsv" | sed "s|$PWD/||" | head -10
}

ruff_find_pattern() {
    local pattern="${1}"
    if [[ -z "$pattern" ]]; then
        echo -e "${RED}Usage: ruff_find_pattern PATTERN${NC}"
        echo "Example: ruff_find_pattern 'assert False'"
        return 1
    fi
    if [[ ! -f "$RUFF_ERROR_FILE" ]]; then
        echo -e "${RED}No error file found. Run ruff_analyze first.${NC}"
        return 1
    fi
    echo -e "${BLUE}Errors matching pattern '$pattern':${NC}"
    cat "$RUFF_ERROR_FILE" | jq -r "select(.message | contains(\"$pattern\")) | [.code, .filename, .location.row, .message] | @tsv" | sed "s|$PWD/||" | head -20
}

# Fix Commands
ruff_autofix() {
    local target="${1:-.}"
    echo -e "${GREEN}Running safe auto-fixes on $target...${NC}"
    uv run ruff check "$target" --fix
}

ruff_unsafe_fix() {
    local target="${1:-.}"
    echo -e "${YELLOW}Running ALL auto-fixes (including unsafe) on $target...${NC}"
    uv run ruff check "$target" --fix --unsafe-fixes
}

ruff_preview() {
    local target="${1:-.}"
    echo -e "${BLUE}Previewing fixes for $target...${NC}"
    uv run ruff check "$target" --fix --diff
}

# Check Commands
ruff_check() {
    local target="${1:-.}"
    echo -e "${BLUE}Checking $target...${NC}"
    uv run ruff check "$target"
}

ruff_count() {
    local target="${1:-.}"
    echo -e "${BLUE}Counting errors in $target...${NC}"
    uv run ruff check "$target" 2>&1 | grep "Found" | grep -oE "[0-9]+ error" || echo "No errors found!"
}

# Specific error type checks
ruff_complexity() {
    local target="${1:-.}"
    echo -e "${BLUE}Checking complexity issues in $target...${NC}"
    uv run ruff check "$target" --select C901,PLR0912,PLR0915
}

ruff_security() {
    local target="${1:-.}"
    echo -e "${BLUE}Checking security issues in $target...${NC}"
    uv run ruff check "$target" --select S
}

ruff_pytest() {
    local target="${1:-.}"
    echo -e "${BLUE}Checking pytest-specific issues in $target...${NC}"
    uv run ruff check "$target" --select PT,B011
}

# Helper to show available commands
ruff_help() {
    echo -e "${GREEN}Available Ruff Commands:${NC}"
    echo -e "${BLUE}Analysis:${NC}"
    echo "  ruff_analyze [path]     - Analyze and save errors to JSON"
    echo "  ruff_summary           - Show error count by type"
    echo "  ruff_by_file           - Show errors by file"
    echo "  ruff_hot_files         - Show top 10 files with most errors"
    echo "  ruff_show CODE         - Show examples of specific error"
    echo "  ruff_find_pattern PAT  - Find errors matching pattern"
    echo ""
    echo -e "${BLUE}Fixing:${NC}"
    echo "  ruff_autofix [path]    - Run safe auto-fixes"
    echo "  ruff_unsafe_fix [path] - Run all fixes (including unsafe)"
    echo "  ruff_preview [path]    - Preview what would be fixed"
    echo ""
    echo -e "${BLUE}Checking:${NC}"
    echo "  ruff_check [path]      - Run ruff check"
    echo "  ruff_count [path]      - Count total errors"
    echo "  ruff_complexity [path] - Check complexity issues"
    echo "  ruff_security [path]   - Check security issues"
    echo "  ruff_pytest [path]     - Check pytest-specific issues"
}

echo -e "${GREEN}Ruff tools loaded! Type 'ruff_help' for available commands.${NC}"