@echo off
REM Runs the Celery worker that executes automation jobs.
REM
REM IMPORTANT (Windows): the default "prefork" worker pool needs
REM os.fork(), which Windows doesn't have - so we use --pool=solo
REM instead. That's fine here since CELERY_WORKER_CONCURRENCY=1 already
REM restricts the worker to one job at a time anyway (FacebookRecoveryBot
REM opens a visible browser window, so jobs must run one-at-a-time, not
REM in parallel).
REM
REM This must be run on a machine with an active desktop session,
REM logged in, since the browser window is not headless.
REM
REM Uses the project's venv explicitly (not just "celery" off PATH) so it
REM always runs with the same interpreter/packages as `manage.py runserver`,
REM instead of possibly resolving to some other Python install on PATH.
REM
REM Also explicitly clears PLAYWRIGHT_BROWSERS_PATH: some terminals (e.g.
REM Cursor's integrated terminal / its agent tool shells) inject this var
REM pointing at a temp sandbox cache that doesn't have a real Chromium
REM install, which makes Playwright fail with "Executable doesn't exist"
REM even though the real browser is installed in the default location.
REM Clearing it here forces Playwright back to its default cache
REM (%LOCALAPPDATA%\ms-playwright) regardless of what launched this script.
set PLAYWRIGHT_BROWSERS_PATH=
cd /d "%~dp0pull_data"
"C:\Users\Lenovo\Envs\pull_data\Scripts\celery.exe" -A core worker --pool=solo --loglevel=info
