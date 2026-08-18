#### Python Version

python version 3.14

#### Install Package > go to requirement folder and run in command prompt:
pip install -r base.txt

#### Once you pip installed the base.txt remember need to add:
1) playwright install
2) playwright install chromium

fix
To setup database
#### Postgres Database

**For Windows**
```sql
psql -U postgres -h localhost
CREATE DATABASE pull_data_db;
CREATE USER pull_data WITH PASSWORD '2+PJh#&?';
ALTER ROLE pull_data SET client_encoding TO 'utf8';
ALTER ROLE pull_data SET default_transaction_isolation TO 'read committed';
ALTER ROLE pull_data SET timezone TO 'UTC';
GRANT ALL PRIVILEGES ON DATABASE pull_data_db TO pull_data;
\c pull_data_db;
ALTER SCHEMA public OWNER TO pull_data;
GRANT ALL ON SCHEMA public TO pull_data;
\q
```

**For Linux**
```sql
psql postgres
CREATE DATABASE pull_data_db;
CREATE USER pull_data WITH PASSWORD '2+PJh#&?';
ALTER ROLE pull_data SET client_encoding TO 'utf8';
ALTER ROLE pull_data SET default_transaction_isolation TO 'read committed';
ALTER ROLE pull_data SET timezone TO 'UTC';
GRANT ALL PRIVILEGES ON DATABASE pull_data_db TO pull_data;
\c pull_data_db;
ALTER SCHEMA public OWNER TO pull_data;
GRANT ALL ON SCHEMA public TO pull_data;
\q
```

For localhost setup

    git clone 

For sorl-thumbnail

    python manage.py makemigrations thumbnail
    python manage.py migrate


### RUN COMMANDS FOR THIS PROJECT (SYNC COUNTRIES)

Our SMS system is powered by a "Hub" architecture. When syncing countries, you must specify which provider to sync from. If the provider's API requires authentication, you must provide your API Key.

**Sync Hero SMS** (No API Key required)
```bash
python manage.py sync_countries --provider hero-sms
```

**Sync ClaudeOTP** (API Key required)
```bash
python manage.py sync_countries --provider claude-otp --api-key YOUR_CLOUDEOTP_API_KEY
```

### ADDING A NEW SMS PROVIDER

To add a new SMS provider to the system, follow these 3 simple steps:

1. **Create the Provider Class**
   Create a new file in `core/services/providers/` (e.g., `twilio_client.py`).
   Your class must inherit from `SMSProviderBase` and implement all abstract methods:
   - `get_balance()`
   - `get_countries()`
   - `get_number()`
   - `get_status()`
   - `set_status()`
   - `cancel_number()`
   - `confirm_number()`
   - `wait_for_otp()`

2. **Register in the Hub**
   Open `core/services/sms_hub.py` and import your new class.
   Add it to the `PROVIDER_MAP` dictionary using a URL-friendly slug:
   ```python
   PROVIDER_MAP = {
       "hero-sms": HeroSMSClient,
       "claude-otp": ClaudeOTPClient,
       "twilio": TwilioClient, # Your new provider
   }
   ```

3. **Sync the Countries**
   Run the sync command for your new provider to pull its countries into the database:
   ```bash
   python manage.py sync_countries --provider twilio --api-key YOUR_TWILIO_KEY
   ```

Need to setup memcached for sorl-thumbnail to work (for mac)

    brew install memcached

    # change [version] to the memcached version
    cp /usr/local/Cellar/memcached/[version]/homebrew.mxcl.memcached.plist ~/Library/LaunchAgents/

    # tell launchd to start
    launchctl load -w ~/Library/LaunchAgents/homebrew.mxcl.memcached.plist


### RUNNING AUTOMATION JOBS (DOCKER + REDIS + CELERY)

Automation jobs (started from the dashboard's "Customize Automation Job" page) run in the
background via Celery, using Redis as the broker/result backend. `FacebookRecoveryBot`
launches a **visible** (non-headless) browser, so:

- The Celery worker must run on a machine with an active, logged-in desktop session.
- Only **one** job runs at a time, on purpose (`CELERY_WORKER_CONCURRENCY = 1` in
  `core/settings/base.py`) — running multiple visible browser sessions in parallel risks
  Facebook rate-limiting/flagging your IP from bursty concurrent login attempts. Extra jobs
  simply queue up and run automatically, one after another.

**1) Install Docker Desktop**

Download from https://www.docker.com/products/docker-desktop/ and install it.

- On Windows, Docker Desktop needs WSL2. If it fails to start with a virtualization error,
  open an **elevated** (Run as administrator) PowerShell and run:
  ```powershell
  wsl --install
  ```
  then reboot and try opening Docker Desktop again.

**2) Start Redis**

A `docker-compose.yml` at the project root defines a Redis service on `127.0.0.1:6379`
(matching the default `CELERY_BROKER_URL`/`CELERY_RESULT_BACKEND`, so no settings changes
are needed).

**For Windows**, just double-click (or run from a terminal):
```bash
run_redis.bat
```

**For Linux/Mac**, or manually on any OS, from the project root:
```bash
docker compose up -d redis
```

Verify it's running:
```bash
docker compose ps
docker exec pull_data_redis redis-cli ping
# should print: PONG
```

**3) Start the Celery worker**

The worker is what actually executes jobs (runs `FacebookRecoveryBot`). It must be left
running whenever you want jobs to be picked up.

**For Windows**, double-click (or run from a terminal):
```bash
run_worker.bat
```
This uses `--pool=solo` since Windows has no `os.fork()`, which the default "prefork" pool
needs. That's fine here since concurrency is capped at 1 anyway.

**For Linux/Mac**, from the `pull_data/` directory (where `manage.py` lives):
```bash
celery -A core worker --loglevel=info
```

**4) Use the dashboard**

With Redis and the worker both running, start a job from the "Customize Automation Job"
page as normal — it will be picked up by the worker automatically. If the worker isn't
running, jobs just sit as `pending` until you start it.

To check the worker is alive and connected without enqueuing anything:
```bash
celery -A core inspect ping
```

**Troubleshooting: "nothing shows up in the terminal / no browser opens when a job runs"**

This almost always means the job was picked up by a *different* worker process than the
one you're watching, not that anything is actually broken. Check for duplicate/orphaned
workers:
```bash
celery -A core status
```
This lists every worker currently connected to Redis. If you see more than one, or one
you don't recognize, find and stop the extras:
```powershell
Get-CimInstance Win32_Process -Filter "Name='celery.exe'" | Select-Object ProcessId, CommandLine
taskkill /PID <pid> /T /F
```
Always use `/T` (kills the whole process tree) — killing just the wrapper process without
`/T` can leave the actual worker running **orphaned**, with no visible console window,
silently still consuming jobs in the background. Once only one worker remains, start a
single fresh one (`run_worker.bat`) and watch that terminal.

Fixtures

    python manage.py -Xutf8 dumpdata tickets.EntryTicket --indent 4 > fixtures/tickets_entryticket.json
    python manage.py loaddata fixtures/tickets_entryticket.json --app tickets.EntryTicket

    If got non-ASCII character (Example Chinese Character), can run this:
    set PYTHONIOENCODING=UTF-8
    py manage.py dumpdata cms.News --indent 4 > fixtures/cms_news.json

#### NOTES:
Ensure you need to run the VPN while running the task (If you request South Africa numbers, then you need to run South Africa VPN)