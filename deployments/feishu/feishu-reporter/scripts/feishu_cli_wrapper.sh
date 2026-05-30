#!/bin/bash
#
# Feishu CLI Wrapper for PaperFlow
#

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
CONFIG_FILE="$SCRIPT_DIR/../../.env"

# Load environment variables
if [ -f "$CONFIG_FILE" ]; then
    export $(cat "$CONFIG_FILE" | grep -v '^#' | xargs)
fi

# Send text message
send_text() {
    local user_id="$1"
    local text="$2"

    lark im message send --user-id "$user_id" --text "$text"
}

# Send card message
send_card() {
    local user_id="$1"
    local card_file="$2"

    lark im message send --user-id "$user_id" --interactive "$(<"$card_file")"
}

# Create doc
create_doc() {
    local title="$1"
    local content="$2"
    local folder_id="${3:-}"

    if [ -n "$folder_id" ]; then
        lark docx create --title "$title" --folder "$folder_id" --content "$content"
    else
        lark docx create --title "$title" --content "$content"
    fi
}

# Get user info
get_user_info() {
    local user_id="$1"

    lark contact user get --user-id "$user_id"
}

# Parse command
case "$1" in
    send_text)
        send_text "$2" "$3"
        ;;
    send_card)
        send_card "$2" "$3"
        ;;
    create_doc)
        create_doc "$2" "$3" "$4"
        ;;
    get_user_info)
        get_user_info "$2"
        ;;
    *)
        echo "Usage: $0 {send_text|send_card|create_doc|get_user_info}"
        exit 1
        ;;
esac
