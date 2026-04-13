#!/bin/bash
#
# Test Fetcher Modules
#

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

echo "==================================="
echo "  Testing Fetcher Modules          "
echo "==================================="

# Test arxiv-fetcher
echo ""
echo "[1/3] Testing arxiv-fetcher..."
python skills/arxiv-fetcher/scripts/fetch_arxiv.py cs.AI,cs.LG

# Test database
echo ""
echo "[2/3] Testing database..."
python skills/storage-helper/scripts/db_ops.py init

# Test journal-fetcher (if feedparser is installed)
echo ""
echo "[3/3] Testing journal-fetcher..."
python -c "
import sys
sys.path.insert(0, 'skills/journal-fetcher/scripts')
try:
    import feedparser
    rss_url = 'https://www.nature.com/nature-machine-intelligence/rss'
    feed = feedparser.parse(rss_url)
    print(f'Nature Machine Intelligence: {len(feed.entries)} papers fetched')
    if feed.entries:
        print(f'  Latest: {feed.entries[0].title[:50]}...')
except Exception as e:
    print(f'Error: {e}')
"

echo ""
echo "==================================="
echo "  Tests Complete                   "
echo "==================================="
