# pull_data

Django dashboard that buys SMS numbers and runs Facebook recovery jobs in the background (Celery + Redis + Playwright).

If you have **never used Python or Django before**, start at Step 1 and follow in order. Do not skip steps.

---

## First-time setup (Windows)

These steps assume **Windows** (this project is commonly run with `py` / PowerShell / Command Prompt). Linux/Mac notes are included where they differ.

### Step 1 — Download and install Python 3.14

1. Go to https://www.python.org/downloads/ and download **Python 3.14**.
2. Run the installer.
3. **Important:** tick **Add python.exe to PATH** before you click Install.
4. Finish the installer, then **close and reopen** Command Prompt / PowerShell.

Check that it worked:

```powershell
py --version
```

You should see something like `Python 3.14.x`.

> On Linux/Mac use `python3 --version` instead of `py --version`.

### Step 2 — Install / verify pip

pip is Python's package installer. A normal Python 3.14 install already includes it.

```powershell
py -m pip --version
```

If that fails, bootstrap pip:

```powershell
py -m ensurepip --upgrade
py -m pip install --upgrade pip
```

### Step 3 — Install Git (needed to clone the project)

Download Git from https://git-scm.com/download/win and install it with the default options.

Check:

```powershell
git --version
```

### Step 4 — Install virtualenv + virtualenvwrapper (`mkvirtualenv`)

A virtual environment keeps this project's packages isolated from the rest of your PC.

```powershell
py -m pip install virtualenv virtualenvwrapper-win
```

**Close and reopen** Command Prompt / PowerShell so `mkvirtualenv` is on your PATH.

> On Linux/Mac:
>
> ```bash
> python3 -m pip install virtualenv virtualenvwrapper
> # then add virtualenvwrapper to your shell (see https://virtualenvwrapper.readthedocs.io/)
> ```

### Step 5 — Create the virtual environment

```powershell
mkvirtualenv pull_data
```

This creates the env at `%USERPROFILE%\Envs\pull_data` (for example `C:\Users\Lenovo\Envs\pull_data`).

Every time you open a new terminal to work on this project, activate it:

```powershell
workon pull_data
```

Your prompt should show `(pull_data)` at the start of the line. To leave the env later: `deactivate`.

### Step 6 — Get the project code

If you do not have the folder yet:

```powershell
git clone <YOUR_REPO_URL>
cd WD
```

If you already have the folder, just open a terminal in it:

```powershell
cd C:\Users\Lenovo\Desktop\Project\WD
workon pull_data
```

### Step 7 — Install Python packages

Still inside the `pull_data` virtualenv, from the **project root** (`WD/`):

```powershell
pip install -r requirements\base.txt
```

This installs Django, Celery, Playwright, psycopg2, and everything else listed in `requirements/base.txt`.

### Step 8 — Install Playwright browsers

Playwright needs a real Chromium browser for the recovery automation:

```powershell
playwright install
playwright install chromium
```

### Step 9 — Install PostgreSQL

The app does **not** use SQLite. You need PostgreSQL running locally.

1. Download PostgreSQL from https://www.postgresql.org/download/windows/
2. During install, remember the password you set for the `postgres` superuser.
3. Keep the default port **5432**.
4. After install, make sure `psql` works in a new terminal:

```powershell
psql --version
```

If `psql` is not found, add PostgreSQL's `bin` folder to PATH, e.g. `C:\Program Files\PostgreSQL\16\bin`.

### Step 10 — Create the database and user

Django is configured (in `pull_data/core/settings/base.py`) to connect as:

| Setting  | Value        |
|----------|--------------|
| Database | `pull_data_db` |
| User     | `pull_data`    |
| Password | `2+PJh#&?`     |
| Host     | `127.0.0.1`    |
| Port     | `5432`         |

**Windows**

```sql
psql -U postgres -h localhost
```

Then paste:

```sql
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

**Linux**

```sql
psql postgres
```

Then run the same SQL as above.

### Step 11 — Run database migrations

`manage.py` lives in the `pull_data/` folder, **not** the project root.

```powershell
cd pull_data
workon pull_data
py manage.py makemigrations thumbnail
py manage.py migrate
```

This creates all tables (users, jobs, countries, SMS providers, etc.).

### Step 12 — Create an admin login

```powershell
py manage.py createsuperuser
```

Enter a username, email, and password. You will use this to log in to the dashboard and Django admin.

### Step 13 — Start the website

From `pull_data/` with the virtualenv active:

```powershell
py manage.py runserver
```

Open a browser at http://127.0.0.1:8000/

Log in with the superuser you just created.

Leave this terminal running while you use the site.

### Step 14 — First country sync (required before jobs)

SMS providers each have their own country list. You must pull those lists into the database at least once before you can pick a country on a job.

Always run these from `pull_data/` with `workon pull_data` active.

**Hero SMS** (no API key):

```powershell
py manage.py sync_countries --provider hero-sms
```

**ClaudeOTP** (API key required — replace with your real key):

```powershell
py manage.py sync_countries --provider claude-otp --api-key YOUR_CLAUDEOTP_API_KEY
```

Do **not** run the `.py` file directly. Django management commands are invoked by name (`sync_countries`), not by file path.

---

## Weekly country sync (every Monday)

SMS providers add, rename, and remove countries. If you never re-sync, the dashboard country list goes stale (wrong IDs, missing countries, leftover names).

Run the same two commands **every Monday**.

### What to run

From `pull_data/` (where `manage.py` is):

```powershell
py manage.py sync_countries --provider hero-sms
py manage.py sync_countries --provider claude-otp --api-key YOUR_CLAUDEOTP_API_KEY
```

Replace `YOUR_CLAUDEOTP_API_KEY` with your ClaudeOTP key. Hero SMS does not need a key.

Optional flags:

- `--dry-run` — print what would be removed, without deleting anything
- `--no-prune` — only add/update countries, never delete stale mappings

### Windows — Task Scheduler (this is the Windows version of cron)

1. Open **Task Scheduler** (`taskschd.msc`).
2. **Create Task…** (not "Create Basic Task").
3. **General** tab:
   - Name: `pull_data weekly country sync`
   - Tick **Run whether user is logged on or not** if you want it unattended
   - Tick **Run with highest privileges**
4. **Triggers** tab → **New…**:
   - Begin the task: **On a schedule**
   - Settings: **Weekly**
   - Recur every: **1** week on **Monday**
   - Start time: `09:00` (or any time the PC is usually on)
5. **Actions** tab → **New…**:
   - Action: **Start a program**
   - Program/script: `C:\Users\Lenovo\Envs\pull_data\Scripts\python.exe`
     (change the username if yours is not `Lenovo`)
   - Add arguments (Hero SMS):
     ```
     manage.py sync_countries --provider hero-sms
     ```
   - Start in:
     ```
     C:\Users\Lenovo\Desktop\Project\WD\pull_data
     ```
6. Click **OK**, then **New…** again and add a **second action** for ClaudeOTP:
   - Same Program/script and Start in
   - Add arguments:
     ```
     manage.py sync_countries --provider claude-otp --api-key YOUR_CLAUDEOTP_API_KEY
     ```
7. **Conditions** tab: untick "Start the task only if the computer is on AC power" if this is a laptop.
8. Click **OK**. Windows may ask for your Windows password.

To test immediately: right-click the task → **Run**, then check the terminal/history and the Countries list in Django admin.

**Easier option:** a `sync_countries.bat` already lives at the project root. Open it, replace `YOUR_CLAUDEOTP_API_KEY` with your real key, then in Task Scheduler use a **single** action:

- Program/script: `C:\Users\Lenovo\Desktop\Project\WD\sync_countries.bat`
- Start in: `C:\Users\Lenovo\Desktop\Project\WD`

**Do not commit your real API key** into git. Keep the placeholder in the repo and only put the real key in your local copy.

### Linux / Mac — crontab

Edit crontab:

```bash
crontab -e
```

Add (runs 09:00 every Monday; `1` = Monday):

```cron
0 9 * * 1 /home/YOUR_USER/.virtualenvs/pull_data/bin/python /path/to/WD/pull_data/manage.py sync_countries --provider hero-sms
0 9 * * 1 /home/YOUR_USER/.virtualenvs/pull_data/bin/python /path/to/WD/pull_data/manage.py sync_countries --provider claude-otp --api-key YOUR_CLAUDEOTP_API_KEY
```

Use the full path to the virtualenv's `python`, not system `python`. Replace the API key and paths.

---

## Adding a new SMS provider

1. **Create the provider class** in `pull_data/core/services/providers/` (e.g. `twilio_client.py`).
   Inherit from `SMSProviderBase` and implement: `get_balance()`, `get_countries()`, `get_number()`, `get_status()`, `set_status()`, `cancel_number()`, `confirm_number()`, `wait_for_otp()`.

2. **Register it in the Hub** — `pull_data/core/services/sms_hub.py`:

   ```python
   PROVIDER_MAP = {
       "hero-sms": HeroSMSClient,
       "claude-otp": ClaudeOTPClient,
       "twilio": TwilioClient,  # your new provider
   }
   ```

3. **Sync countries** for the new provider:

   ```powershell
   py manage.py sync_countries --provider twilio --api-key YOUR_TWILIO_KEY
   ```

---

## Running automation jobs (Docker + Redis + Celery)

Jobs started from **Customize Automation Job** run in Celery, with Redis as the broker. `FacebookRecoveryBot` opens a **visible** (non-headless) browser, so:

- The Celery worker must run on a machine with an active, logged-in desktop session.
- Only **one** job runs at a time (`CELERY_WORKER_CONCURRENCY = 1`) so Facebook is less likely to flag bursty parallel logins. Extra jobs queue and run one after another.

### 1) Install Docker Desktop

Download from https://www.docker.com/products/docker-desktop/

On Windows, Docker needs WSL2. If it fails with a virtualization error, open an **elevated** (Run as administrator) PowerShell:

```powershell
wsl --install
```

Reboot, then open Docker Desktop again.

### 2) Start Redis

A `docker-compose.yml` at the project root exposes Redis on `127.0.0.1:6379` (matches the default Celery settings).

**Windows** — double-click (or run from the project root):

```powershell
run_redis.bat
```

**Linux/Mac**, or manually on any OS, from the project root:

```bash
docker compose up -d redis
```

Verify:

```powershell
docker compose ps
docker exec pull_data_redis redis-cli ping
# should print: PONG
```

### 3) Start the Celery worker

Leave the worker running whenever you want jobs to be picked up.

**Windows** — double-click (or run):

```powershell
run_worker.bat
```

This uses `--pool=solo` because Windows has no `os.fork()`. That is fine here because concurrency is already 1.

`run_worker.bat` points at `C:\Users\Lenovo\Envs\pull_data\Scripts\celery.exe`. If your Windows username or env name is different, edit that path.

**Linux/Mac**, from `pull_data/`:

```bash
celery -A core worker --loglevel=info
```

### 4) Use the dashboard

With Redis and the worker both running, start a job from **Customize Automation Job**. If the worker is not running, jobs stay `pending`.

Check the worker without enqueuing a job:

```powershell
celery -A core inspect ping
```

### Troubleshooting: nothing in the terminal / no browser when a job runs

Usually a **different** worker process picked up the job. Check for extras:

```powershell
celery -A core status
```

If you see more than one worker, stop the extras:

```powershell
Get-CimInstance Win32_Process -Filter "Name='celery.exe'" | Select-Object ProcessId, CommandLine
taskkill /PID <pid> /T /F
```

Always use `/T` (kills the whole process tree). Killing only the wrapper can leave an **orphaned** worker with no window, still eating jobs. Then start a single fresh worker (`run_worker.bat`) and watch that terminal.

---

## Memcached (Mac only, for sorl-thumbnail)

```bash
brew install memcached

# change [version] to the memcached version
cp /usr/local/Cellar/memcached/[version]/homebrew.mxcl.memcached.plist ~/Library/LaunchAgents/

launchctl load -w ~/Library/LaunchAgents/homebrew.mxcl.memcached.plist
```

---

## Fixtures

```powershell
py manage.py -Xutf8 dumpdata tickets.EntryTicket --indent 4 > fixtures/tickets_entryticket.json
py manage.py loaddata fixtures/tickets_entryticket.json --app tickets.EntryTicket
```

If there are non-ASCII characters (e.g. Chinese):

```powershell
set PYTHONIOENCODING=UTF-8
py manage.py dumpdata cms.News --indent 4 > fixtures/cms_news.json
```

---

## Notes

- Run a VPN that matches the country of the SMS number you request (e.g. South Africa numbers → South Africa VPN).
- Always `workon pull_data` before `pip`, `py manage.py`, `playwright`, or `celery`.
- `manage.py` commands must be run from the `pull_data/` directory.
