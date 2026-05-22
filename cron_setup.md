# Cron Setup — Life System Orchestrator

Two cron jobs are required:

| Job | Schedule | Command |
|-----|----------|---------|
| EOD trigger | 23:30 daily (user timezone) | `python -m orchestrator eod` |
| Health ping | 12:00 daily | `python -m orchestrator health` |

---

## Option A: Local Unix / macOS (`crontab -e`)

Open your crontab:

```bash
crontab -e
```

Add the two entries below. Replace `/path/to/project` with your actual project root, and adjust the time offset if your system clock is not in the same timezone as `TIMEZONE` in your `.env`.

```cron
# Life System — EOD trigger at 23:30 local time
30 23 * * * cd /path/to/project && export $(cat .env | xargs) && python -m orchestrator eod >> /path/to/project/logs/eod.log 2>&1

# Life System — Supabase keep-alive health ping at 12:00
0 12 * * * cd /path/to/project && export $(cat .env | xargs) && python -m orchestrator health >> /path/to/project/logs/health.log 2>&1
```

**Notes:**
- `cd /path/to/project` ensures Python finds the `orchestrator` package.
- `export $(cat .env | xargs)` injects env vars from your `.env` file.
- Logs are appended to `logs/eod.log` and `logs/health.log`; create the `logs/` directory first.
- If your system clock is UTC but your timezone is `America/New_York` (UTC-5), schedule EOD at `30 04 * * *` (04:30 UTC = 23:30 EST).

Create the logs directory:

```bash
mkdir -p /path/to/project/logs
```

Verify cron is running:

```bash
crontab -l
```

---

## Option B: GitHub Actions (cloud-hosted cron, free tier)

Create `.github/workflows/life_system_cron.yml` in your repository:

```yaml
name: Life System Cron

on:
  schedule:
    # EOD trigger: 23:30 America/New_York = 04:30 UTC (UTC offset -5; adjust for DST)
    - cron: "30 4 * * *"
    # Health ping: 12:00 UTC daily
    - cron: "0 12 * * *"
  workflow_dispatch: {}   # allow manual trigger from GitHub UI

jobs:
  orchestrator:
    runs-on: ubuntu-latest
    steps:
      - name: Checkout
        uses: actions/checkout@v4

      - name: Set up Python
        uses: actions/setup-python@v5
        with:
          python-version: "3.11"

      - name: Install dependencies
        run: pip install -r requirements.txt

      - name: Determine which flow to run
        id: flow
        run: |
          MINUTE=$(date -u +"%M")
          HOUR=$(date -u +"%H")
          if [ "$HOUR" = "04" ] && [ "$MINUTE" = "30" ]; then
            echo "command=eod" >> $GITHUB_OUTPUT
          else
            echo "command=health" >> $GITHUB_OUTPUT
          fi

      - name: Run orchestrator
        env:
          SUPABASE_URL: ${{ secrets.SUPABASE_URL }}
          SUPABASE_SERVICE_KEY: ${{ secrets.SUPABASE_SERVICE_KEY }}
          GROQ_API_KEY: ${{ secrets.GROQ_API_KEY }}
          GROQ_MODEL_ID: ${{ secrets.GROQ_MODEL_ID }}
          TIMEZONE: ${{ secrets.TIMEZONE }}
          LOG_LEVEL: INFO
        run: python -m orchestrator ${{ steps.flow.outputs.command }}
```

**GitHub Secrets setup:**

Go to your repository → Settings → Secrets and variables → Actions → New repository secret.

Add each of these secrets:

| Secret name | Value |
|-------------|-------|
| `SUPABASE_URL` | Your Supabase project URL |
| `SUPABASE_SERVICE_KEY` | Supabase service role key |
| `GROQ_API_KEY` | Groq API key |
| `GROQ_MODEL_ID` | e.g. `llama3-8b-8192` |
| `TIMEZONE` | e.g. `America/New_York` |

**DST note:** GitHub Actions cron runs on UTC. If you're in a DST-observing timezone, you'll need to update the cron schedule twice a year, or use a time-zone-aware scheduling service like [Zuplo Cron](https://zuplo.com) or AWS EventBridge.

---

## Verifying the health ping keeps Supabase alive

Supabase free-tier projects pause after 7 days of inactivity. The 12:00 UTC daily health ping prevents this.

To confirm it's working over a 7-day test period:

1. Enable the cron (either method above).
2. After 7 days, verify your Supabase project is still active in the Supabase dashboard.
3. Check `run_history.json` for 7 consecutive `health` entries with `"success": true`.

```bash
grep '"flow": "health"' orchestrator/run_history.json | tail -7
```
