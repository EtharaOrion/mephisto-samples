#!/bin/bash
set -e

LIST_MODE=0
DETAILS_MODE=0
for arg in "$@"; do
    case "$arg" in
        --list|-l) LIST_MODE=1 ;;
        --details|-d) DETAILS_MODE=1 ;;
        -h|--help)
            echo "Usage: sforge-submit [OPTIONS]"
            echo ""
            echo "Submit current code to the judge server for evaluation."
            echo "Results include score, pass rate, and a summary of findings."
            echo ""
            echo "Options:"
            echo "  --list, -l      List all previous submissions and scores for this run"
            echo "  --details, -d   Submit and show detailed per-test results (triggers a new submission)"
            echo "  -h, --help      Show this help message"
            exit 0
            ;;
        *)
            echo "ERROR: Unknown option: $arg" >&2
            echo "Run 'sforge-submit --help' for usage." >&2
            exit 1
            ;;
    esac
done

JUDGE_URL="${SFORGE_JUDGE_URL}"
TOKEN="${SFORGE_TOKEN}"
PATCH_DIR="${SFORGE_PATCH_DIR:-$(pwd)}"
STATE_FILE="/tmp/sforge_state.json"

if [ -z "$JUDGE_URL" ]; then
    echo "ERROR: SFORGE_JUDGE_URL not set" >&2
    exit 1
fi
if [ -z "$TOKEN" ]; then
    echo "ERROR: SFORGE_TOKEN not set" >&2
    exit 1
fi

if [ "$LIST_MODE" -eq 1 ]; then
    HIST=$(curl -s -m 30 "$JUDGE_URL/api/v1/history?token=$TOKEN")
    if [ -z "$HIST" ]; then
        echo "ERROR: No response from judge server" >&2
        exit 1
    fi
    BEST_RATE=$(echo "$HIST" | jq -r '.best_pass_rate // 0')
    BEST_SCORE=$(echo "$HIST" | jq -r '.best_score // "N/A"')
    COUNT=$(echo "$HIST" | jq -r '.entries | length')
    echo ""
    echo "========================================"
    echo "  Submission History"
    echo "  Total submissions: $COUNT"
    echo "  Best pass rate: $(jq -n --argjson r "$BEST_RATE" '$r * 100 | . * 10 | floor / 10')%"
    if [ "$BEST_SCORE" != "N/A" ] && [ "$BEST_SCORE" != "null" ]; then
        echo "  Best score: $BEST_SCORE"
    fi
    echo "========================================"
    echo ""
    if [ "$COUNT" -gt 0 ]; then
        printf "  %-14s %-10s %-8s %-12s %-10s %s\n" "ROUND" "STATUS" "VALID" "PASS_RATE" "SCORE" "SUMMARY"
        printf "  %-14s %-10s %-8s %-12s %-10s %s\n" "-----" "------" "-----" "---------" "-----" "-------"
        echo "$HIST" | jq -r '.entries[] | select(.type == "submission") |
            "  " +
            ((.round // "-") | . + " " * ([14 - length, 0] | max)) + " " +
            ((.status // "-") | . + " " * ([10 - length, 0] | max)) + " " +
            (if .valid == false then "no" else "yes" end | . + " " * ([8 - length, 0] | max)) + " " +
            (if .pass_rate != null then (.pass_rate * 100 * 10 | floor / 10 | tostring + "%") else "-" end | . + " " * ([12 - length, 0] | max)) + " " +
            (if .score != null then (.score | tostring) else "-" end | . + " " * ([10 - length, 0] | max)) + " " +
            ((.summary // "-") | if length > 40 then .[:37] + "..." else . end)'
    fi
    echo ""
    exit 0
fi

# ── Archive ──

cd "$PATCH_DIR"
ARCHIVE_FILE=$(mktemp --suffix=.tar.gz)
TAR_PATHS="${SFORGE_SUBMIT_PATHS:-.}"
if [ -n "${SFORGE_SUBMIT_PATHS:-}" ]; then
    EXISTING_PATHS=""
    for p in $SFORGE_SUBMIT_PATHS; do
        [ -e "$p" ] && EXISTING_PATHS="$EXISTING_PATHS $p"
    done
    TAR_PATHS="${EXISTING_PATHS# }"
fi
if [ -z "$TAR_PATHS" ]; then
    tar czf "$ARCHIVE_FILE" --files-from /dev/null
else
    tar czf "$ARCHIVE_FILE" --exclude='.git' ${SFORGE_SUBMIT_EXCLUDE_FLAGS:-} $TAR_PATHS
fi
ARCHIVE_SIZE=$(wc -c < "$ARCHIVE_FILE")

echo ""
echo "========================================"
echo "  Submitting for evaluation"
echo "  Archive size: $ARCHIVE_SIZE bytes"
echo "  Waiting for test results..."
echo "========================================"
echo ""

# ── Submit + poll ──

HTTP_CODE=$(curl -s -o /tmp/_submit_resp.json -w '%{http_code}' -m 120 -X POST "$JUDGE_URL/api/v1/submit" \
    -F "token=$TOKEN" \
    -F "archive=@$ARCHIVE_FILE")
rm -f "$ARCHIVE_FILE"
SUBMIT_RESP=$(cat /tmp/_submit_resp.json)

if [ "$HTTP_CODE" = "429" ]; then
    DETAIL=$(echo "$SUBMIT_RESP" | jq -r '.detail // empty')
    if echo "$DETAIL" | grep -qi "budget\|exhausted"; then
        echo "SUBMISSION LIMIT REACHED: $DETAIL" >&2
        echo "$DETAIL"
    else
        echo "COOLDOWN: $DETAIL" >&2
        echo "$DETAIL"
    fi
    exit 1
fi

SUBMISSION_ID=$(echo "$SUBMIT_RESP" | jq -r '.submission_id // empty')
ROUND_ID=$(echo "$SUBMIT_RESP" | jq -r '.round_id // empty')
REMAINING=$(echo "$SUBMIT_RESP" | jq -r '.remaining_submissions // empty')
if [ -z "$SUBMISSION_ID" ]; then
    echo "ERROR: Failed to submit to judge server (HTTP $HTTP_CODE)" >&2
    echo "$SUBMIT_RESP" >&2
    exit 1
fi

if [ -n "$ROUND_ID" ]; then
    if [ -n "$REMAINING" ] && [ "$REMAINING" != "null" ]; then
        echo "  Round: $ROUND_ID  (remaining submissions: $REMAINING)"
    else
        echo "  Round: $ROUND_ID"
    fi
    echo ""
fi

for _ in $(seq 1 720); do
    sleep 10
    RESULT=$(curl -s -m 30 "$JUDGE_URL/api/v1/result/$SUBMISSION_ID" 2>/dev/null || true)
    STATUS=$(echo "$RESULT" | jq -r '.status // empty')
    if [ "$STATUS" = "completed" ] || [ "$STATUS" = "error" ]; then
        break
    fi
done

STATUS=$(echo "$RESULT" | jq -r '.status // empty')
if [ "$STATUS" != "completed" ] && [ "$STATUS" != "error" ]; then
    echo "ERROR: Evaluation timed out or judge unreachable" >&2
    exit 1
fi

# ── Parse + update display cache + print ──

TS=$(date +%s)
ERROR_MSG=$(echo "$RESULT" | jq -r '.error // empty')

if [ -n "$ERROR_MSG" ]; then
    CURRENT_RATE=0
    CURRENT_SCORE="null"
    PASSED=0
    TOTAL=0
    FAILED=0
else
    REPORT=$(echo "$RESULT" | jq -r '.report')
    PASSED=$(echo "$REPORT" | jq -r '.passed')
    TOTAL=$(echo "$REPORT" | jq -r '.total_tests')
    FAILED=$(echo "$REPORT" | jq -r '.failed')
    CURRENT_RATE=$(echo "$REPORT" | jq -r '.pass_rate')
    CURRENT_SCORE=$(echo "$REPORT" | jq -r '.score // null')
    VALID=$(echo "$REPORT" | jq -r '.valid // true')
    SUMMARY=$(echo "$REPORT" | jq -r '.summary // empty')
fi

# Update local state file (display-only cache — not used for final scoring)
if [ ! -f "$STATE_FILE" ]; then
    echo '{"best_pass_rate": 0, "best_score": null, "best_round": "", "submissions": []}' > "$STATE_FILE"
fi
TMP=$(mktemp)
jq --arg round "${ROUND_ID:-unknown}" \
   --argjson ts "$TS" \
   --argjson rate "$CURRENT_RATE" \
   --argjson score "$CURRENT_SCORE" \
   '
   .submissions += [{kind: "agent", round: $round, at: $ts, pass_rate: $rate, score: $score}]
   | if $rate > (.best_pass_rate // 0) then
       .best_pass_rate = $rate | .best_round = $round | .best_score = $score
     else . end
   ' "$STATE_FILE" > "$TMP" && mv "$TMP" "$STATE_FILE"

if [ -n "$ERROR_MSG" ]; then
    echo "========================================"
    echo "  ${ROUND_ID:-submission}: ERROR"
    echo "  $ERROR_MSG"
    echo "========================================"
else
    echo "========================================"
    echo "  ${ROUND_ID:-submission} Results"
    echo "========================================"
    if [ "$VALID" = "false" ]; then
        echo "  Valid:       no"
    fi
    if [ "$CURRENT_SCORE" != "null" ]; then
        echo "  Score:       $CURRENT_SCORE"
    fi
    if [ "$TOTAL" -gt 0 ] 2>/dev/null; then
        PASS_PCT=$(jq -n --argjson r "$CURRENT_RATE" '$r * 100 | . * 10 | floor / 10')
        echo "  Pass rate:   ${PASS_PCT}%"
        echo "  Passed:      $PASSED/$TOTAL"
    fi
    if [ -n "$SUMMARY" ]; then
        echo ""
        echo "  Summary:"
        echo "    $SUMMARY"
    fi
    # Show metrics if present
    METRICS=$(echo "$REPORT" | jq -r '.metrics // empty')
    if [ -n "$METRICS" ] && [ "$METRICS" != "{}" ] && [ "$METRICS" != "null" ]; then
        echo ""
        echo "  Metrics:"
        echo "$REPORT" | jq -r '.metrics | to_entries[] | "    \(.key): \(.value)"'
    fi
    echo ""
    # Show failed items (from details if available, else from test_details)
    DETAIL_FAILURES=$(echo "$REPORT" | jq -r '[.details[]? | select(.status != "PASSED")] | length')
    if [ "$DETAIL_FAILURES" -gt 0 ] 2>/dev/null; then
        echo "  Failed checks:"
        echo "$REPORT" | jq -r '.details[] | select(.status != "PASSED") | .name' | head -20 | while read -r t; do echo "    - $t"; done
        if [ "$DETAIL_FAILURES" -gt 20 ] 2>/dev/null; then
            echo "    ... and $((DETAIL_FAILURES - 20)) more"
        fi
    else
        FAILED_TESTS=$(echo "$REPORT" | jq -r '.test_details[]? | select(.status != "PASSED") | .name')
        if [ -n "$FAILED_TESTS" ]; then
            echo "  Failed tests:"
            echo "$FAILED_TESTS" | head -20 | while read -r t; do echo "    - $t"; done
        else
            if [ "$TOTAL" -gt 0 ] 2>/dev/null; then
                echo "  All tests passed!"
            fi
        fi
    fi
    # Show full details if --details flag
    if [ "$DETAILS_MODE" -eq 1 ]; then
        HAS_DETAILS=$(echo "$REPORT" | jq -r '.details | length')
        if [ "$HAS_DETAILS" -gt 0 ] 2>/dev/null; then
            echo ""
            echo "  Details:"
            echo "$REPORT" | jq -r '.details[] | "    [\(.status)] \(.name)\(if .message then ": " + .message else "" end)"'
        fi
    fi
    echo "========================================"
    echo ""
fi
