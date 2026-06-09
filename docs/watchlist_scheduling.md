# Watchlist Scheduling

Use `scripts/run_watchlist.py` to run intelligence watchlists without starting FastAPI.
The watchlist runner generates due-diligence style briefs, appends every run to a JSONL archive, and renders a Markdown report that can be reviewed manually.

## Runtime Paths

```bash
export PROJECT_DIR=/home/lison/Desktop/zhaoping
export INTELLIGENCE_ARCHIVE_PATH=/home/lison/Desktop/zhaoping/data/intelligence_archive.jsonl
mkdir -p "$PROJECT_DIR/data" "$PROJECT_DIR/reports" "$PROJECT_DIR/logs"
```

Keep archive and report paths local unless a separate retention and access-control policy exists.

## One-shot Run

```bash
cd /home/lison/Desktop/zhaoping
INTELLIGENCE_ARCHIVE_PATH=/home/lison/Desktop/zhaoping/data/intelligence_archive.jsonl \
conda run -n robot_agent python scripts/run_watchlist.py \
  --config config/watchlist.example.toml \
  --report reports/watchlist_latest.md
```

The command writes JSON to stdout, appends brief artifacts to the JSONL archive, and writes a Markdown report when `--report` is provided.

## Cron Example

Run every weekday at 08:30 local time:

```cron
30 8 * * 1-5 cd /home/lison/Desktop/zhaoping && INTELLIGENCE_ARCHIVE_PATH=/home/lison/Desktop/zhaoping/data/intelligence_archive.jsonl conda run -n robot_agent python scripts/run_watchlist.py --config config/watchlist.example.toml --report reports/watchlist_latest.md >> logs/watchlist_cron.log 2>&1
```

Create runtime directories first:

```bash
mkdir -p data reports logs
```

## Systemd User Service

`~/.config/systemd/user/zhaoping-watchlist.service`:

```ini
[Unit]
Description=Zhaoping intelligence watchlist run

[Service]
Type=oneshot
WorkingDirectory=/home/lison/Desktop/zhaoping
Environment=INTELLIGENCE_ARCHIVE_PATH=/home/lison/Desktop/zhaoping/data/intelligence_archive.jsonl
ExecStart=/home/lison/miniconda3/bin/conda run -n robot_agent python scripts/run_watchlist.py --config config/watchlist.example.toml --report reports/watchlist_latest.md
```

`~/.config/systemd/user/zhaoping-watchlist.timer`:

```ini
[Unit]
Description=Run Zhaoping intelligence watchlist on weekdays

[Timer]
OnCalendar=Mon..Fri 08:30
Persistent=true
Unit=zhaoping-watchlist.service

[Install]
WantedBy=timers.target
```

Enable and run:

```bash
mkdir -p data reports logs ~/.config/systemd/user
systemctl --user daemon-reload
systemctl --user enable --now zhaoping-watchlist.timer
systemctl --user start zhaoping-watchlist.service
systemctl --user status zhaoping-watchlist.service
systemctl --user list-timers zhaoping-watchlist.timer
journalctl --user -u zhaoping-watchlist.service -n 100
```

## Verification

Run once with a temporary archive to verify the command works without touching the default archive:

```bash
cd /home/lison/Desktop/zhaoping
INTELLIGENCE_ARCHIVE_PATH=/tmp/zhaoping_watchlist_verify.jsonl \
conda run -n robot_agent python scripts/run_watchlist.py \
  --config config/watchlist.example.toml \
  --report /tmp/zhaoping_watchlist_verify.md
test -s /tmp/zhaoping_watchlist_verify.jsonl
test -s /tmp/zhaoping_watchlist_verify.md
```

Run the same command twice when validating diff behavior. The first run should report `insufficient_history`; the second run should report `ready` for each unchanged watchlist item because two snapshots now exist.

If FastAPI is running, inspect the archive through the API:

```bash
curl 'http://localhost:8000/search/archive/recent?limit=5'
curl 'http://localhost:8000/search/archive/diff?artifact_type=brief&watchlist_name=机器人融资'
```

## Safety Notes

- Keep API keys in environment variables only; do not write secrets into watchlist config.
- The default federated search path plans and archives evidence candidates without bypassing login, paywalls, robots.txt, or access controls.
- Treat generated reports as research work products, not investment advice, legal advice, or final factual determinations.
- Review original sources before making hiring, investment, vendor, or competitive decisions from a generated brief.
