import logging
import re
import threading
import time
from django.conf import settings
from playwright.sync_api import sync_playwright, TimeoutError as PlaywrightTimeoutError, Error as PlaywrightError
from playwright_stealth import Stealth
from playwright_recaptcha import recaptchav2, recaptchav3
from playwright_recaptcha.recaptchav2.recaptcha_box import RecaptchaBox as _PWRecaptchaBox
from apps.jobs.models import AutomationJob, FlowAttempt
from apps.accounts.models import FacebookAccount
from core.services.sms_hub import get_sms_provider
from core.services.exceptions import SMSProviderError, SMSTimeoutError

logger = logging.getLogger(__name__)


def _case_insensitive_translations_pattern(translations):
    """
    Monkeypatch for playwright_recaptcha's RecaptchaBox._get_translations_pattern.

    The library matches reCAPTCHA button labels (e.g. "Verify"/"Skip"/"Next")
    against a fixed, case-sensitive regex built from its `translations.py`
    list (only "Verify", never "VERIFY"). Facebook renders these labels in
    all caps, so the library's own `verify_button` locator never matches -
    `_submit_tile_answers()` then calls `verify_button.click()`, which hangs
    for Playwright's full default timeout and raises, even though CapSolver
    already selected the correct tiles. Re-registering this as a
    case-insensitive match fixes verify/skip/next/checkbox detection for
    every language in the list, not just English, without having to fork
    the library.
    """
    escaped_translations = [re.escape(t) for t in translations]
    return re.compile(f'^({"|".join(escaped_translations)}).?$', re.IGNORECASE)


_PWRecaptchaBox._get_translations_pattern = staticmethod(_case_insensitive_translations_pattern)

class _JobRunConfig:
    """
    Duck-types a UserConfig (the shape get_sms_provider() and the rest of
    this bot expect) but resolves every value from the job's per-run
    overrides first, falling back to the user's saved UserConfig. This is
    the single place that implements the override-or-default resolution
    for the bot, mirroring the AutomationJob.effective_* properties used
    for display elsewhere.
    """
    def __init__(self, job):
        self.user = job.user
        self.sms_provider = job.effective_sms_provider
        self.sms_api_key = job.effective_sms_api_key
        self.default_country = job.effective_country
        self.max_price = job.effective_max_price
        self.default_password = job.effective_default_password
        self.max_attempts = job.effective_max_attempts

class FacebookRecoveryBot:
    def __init__(self, job_id: int):
        self.job = AutomationJob.objects.select_related(
            'user', 'user__userconfig', 'country', 'sms_provider',
        ).get(id=job_id)
        self.user = self.job.user
        # Per-run overrides on the job take priority over the user's saved
        # UserConfig defaults, so the same UserConfig can be reused for
        # different settings across separate jobs.
        self.config = _JobRunConfig(self.job)
        self.country = self.config.default_country
        self.target = self.job.effective_target_accounts
        # Hard limit on total attempts to prevent infinite loops - job
        # override, else the user's saved UserConfig, else a system default.
        self.max_attempts = self.config.max_attempts

    def start(self):
        logger.info(f"Starting Facebook Recovery Job {self.job.id} for user {self.user.username}")
        self.job.status = "running"
        self.job.save()
        
        provider = get_sms_provider(self.config)

        while self.job.successful_count < self.target and self.job.total_attempts < self.max_attempts:
            self.job.total_attempts += 1
            self.job.save()
            
            logger.info(f"Attempt {self.job.total_attempts}: Requesting number...")
            
            last_error = None
            attempt = None
            activation_id = None
            try:
                # 1. Get Number from SMS Provider
                # Get the mapping for the selected country (job override, or
                # the user's saved default) and provider
                mapping = self.country.provider_mappings.get(provider=self.config.sms_provider)
                number_data = provider.get_number(
                    mapping.provider_country_id, 
                    service="FACEBOOK", 
                    max_price=self.config.max_price
                )
                phone_number = number_data['phone']
                activation_id = number_data['activation_id']
                
                attempt = FlowAttempt.objects.create(
                    job=self.job,
                    phone_number=phone_number,
                    activation_id=activation_id,
                    status="failed" # Default to failed until it succeeds
                )
                
                # 2. Run the Playwright flow
                self._run_browser_flow(provider, attempt, phone_number, activation_id)
                
            except Exception as e:
                last_error = str(e)
                logger.error(f"Error during attempt: {last_error}")
                if attempt is not None:
                    # A number was already obtained and its FlowAttempt row
                    # already created before this error hit (e.g. the browser
                    # itself failed to launch, or context/browser cleanup in
                    # _run_browser_flow's `finally` raised) - release the
                    # number back to the provider instead of silently leaving
                    # it reserved/paid for, and record the error on the real
                    # attempt row instead of creating a second, orphaned one
                    # with no phone number attached.
                    self._cancel_number_safe(provider, activation_id)
                    attempt.status = "failed"
                    attempt.fail_reason = "other"
                    attempt.error_message = last_error
                    attempt.save()
                else:
                    # Getting a number failed before a FlowAttempt row could be
                    # created above, so record it here instead - otherwise this
                    # attempt would be invisible on the dashboard even though it
                    # counted towards total_attempts.
                    FlowAttempt.objects.create(
                        job=self.job,
                        status="failed",
                        fail_reason="other",
                        error_message=last_error,
                    )

            if last_error:
                self.job.error_message = last_error
                self.job.save(update_fields=["error_message"])

            # Small delay between attempts
            time.sleep(2)

        if self.job.successful_count >= self.target:
            self.job.status = "success"
            self.job.error_message = None
        elif self.job.successful_count > 0:
            self.job.status = "partial"
        else:
            self.job.status = "failed"
            
        from django.utils import timezone
        self.job.completed_at = timezone.now()
        self.job.save()
        logger.info(f"Job {self.job.id} finished with status {self.job.status}. Success: {self.job.successful_count}/{self.target}")

    def _get_button_by_names(self, page, names, timeout=None):
        for name in names:
            locator = page.get_by_role("button", name=re.compile(re.escape(name), re.I))
            if locator.count() > 0:
                return locator.first
        return None

    def _get_text_locator(self, page, texts):
        for text in texts:
            locator = page.get_by_text(re.compile(re.escape(text), re.I), exact=False)
            if locator.count() > 0:
                return locator.first
        return None

    def _fill_textbox_by_names(self, page, names, value):
        for name in names:
            locator = page.get_by_role("textbox", name=re.compile(re.escape(name), re.I))
            if locator.count() > 0:
                locator.first.fill(value)
                return True
        return False

    def _click_button_by_names(self, page, names, timeout=None):
        button = self._get_button_by_names(page, names, timeout=timeout)
        if button is None:
            return False
        try:
            button.click(timeout=timeout)
            return True
        except PlaywrightTimeoutError:
            # Button was found but never became actionable (e.g. stuck with
            # aria-disabled="true" while Facebook's JS finishes loading).
            # Treat this as "couldn't click" rather than crashing the whole flow.
            logger.warning(f"Timed out clicking button matching {names!r} (timeout={timeout}ms).")
            return False

    def _run_browser_flow(self, provider, attempt, phone_number, activation_id):
        with sync_playwright() as p:
            # --disable-notifications makes Chromium auto-deny every notification
            # permission request with no UI at all. Facebook's "Allow
            # www.facebook.com to send notifications?" prompt is a NATIVE
            # browser-chrome popup (not part of the page's DOM), so no
            # page.click()/get_by_role() selector can ever reach it - it would
            # otherwise sit there forever, blocking the page beneath it (e.g.
            # the new-password screen). This flag stops it from appearing at all.
            browser = p.chromium.launch(
                headless=False,  # Keep visible for now
                args=["--disable-notifications"],
            )
            # Force English so Facebook's UI (and, crucially, the Google
            # reCAPTCHA widget it embeds) renders in English. Facebook can
            # render pages in a local language (e.g. Indonesian, Filipino)
            # depending on the phone number's region, but the
            # playwright-recaptcha solver only recognizes reCAPTCHA button
            # labels ("Verify"/"Skip"/"Next") in a handful of languages, and
            # every button-name check in this file only lists a few languages
            # too - neither approach scales to the dozens of languages
            # Facebook can render across different countries. English is
            # always supported by both, so force it everywhere instead of
            # chasing translations country by country.
            context = browser.new_context(locale="en-US")
            # The Accept-Language header (set via `locale` above) is only a
            # hint - Facebook often decides the UI language from the phone
            # number's country/account settings instead, ignoring it. Its
            # `locale` cookie is what actually pins the UI language, so set
            # it explicitly before the first navigation.
            context.add_cookies([
                {"name": "locale", "value": "en_US", "domain": ".facebook.com", "path": "/"},
            ])
            page = context.new_page()
            
            # Apply stealth mode to avoid bot detection
            Stealth().apply_stealth_sync(page)

            capsolver_api_key = settings.CAPSOLVER_API_KEY

            try:
                # Wrap the entire flow in a recaptchav2 solver context so it captures
                # reCAPTCHA network tokens from the very first page navigation.
                with recaptchav2.SyncSolver(page, capsolver_api_key=capsolver_api_key) as recaptcha_solver:

                    # Step 1: Navigate to Facebook identify
                    logger.info("Navigating to Facebook Identify...")
                    page.goto("https://www.facebook.com/login/identify/?locale=en_US")

                    # Step 2: Fill in phone number and click Continue
                    if not self._fill_textbox_by_names(
                        page,
                        [
                            "Mobile number or email address",
                            "Nomor ponsel atau alamat email",
                            "Nomor telepon atau alamat email",
                        ],
                        phone_number,
                    ):
                        page.locator('input[type="text"], input[name="email"], input[name="phone"]').first.fill(phone_number)

                    self._click_button_by_names(page, ["Continue", "Lanjutkan", "Lanjut"], timeout=10000)

                    # Step 3: Handle post-identify flow (no account / multiple accounts / choose SMS / captcha)
                    if not self._handle_post_identify_flow(
                        page, capsolver_api_key, attempt, activation_id, provider, phone_number
                    ):
                        return

                    # Guard: Facebook can bounce back to the "Choose a way to log in"
                    # screen at various points (e.g. after a "Something went wrong.
                    # Please try again." retry), sometimes now offering ONLY
                    # "Continue with password" - which we have no way to satisfy.
                    if self._is_password_only_login_page(page):
                        logger.info("Only 'Continue with password' is offered for this number. Failing attempt.")
                        self._fail_attempt(
                            attempt, provider, activation_id, "password_prompt",
                            "Facebook only offered 'Continue with password' - no SMS/email code option available",
                        )
                        return

                    # Step 4: Handle "View notifications on other devices" screen
                    try:
                        page.wait_for_timeout(2000)
                        if self._click_button_by_names(page, ["Try another way", "Coba cara lain"], timeout=5000):
                            logger.info("Facebook wants device approval. Clicking 'Try another way'...")
                            page.wait_for_timeout(2000)
                            # After "Try another way", select SMS again if prompted
                            if self._is_choose_login_method_page(page):
                                if self._is_password_only_login_page(page):
                                    logger.info("Only 'Continue with password' is offered for this number. Failing attempt.")
                                    self._fail_attempt(
                                        attempt, provider, activation_id, "password_prompt",
                                        "Facebook only offered 'Continue with password' - no SMS/email code option available",
                                    )
                                    return

                                if not self._select_sms_and_continue(page, phone_number):
                                    logger.info("SMS login method not offered (or number mismatch) for this number. Failing attempt.")
                                    self._fail_attempt(
                                        attempt, provider, activation_id, "no_sms_option",
                                        "Facebook did not offer a matching 'Get code via SMS' option for this number",
                                    )
                                    return

                                if not self._solve_recaptcha_v2_if_present(
                                    page, capsolver_api_key, attempt, activation_id, provider
                                ):
                                    return
                    except PlaywrightTimeoutError:
                        pass

                    # Fallback for older recovery UI that sends SMS via reset_action
                    try:
                        page.click('button[name="reset_action"]', timeout=3000)
                    except PlaywrightTimeoutError:
                        pass

                    # Safety net: if we're still sitting on a login-method
                    # page that offers no way to get an SMS/email code (e.g.
                    # password-only), none of the button clicks above would
                    # have done anything and there is no "Get Code" button to
                    # find below either. Without this check, the flow would
                    # silently fall through into Step 5's up-to-10-minute OTP
                    # wait for a code Facebook was never asked to send,
                    # eventually failing with a misleading "timeout" reason
                    # instead of the real cause. Fail fast here instead.
                    if self._is_password_only_login_page(page):
                        logger.info("Only 'Continue with password' is offered for this number. Failing attempt.")
                        self._fail_attempt(
                            attempt, provider, activation_id, "password_prompt",
                            "Facebook only offered 'Continue with password' - no SMS/email code option available",
                        )
                        return
                    if self._is_no_sms_option_page(page):
                        logger.info("No SMS option is offered for this number. Failing attempt.")
                        self._fail_attempt(
                            attempt, provider, activation_id, "no_sms_option",
                            "Facebook did not offer an SMS code option for this number "
                            "(caught by pre-OTP-wait safety net)",
                        )
                        return
                    if not self._is_choose_login_method_page(page) and not self._has_recaptcha_v2(page):
                        # Neither a recognized login-method page nor a
                        # reCAPTCHA - if a "Get Code"-ish button matches
                        # below anyway (its name list includes generic
                        # fallbacks like "Continue"), we have no idea what
                        # it's actually about to click. Capture the page now,
                        # before that click, since this is exactly the blind
                        # spot that has been producing confusing downstream
                        # states in past runs.
                        self._dump_page_diagnostics(page, "pre-Step-4b: about to blindly click Get Code/Continue")

                    # Step 4b: Click "Get Code" / "Send Code" confirmation if shown
                    # After selecting SMS, Facebook shows a screen like:
                    # "We'll send a code to your number ending in XXXX" with a "Get Code" button
                    page.wait_for_timeout(1500)
                    get_code_clicked = self._click_button_by_names(page, [
                        "Get Code", "Dapatkan Kode",
                        "Send Code", "Kirim Kode",
                        "Send SMS", "Kirim SMS",
                        "Send", "Kirim",
                        "Continue", "Lanjutkan", "Lanjut",
                    ], timeout=5000)
                    if get_code_clicked:
                        logger.info("Clicked 'Get Code' confirmation button. Checking for reCAPTCHA...")
                        page.wait_for_timeout(1500)

                        # Step 4c: Solve reCAPTCHA if it pops up after "Get Code"
                        # Facebook sometimes shows "Help us confirm that it's you" with a CAPTCHA
                        if not self._solve_recaptcha_v2_if_present(
                            page, capsolver_api_key, attempt, activation_id, provider
                        ):
                            return

                        # After solving CAPTCHA, click "Next" to continue
                        self._click_button_by_names(page, [
                            "Next", "Lanjut", "Selanjutnya", "Continue", "Lanjutkan"
                        ], timeout=5000)
                        page.wait_for_timeout(1500)

                    # Step 5: Wait for OTP from SMS provider
                    # Phase 1: Wait up to 1 minute for the OTP to arrive
                    logger.info("Waiting for OTP from SMS provider (Phase 1 - 60s)...")
                    otp_code = None
                    try:
                        otp_code = provider.wait_for_otp(activation_id, poll_interval=5, max_attempts=12)
                    except SMSTimeoutError:
                        pass

                    # If nothing arrived, try clicking "Didn't get a code?" on the page
                    if not otp_code:
                        logger.info("No OTP after 60s. Trying to click 'Didn't get a code?'...")
                        resend_clicked = False
                        # Try as a button first
                        resend_clicked = self._click_button_by_names(page, [
                            "Resend code", "Kirim ulang kode",
                            "Send code again", "Kirim kode lagi",
                            "Resend", "Kirim ulang",
                        ], timeout=2000)
                        # Try as a text link (Facebook renders this as a link, not a button)
                        if not resend_clicked:
                            for link_text in [
                                "Didn't get a code?",
                                "Tidak menerima kode?",
                                "Tidak dapat kode?",
                            ]:
                                locator = page.get_by_text(link_text, exact=False)
                                if locator.count() > 0:
                                    locator.first.click()
                                    logger.info(f"Clicked resend link: '{link_text}'")
                                    resend_clicked = True
                                    break
                        page.wait_for_timeout(2000)


                    # Phase 2: Wait another 9 minutes (Phase 1 + Phase 2 = 10 minutes total)
                    if not otp_code:
                        logger.info("Waiting for OTP (Phase 2 - 540s)...")
                        try:
                            otp_code = provider.wait_for_otp(activation_id, poll_interval=5, max_attempts=108)
                        except SMSTimeoutError:
                            pass

                    if not otp_code:
                        logger.info("OTP Timeout after all retries. Moving to next number.")
                        self._fail_attempt(attempt, provider, activation_id, "timeout")
                        return

                    logger.info(f"Received OTP: {otp_code}")

                    # Step 6: Enter OTP code into the page. Facebook sometimes rejects the
                    # submission (shows an "incorrect code" error) even though we submitted
                    # the right code - e.g. the field didn't register the input properly.
                    # Retry once by re-typing and resubmitting before giving up.
                    otp_accepted = False
                    max_otp_submit_attempts = 2
                    for otp_submit_attempt in range(1, max_otp_submit_attempts + 1):
                        logger.info(f"Submitting OTP code (attempt {otp_submit_attempt}/{max_otp_submit_attempts}): {otp_code}")
                        if not self._fill_textbox_by_names(page, [
                            "Security code",
                            "Kode keamanan",
                            "Kode konfirmasi",
                            "Kode verifikasi",
                            "Enter code",
                            "Masukkan kode",
                        ], otp_code):
                            # Fallback to the classic input[name="n"] selector
                            page.locator('input[name="n"], input[type="text"]').first.fill(otp_code)

                        # Wait for Facebook's JS to enable the Continue button after field is filled
                        page.wait_for_timeout(1500)
                        self._click_button_by_names(page, ["Continue", "Lanjutkan", "Lanjut", "Kirim", "Submit"], timeout=10000)

                        # Fallback: old-style reset_action submit
                        try:
                            page.click('button[name="reset_action"]', timeout=3000)
                        except Exception:
                            pass

                        page.wait_for_timeout(2000)

                        if self._is_otp_error_shown(page):
                            logger.warning(f"Facebook rejected the OTP code on attempt {otp_submit_attempt}/{max_otp_submit_attempts}.")
                            continue

                        otp_accepted = True
                        break

                    if not otp_accepted:
                        logger.info("OTP code was rejected by Facebook after retrying. Moving to next number.")
                        self._fail_attempt(
                            attempt, provider, activation_id, "otp_rejected",
                            "Facebook kept rejecting the OTP code as incorrect/invalid after retrying",
                        )
                        return

                    # Step 7: Handle post-OTP screens (new password, "Save your login
                    # info?", turn-on-notifications, review recent logins, etc.) until
                    # we actually land on the Facebook home/feed page. We must NOT stop
                    # early here: some interstitial pages (e.g. the notification
                    # permission screen, which has "Allow"/"Don't Allow" buttons and can
                    # have "allow"/"disallow" in its URL) can otherwise be mistaken for
                    # a successful final landing page and cause us to extract cookies
                    # and close the browser too soon.
                    logger.info("After OTP submission. Advancing through any interstitial screens...")
                    current_url, password_was_set = self._advance_to_home_page(page, attempt, provider, activation_id)

                    # If an unrecoverable checkpoint (e.g. a 2FA authenticator app code
                    # we have no way to provide) was hit, the attempt has already been
                    # marked as failed - just move on to the next number.
                    if current_url is None:
                        return

                    # Step 8: Only treat this as a success once we've actually reached
                    # the logged-in Facebook home page.
                    if self._is_home_page(current_url):
                        logger.info(f"Successfully logged in! URL: {current_url}")
                        # Only record default_password if we actually set it on a
                        # "create a new password" screen. If Facebook logged us
                        # straight in without ever asking for a new password, the
                        # real password is unknown/unchanged - save blank instead
                        # of falsely claiming it's default_password.
                        saved_password = self.config.default_password if password_was_set else ""
                        self._save_success(context, attempt, saved_password)
                    else:
                        logger.warning(f"Login may have failed. Final URL: {current_url}")
                        self._cancel_number_safe(provider, activation_id)
                        attempt.status = "failed"
                        attempt.fail_reason = "other"
                        attempt.error_message = f"Unexpected final URL: {current_url}"
                        attempt.save()

            except Exception as e:
                # Use logger.exception() (not logger.error()) so the full traceback
                # is captured - this is often the only way to diagnose what actually
                # went wrong (e.g. a DB IntegrityError inside _save_success would
                # otherwise just look like a silently failed/closed browser).
                logger.exception(f"Playwright error: {str(e)}")
                # This is the catch-all for any unexpected error anywhere in the
                # flow (Steps 1 through the final URL check) - unlike the
                # explicit failure paths above (which go through _fail_attempt
                # and already cancel), nothing else has released this number
                # back to the provider yet, so do it here too.
                self._cancel_number_safe(provider, activation_id)
                attempt.status = "failed"
                attempt.fail_reason = "other"
                attempt.error_message = str(e)
                attempt.save()
            finally:
                context.close()
                browser.close()



    def _is_home_page(self, url: str) -> bool:
        """
        Returns True only when `url` looks like the actual, logged-in Facebook
        home/feed page - not an interstitial screen such as the new-password
        page, "Save your login info?", the notification permission prompt,
        checkpoint/review flows, etc. Those interstitial pages don't contain
        "login"/"identify" either, so checking for those alone isn't enough
        and can cause us to stop (and extract cookies) too early.
        """
        if "facebook.com" not in url:
            return False

        blocked_markers = [
            "login", "identify", "checkpoint", "recover",
            "save-device", "two_step_verification", "two_factor",
            "captcha", "notifications", "review", "save_login_info",
            "privacy_mutation_token", "help/", "policies",
        ]
        # Only inspect the part after the host so a marker never matches
        # "facebook.com" itself.
        path_and_query = url.split("facebook.com", 1)[-1].lower()
        return not any(marker in path_and_query for marker in blocked_markers)

    def _advance_to_home_page(self, page, attempt, provider, activation_id, max_attempts=6, per_step_timeout=8000):
        """
        Repeatedly resolves whatever interstitial screen Facebook shows after
        OTP submission (new password, notification permission, "Save your
        login info?", review recent devices, 2FA authenticator app prompt,
        etc.) until the page actually reaches the logged-in home feed, or we
        run out of attempts.

        Returns a `(final_url, password_was_set)` tuple, where `password_was_set`
        is True only if Facebook actually showed the "create a new password"
        screen and we filled/saved a new password on it. If it was never shown
        (e.g. the account already had a working password and Facebook logged
        us straight in), the caller should NOT record `default_password` as
        the account's password since it was never actually set.

        Returns `(None, False)` if an unrecoverable checkpoint was hit (e.g. a
        2FA authenticator app code we have no way to provide) - in that case
        the attempt has already been marked as failed.
        """
        password_was_set = False
        for i in range(max_attempts):
            try:
                page.wait_for_load_state('networkidle', timeout=per_step_timeout)
            except PlaywrightTimeoutError:
                pass

            current_url = page.url
            logger.info(f"Post-login step {i + 1}/{max_attempts}. URL: {current_url}")

            if self._is_home_page(current_url):
                return current_url, password_was_set

            # 2FA authenticator app code required (Google Authenticator, Duo
            # Mobile, etc.). We have no way to generate this code, so this
            # account can't be recovered - fail fast instead of getting stuck
            # clicking around, or worse, timing out on the whole flow.
            if self._is_authenticator_app_page(page):
                logger.info("2FA authenticator app code required. This account can't be recovered without it. Failing attempt.")
                self._fail_attempt(
                    attempt, provider, activation_id, "two_factor_required",
                    "Facebook asked for a 2FA authenticator app code, which we have no way to provide",
                )
                return None, False

            # New password page
            if page.locator('input[type="password"]').count() > 0:
                logger.info("New password page detected.")
                new_password = self.config.default_password or "DefaultPass123!"
                page.locator('input[type="password"]').first.fill(new_password)
                self._click_button_by_names(page, ["Continue", "Lanjutkan", "Save", "Simpan"], timeout=per_step_timeout)
                page.wait_for_timeout(1500)
                password_was_set = True
                continue

            # "Confirm/verify it's you" checkpoint - a review screen with a
            # Continue button and a disclaimer like "this can take up to a
            # few minutes". Just acknowledge it and move on; the account may
            # still be under async review afterwards, so we don't treat this
            # page itself as success or failure.
            if self._is_verify_its_you_page(page):
                logger.info("'Verify it's you' checkpoint detected. Clicking Continue...")
                self._click_button_by_names(page, ["Continue", "Lanjutkan", "Lanjut", "OK", "Oke"], timeout=per_step_timeout)
                page.wait_for_timeout(2000)
                continue

            # Any other known interstitial (notification permission - which has
            # "Allow"/"Don't Allow" buttons, "Save your login info?", review
            # recent logins, etc.). We prefer the "decline"-style buttons
            # (Not Now / Don't Allow / Block) so we don't need to grant any
            # extra permissions just to get past the screen.
            dismissed = self._click_button_by_names(
                page,
                [
                    "Skip", "Lewati",
                    "Not Now", "Nanti", "Tidak Sekarang",
                    "Don't Allow", "Jangan Izinkan", "Block", "Blokir",
                    "Continue", "Lanjutkan",
                    "OK", "Oke",
                    "Close", "Tutup",
                    "Allow", "Izinkan",
                    "Turn On", "Aktifkan",
                ],
                timeout=per_step_timeout,
            )
            if dismissed:
                page.wait_for_timeout(1500)
                continue

            # Last resort for interstitials rendered in a language none of
            # our text lists cover (Vietnamese, Thai, Filipino, etc. - there
            # are simply too many for Facebook's full language list to
            # enumerate by hand). Single-purpose checkpoint screens like
            # "verify it's you" have exactly one actionable button - if we
            # can find exactly one on the page, click it regardless of its
            # label; on these screens that's always the intended next step.
            if self._click_lone_prominent_button(page, timeout=per_step_timeout):
                logger.info("Clicked the page's only actionable button (language-independent fallback).")
                page.wait_for_timeout(1500)
                continue

            # Nothing to click and not home yet - give the page a moment in
            # case it's still redirecting, then check again.
            page.wait_for_timeout(2000)

        return page.url, password_was_set

    def _click_lone_prominent_button(self, page, timeout=None) -> bool:
        """
        Finds and clicks the single actionable button on the page, ignoring
        known persistent site-chrome widgets (e.g. the floating "Get Help"
        chat bubble present on many Facebook pages regardless of language).
        Only clicks when exactly one candidate remains, so this never risks
        guessing wrong on a page with multiple real choices.
        """
        widget_keywords = [
            "help", "hỗ trợ", "bantuan", "ayuda", "aide", "hilfe", "aiuto",
            "tolong", "tulong", "chat", "messenger", "support",
        ]
        try:
            buttons = page.get_by_role("button")
            count = buttons.count()
        except Exception:
            return False

        candidates = []
        for i in range(count):
            btn = buttons.nth(i)
            try:
                if not btn.is_visible() or not btn.is_enabled():
                    continue
                name = (btn.inner_text() or "").strip()
            except Exception:
                continue
            if not name or any(keyword in name.lower() for keyword in widget_keywords):
                continue
            candidates.append(btn)

        if len(candidates) != 1:
            return False

        try:
            candidates[0].click(timeout=timeout)
            return True
        except PlaywrightTimeoutError:
            return False

    def _is_verify_its_you_page(self, page) -> bool:
        """
        Detects Facebook's "confirm/verify it's you" review checkpoint,
        which shows a Continue button plus a disclaimer that the check can
        take some time (e.g. "This can take up to a few minutes").
        """
        heading_texts = [
            "confirm it's you",
            "verify it's you",
            "let's confirm it's you",
            "make sure it's really you",
            "help us confirm",
            "we just need to confirm",
            "konfirmasi bahwa ini anda",
            "pastikan ini benar anda",
            "bantu kami memastikan",
        ]
        for text in heading_texts:
            if page.get_by_text(re.compile(re.escape(text), re.I), exact=False).count() > 0:
                return True

        # Fallback: the characteristic "this may take a few minutes/seconds" disclaimer.
        disclaimer_texts = [
            "this can take up to",
            "this may take up to",
            "may take a few minutes",
            "hal ini dapat memakan waktu",
            "membutuhkan waktu hingga",
            "akan memakan waktu",
        ]
        for text in disclaimer_texts:
            if page.get_by_text(re.compile(re.escape(text), re.I), exact=False).count() > 0:
                return True

        return False

    def _is_authenticator_app_page(self, page) -> bool:
        """
        Detects Facebook's 2FA "open your authentication app" checkpoint
        (Google Authenticator, Duo Mobile, etc.), like:

            "Buka aplikasi autentikasi" / "Masukkan kode 6 digit untuk akun
            ini dari aplikasi autentikasi dua faktor yang Anda siapkan
            (seperti Duo Mobile atau Google Authenticator)."

        We have no access to the account owner's authenticator secret/app,
        so there's no way to generate this code - this account simply can't
        be recovered this way.
        """
        heading_texts = [
            "open your authentication app",
            "open authentication app",
            "buka aplikasi autentikasi",
            "enter the 6-digit code",
            "masukkan kode 6 digit",
        ]
        for text in heading_texts:
            if page.get_by_text(re.compile(re.escape(text), re.I), exact=False).count() > 0:
                return True

        app_mentions = [
            "google authenticator",
            "duo mobile",
            "authentication app",
            "authenticator app",
            "aplikasi autentikasi dua faktor",
            "two-factor authentication app",
        ]
        for text in app_mentions:
            if page.get_by_text(re.compile(re.escape(text), re.I), exact=False).count() > 0:
                return True

        return False

    def _cookies_to_string(self, cookies) -> str:
        """
        Formats Playwright's cookie list the same way a browser extension
        (e.g. Cookie-Editor) exports them: "name=value; name=value; ...".
        """
        return "; ".join(f"{c['name']}={c['value']}" for c in cookies)

    def _save_success(self, context, attempt, password):
        # Fetch ALL cookies with no URL filter first - Playwright's
        # BrowserContext.cookies(urls=...) URL-matching has been unreliable
        # across browser engines in practice and can silently return an
        # empty/incomplete list for cookies set with
        # a leading-dot parent domain like ".facebook.com". That previously
        # caused genuinely successful logins to be reported as failed with
        # "No c_user cookie found". Instead, filter manually by the
        # `domain` field the browser reports for each cookie, which is
        # always populated correctly regardless of engine.
        all_cookies = context.cookies()
        cookies = [c for c in all_cookies if "facebook.com" in (c.get("domain") or "")]

        if not cookies:
            # Extremely defensive fallback: if for some reason the domain
            # filter matched nothing (e.g. Facebook cookies came back with
            # an unexpected domain value), fall back to the unfiltered list
            # rather than failing a genuinely successful login.
            logger.warning("No cookies matched 'facebook.com' by domain; falling back to all captured cookies.")
            cookies = all_cookies

        # Find c_user cookie for UID
        uid = None
        for cookie in cookies:
            if cookie['name'] == 'c_user':
                uid = cookie['value']
                break
                
        if not uid:
            logger.warning("Successful login but no c_user cookie found!")
            attempt.status = "failed"
            attempt.fail_reason = "other"
            attempt.error_message = "No c_user cookie found"
            attempt.save()
            return

        # Drop the `locale` cookie we forced to "en_US" ourselves (see the
        # context.add_cookies() call above) - it's only there to pin the UI
        # language during the automation run and isn't needed by/relevant
        # to whoever uses the exported cookies afterwards.
        cookies_to_save = [c for c in cookies if c['name'] != 'locale']
        cookie_string = self._cookies_to_string(cookies_to_save)

        # Save (or refresh) the account. If we've already recovered this
        # exact Facebook account before (same user + uid), creating a new
        # row would raise an IntegrityError due to the unique_together
        # constraint - which would otherwise look exactly like "successful
        # login but nothing got saved". Update the existing record with the
        # fresh cookies/password instead of failing.
        try:
            FacebookAccount.objects.update_or_create(
                user=self.user,
                uid=uid,
                defaults={
                    "attempt": attempt,
                    "password": password,
                    "cookies": cookie_string,
                    "is_active": True,
                },
            )
        except Exception as e:
            logger.exception(f"Login succeeded but saving the FacebookAccount record failed: {e}")
            attempt.status = "failed"
            attempt.fail_reason = "other"
            attempt.error_message = f"Login succeeded but failed to save account: {e}"
            attempt.save()
            return

        # Update attempt
        attempt.status = "success"
        attempt.save()
        
        # Update job
        self.job.successful_count += 1
        self.job.save()
        logger.info(f"Successfully saved account {uid}")

    def _fail_attempt(self, attempt, provider, activation_id, fail_reason, error_message=None):
        provider.cancel_number(activation_id)
        attempt.status = "failed"
        attempt.fail_reason = fail_reason
        if error_message:
            attempt.error_message = error_message
        attempt.save()

    def _cancel_number_safe(self, provider, activation_id) -> None:
        """
        Best-effort wrapper around provider.cancel_number(), for failure
        paths that mark an attempt failed directly instead of going through
        _fail_attempt() (which already cancels). Wrapped in its own
        try/except so a cancellation failure (network hiccup, or the
        provider rejecting cancellation because the OTP was already
        delivered) never masks or interrupts handling of the original error
        that caused this attempt to fail.
        """
        if not activation_id:
            return
        try:
            provider.cancel_number(activation_id)
        except Exception as cancel_err:
            logger.warning(f"Failed to cancel number (activation_id={activation_id}): {cancel_err}")

    def _is_otp_error_shown(self, page) -> bool:
        """
        Detects Facebook's "incorrect/invalid code" error after submitting
        the OTP. This can show up even with the right code if the input
        field didn't register the fill properly, so it's worth retrying
        once by re-typing before giving up on this phone number.
        """
        error_texts = [
            "code you entered is incorrect",
            "incorrect code",
            "wrong code",
            "invalid code",
            "that code doesn't match",
            "please try again",
            "code has expired",
            "kode yang anda masukkan salah",
            "kode salah",
            "kode tidak valid",
            "kode tidak sesuai",
            "kode sudah kedaluwarsa",
            "coba lagi",
        ]
        for text in error_texts:
            if page.get_by_text(re.compile(re.escape(text), re.I), exact=False).count() > 0:
                return True
        return False

    def _dump_page_diagnostics(self, page, context: str) -> None:
        """
        Logs the page's URL, title, and a truncated dump of its visible text.

        Used as a debugging aid whenever none of our known page-state
        detectors (heading-role-based, text-based, radio-based heuristics)
        recognize the current page. Multiple layers of detection have
        independently failed for some Facebook screens in the past, and
        guessing at additional text variations without seeing the real DOM
        content hasn't reliably fixed it - this captures the actual visible
        text so a real, targeted detector/fix can be written from it.
        """
        try:
            url = page.url
            title = page.title()
            body_text = page.locator("body").inner_text(timeout=3000)
            # Facebook's identify/login dialogs are always short; cap this
            # generously so a legitimately huge/unexpected page (e.g. the
            # news feed) doesn't flood the log.
            snippet = body_text[:3000]
            # Windows' console and (previously) the log file handler default
            # to the cp1252 codec, which can't represent most non-Latin1
            # Unicode. Since Facebook's actual page text is exactly what we
            # need to see here, and can contain arbitrary Unicode (foreign
            # UI text, emoji, smart quotes, etc.), encode defensively to
            # plain ASCII with escapes rather than risk a UnicodeEncodeError
            # inside logging's emit() silently swallowing this entire record
            # (as happened before) - readable escapes beat a lost log line.
            safe_snippet = snippet.encode("ascii", errors="backslashreplace").decode("ascii")
            logger.warning(
                f"[UNRECOGNIZED PAGE @ {context}] url={url!r} title={title!r}\n"
                f"--- visible text (first 3000 chars, non-ASCII escaped) ---\n{safe_snippet}\n"
                f"--- end visible text ---"
            )
        except Exception as e:
            logger.warning(f"[UNRECOGNIZED PAGE @ {context}] Failed to capture diagnostics: {e}")

    def _is_find_account_error_page(self, page) -> bool:
        """
        Detects Facebook's "Find your account" phone/email entry screen
        (login/identify) redisplaying itself with a generic
        "Something went wrong. Please try again." banner instead of
        navigating forward after Step 2's "Continue" click.

        This is usually a transient server-side hiccup rather than a real
        rejection of the phone number - the entered number is still shown
        filled in and simply clicking "Continue" again typically proceeds
        normally, so this is handled with a short retry loop rather than
        failing the attempt immediately.
        """
        error_texts = [
            "Something went wrong. Please try again.",
            "Ada yang tidak beres. Silakan coba lagi.",
            "Terjadi kesalahan. Silakan coba lagi.",
        ]
        has_error = any(
            page.get_by_text(re.compile(re.escape(text), re.I), exact=False).count() > 0
            for text in error_texts
        )
        if not has_error:
            return False

        return page.get_by_text(
            re.compile(r"Find your account|Temukan akun anda", re.I), exact=False
        ).count() > 0

    def _is_no_account_page(self, page) -> bool:
        no_account_texts = [
            "No account found",
            "Tidak ada akun yang ditemukan",
            "Akun tidak ditemukan",
            "Tidak ditemukan akun",
        ]
        for text in no_account_texts:
            if page.get_by_text(text, exact=False).count() > 0:
                return True
        return False

    def _is_choose_login_method_page(self, page) -> bool:
        headings = [
            "Choose a way to log in",
            "Choose how to log in",
            "Choose how to confirm",
            "Pilih cara masuk",
            "Pilih cara untuk masuk",
            "Cara masuk",
        ]
        for heading in headings:
            # Use a case-insensitive regex so minor casing/punctuation differences
            # in Facebook's heading text don't cause a false negative.
            pattern = re.compile(re.escape(heading), re.I)
            if page.get_by_role("heading", name=pattern).count() > 0:
                return True
            # Facebook doesn't always mark this text with a semantic ARIA
            # heading role (varies by screen/locale) - get_by_role("heading",
            # ...) silently returns zero matches in that case, which used to
            # let this whole detection (and everything downstream that
            # depends on it, e.g. _is_password_only_login_page) fail
            # silently. Fall back to a plain text match so a missing role
            # doesn't hide an otherwise clearly-visible heading.
            if page.get_by_text(pattern, exact=False).count() > 0:
                return True
        return False

    def _is_password_only_login_page(self, page) -> bool:
        """
        Detects Facebook's "Choose a way to log in" screen when the ONLY
        method offered is "Continue with password" - no SMS/email code
        option at all. This can happen after repeated recovery attempts
        (often shown together with a "Something went wrong. Please try
        again." banner). We don't know the account's real password, so
        there's nothing we can do here - this attempt must be skipped
        instead of blindly clicking "Continue" (which would try to proceed
        with password login with nothing entered).
        """
        if not self._is_choose_login_method_page(page):
            return False

        has_password_option = page.get_by_text(
            re.compile(r"Continue with password|Lanjutkan dengan kata sandi", re.I), exact=False
        ).count() > 0
        if not has_password_option:
            return False

        # If a genuine SMS option is also present, this isn't the
        # password-only case - let the normal SMS selection logic handle it.
        sms_texts = [
            "Get code via SMS", "Get a code sent to your phone",
            "Dapatkan kode via SMS", "Dapatkan kode lewat SMS", "Dapatkan kode melalui SMS",
            "Kode SMS",
        ]
        for text in sms_texts:
            if page.get_by_text(re.compile(re.escape(text), re.I), exact=False).count() > 0:
                return False

        return True

    def _is_no_sms_option_page(self, page) -> bool:
        """
        Returns True when the page is a login-method-selection screen that
        offers NO SMS option (e.g. only "Get code via email" or only
        "Continue with password").

        Detection is done in two independent layers so that a heading-text
        mismatch in _is_choose_login_method_page can never cause us to
        miss the email-only case and accidentally proceed:

        Layer 1 (heading-based): standard _is_choose_login_method_page gate.
        Layer 2 (radio-based): if radios are present and NONE of them have
            an SMS-related label, treat the page as no-SMS regardless of
            whether the heading matched.
        """
        # ── SMS and non-SMS label sets (shared by both layers) ──────────────
        sms_texts = [
            "Get code via SMS", "Get a code sent to your phone",
            "Dapatkan kode via SMS", "Dapatkan kode lewat SMS", "Dapatkan kode melalui SMS",
            "Kode SMS",
        ]
        non_sms_texts = [
            "Get code via email", "Get a code sent to your email",
            "Dapatkan kode via email", "Dapatkan kode lewat email", "Dapatkan kode melalui email",
            "Continue with password", "Lanjutkan dengan kata sandi",
        ]

        def _sms_visible() -> bool:
            for text in sms_texts:
                if page.get_by_text(re.compile(re.escape(text), re.I), exact=False).count() > 0:
                    return True
            return False

        def _non_sms_visible() -> bool:
            for text in non_sms_texts:
                if page.get_by_text(re.compile(re.escape(text), re.I), exact=False).count() > 0:
                    logger.info(f"Non-SMS login option detected on page (found: '{text}').")
                    return True
            return False

        # Layer 1: heading matched → simple presence check.
        if self._is_choose_login_method_page(page):
            if _sms_visible():
                return False   # SMS is available - not a no-SMS page
            if _non_sms_visible():
                return True    # Non-SMS visible + no SMS → email/password-only
            return False       # Can't tell; let normal flow handle it

        # Layer 2: heading DID NOT match, but radio buttons suggest we're
        # on a login-method-selection page. If radios are present and no
        # SMS label is anywhere on the page, treat this as no-SMS.
        radio_count = page.locator('input[type="radio"]').count()
        if radio_count > 0 and not _sms_visible() and _non_sms_visible():
            logger.warning(
                "Login method page detected via radio-button heuristic "
                "(heading not matched) with no SMS option — treating as no-SMS page."
            )
            return True

        return False

    def _is_multiple_accounts_page(self, page) -> bool:

        if self._is_choose_login_method_page(page):
            return False

        multi_account_texts = [
            "Choose an account",
            "Choose your account",
            "Pilih akun",
            "Pilih akun Anda",
            "several accounts",
            "beberapa akun",
            "multiple accounts",
            "banyak akun",
            "Which account",
            "Akun mana",
            "match the email address or mobile number",
            "cocok dengan alamat email atau nomor ponsel",
        ]
        for text in multi_account_texts:
            if page.get_by_text(text, exact=False).count() > 0:
                return True

        # Heuristic: account picker with multiple radios before the login-method page
        return page.locator('input[type="radio"]').count() > 1

    def _phone_suffix_candidates(self, phone_number):
        """
        Builds a list of progressively shorter digit suffixes for
        `phone_number`, since Facebook may render the number with/without
        the country code, with spacing, or partially masked (e.g.
        "+62 *** *** 2887"). Used to fuzzy-match a phone number shown on the
        page against the number we actually submitted.
        """
        digits = re.sub(r'\D', '', phone_number or '')
        suffix_lengths = [len(digits), 10, 8, 6, 4]
        candidates = []
        for n in suffix_lengths:
            if n and len(digits) >= n:
                suffix = digits[-n:]
                if suffix not in candidates:
                    candidates.append(suffix)
        return candidates

    def _select_account_matching_phone_and_continue(self, page, phone_number) -> bool:
        """
        Facebook's "Choose your account"/"Choose an account" screen can list
        several profiles that share the same phone number/email (e.g. one
        row showing the phone number itself, another showing a masked name
        like "R... D..."). We must pick the row that actually matches the
        phone number we're recovering, not just the first one, otherwise we
        end up trying to recover a completely different account.

        Returns False (without clicking anything) if none of the listed
        entries mention our phone number at all - guessing and picking the
        first option here would silently proceed with the WRONG account,
        which is worse than just failing this attempt.
        """
        logger.info("Multiple accounts found for this number. Selecting the account matching the phone number...")

        candidates = self._phone_suffix_candidates(phone_number)

        matched_row = None
        matched_suffix = None
        for suffix in candidates:
            pattern = re.compile(re.escape(suffix))
            # The newer "Choose your account" UI renders each account as a
            # clickable row (button/link); older UIs use a plain text label
            # next to a radio input.
            row = page.get_by_role("button", name=pattern)
            if row.count() == 0:
                row = page.get_by_role("link", name=pattern)
            if row.count() == 0:
                row = page.get_by_text(pattern, exact=False)
            if row.count() > 0:
                matched_row = row.first
                matched_suffix = suffix
                break

        if matched_row is None:
            logger.warning(
                f"None of the listed accounts mention our phone number ({phone_number}). "
                "Refusing to guess which account to pick - failing this attempt instead."
            )
            return False

        logger.info(f"Found account row matching phone number ending in ...{matched_suffix}. Selecting it.")
        matched_row.click()

        # Some variants need an explicit "Continue" after selecting a radio
        # option; others (row/link style) navigate immediately on click. Use
        # a short timeout so we don't stall when there's nothing to click.
        self._click_button_by_names(page, ["Continue", "Lanjutkan", "Lanjut"], timeout=5000)
        page.wait_for_timeout(2000)
        return True

    def _select_sms_and_continue(self, page, phone_number=None) -> bool:
        """
        On Facebook's "Choose a way to log in" screen, finds the "Get code via
        SMS" radio option, verifies its phone number matches `phone_number`
        (the number obtained from the SMS provider in Step 1), and clicks
        Continue.

        Returns False if:
        - No SMS option is offered at all on this page, OR
        - The SMS option displays a phone number but it does NOT match the
          number we submitted in Step 1.  In that case we refuse to proceed
          because the OTP would be sent to a number we don't control.

        If the SMS option text contains no digits (Facebook just says "Get code
        via SMS" with no number shown), we can't verify and proceed normally.
        """
        logger.info("On 'Choose a way to log in' page. Looking for 'Get code via SMS'...")

        # SMS label texts to match.  Note: do NOT include bare "SMS" here - it
        # is too broad and will match email options or parent containers that
        # happen to contain the letters "SMS" somewhere in their subtree,
        # causing the bot to click the wrong (e.g. email) option.
        sms_label_texts = [
            "Get code via SMS",
            "Get a code sent to your phone",
            "Dapatkan kode via SMS",
            "Dapatkan kode lewat SMS",
            "Dapatkan kode melalui SMS",
            "Kode SMS",
        ]

        # Strategy 1: find the radio button whose accessible name / associated
        # label text contains one of the SMS phrases.  This is the most precise
        # approach because it targets the actual <input type="radio"> element,
        # not an arbitrary text node that might be a parent container.
        sms_radio = None
        for label_text in sms_label_texts:
            pattern = re.compile(re.escape(label_text), re.I)
            radio = page.get_by_role("radio", name=pattern)
            if radio.count() > 0:
                sms_radio = radio.first
                logger.info(f"Found SMS radio button matching '{label_text}'.")
                break

        # Strategy 2: fall back to finding the label/text element itself, then
        # look for an associated radio in the same container.  Avoids clicking
        # a broad wrapper element that would trigger the wrong option.
        if sms_radio is None:
            sms_label = self._get_text_locator(page, sms_label_texts)
            if sms_label is not None:
                try:
                    # Walk up to the nearest ancestor that is a label or a
                    # list-item / option container, then find its radio child.
                    container = sms_label.locator(
                        "xpath=ancestor-or-self::label"
                        " | xpath=ancestor::li"
                        " | xpath=ancestor::div[@role='radio']"
                        " | xpath=ancestor::div[contains(@class,'option')]"
                    ).last
                    radio_in_container = container.locator('input[type="radio"]')
                    if radio_in_container.count() > 0:
                        sms_radio = radio_in_container.first
                        logger.info("Found SMS radio via label container traversal.")
                except Exception:
                    pass

        # IMPORTANT: Do NOT add a "last resort" fallback that clicks the label
        # text element directly and returns True.  If we could not confirm a
        # specific SMS radio button, clicking an arbitrary text element risks
        # selecting the email option (or any other non-SMS option on the page).
        # The correct behaviour when no SMS radio is found is to return False
        # so the caller can fail the attempt cleanly.
        if sms_radio is None:
            logger.warning("No SMS login option found on this page (no matching radio button).")
            return False

        if phone_number:
            # Read the text of the radio's enclosing OPTION ROW (not the
            # whole page) to see what phone number Facebook is showing for
            # this SMS option specifically. We must stay scoped to just this
            # row - the account header above these options also displays a
            # phone number (the one we submitted, since that's how the
            # account was matched), so if our scope accidentally widens
            # enough to include it, we'd always see a "match" via the header
            # even when the actual SMS option's number underneath disagrees.
            option_text = ""
            try:
                # Prefer the nearest semantically-meaningful row container.
                row = sms_radio.locator(
                    "xpath=ancestor-or-self::label"
                    " | xpath=ancestor::li"
                    " | xpath=ancestor::div[@role='radio']"
                    " | xpath=ancestor::div[contains(@class,'option')]"
                ).first
                if row.count() > 0:
                    option_text = row.inner_text()
            except Exception:
                option_text = ""

            if not re.search(r'\d', option_text):
                # No named row container matched (or it had no digits) -
                # fall back to climbing a couple of plain ancestor levels,
                # stopping at the first one with digits. Capped low (3) to
                # avoid accidentally reaching all the way up to the account
                # header section above these options.
                try:
                    node = sms_radio
                    for _ in range(3):
                        node = node.locator("xpath=..")
                        try:
                            text = node.inner_text()
                        except Exception:
                            text = ""
                        if re.search(r'\d', text):
                            option_text = text
                            break
                except Exception:
                    pass

            digit_runs = re.findall(r'\d+', option_text)
            all_option_digits = ''.join(digit_runs)

            # Only enforce the match when the option text actually contains
            # digits to compare against.  When Facebook just says "Get code
            # via SMS" with no digits shown, there is nothing to compare
            # against and we proceed normally. Some UI variants mask all but
            # the last 2 digits (e.g. "+**********69") - that's still worth
            # checking, since a submitted number ending in a different pair
            # of digits is a certain mismatch.
            if len(all_option_digits) >= 2:
                candidates = self._phone_suffix_candidates(phone_number)
                # Check each individual digit run separately (not the
                # concatenated string) to avoid false mismatches when the
                # container text includes the account number as well as the
                # masked SMS number.
                matched = any(
                    any(run.endswith(c[-len(run):]) or c.endswith(run)
                        for c in candidates)
                    for run in digit_runs if len(run) >= 2
                )
                if matched:
                    logger.info(
                        f"SMS option phone number matches our submitted number "
                        f"(page shows {digit_runs}, submitted '...{candidates[0][-4:] if candidates else '?'}')."
                    )
                else:
                    logger.warning(
                        f"SMS option phone number does NOT match our submitted number "
                        f"(page shows {digit_runs}, submitted '...{candidates[0][-4:] if candidates else '?'}'). "
                        "Refusing to continue — the OTP would be sent to a different number."
                    )
                    return False

        sms_radio.click()
        self._click_button_by_names(page, ["Continue", "Lanjutkan", "Lanjut"], timeout=10000)
        page.wait_for_timeout(2000)
        return True



    def _handle_post_identify_flow(self, page, capsolver_api_key, attempt, activation_id, provider, phone_number) -> bool:
        page.wait_for_timeout(2000)

        # A reCAPTCHA can appear immediately after Step 2's "Continue" click -
        # before we even get to see the no-account/multiple-accounts/choose-method
        # screens. Check for it here first so it doesn't sit unsolved, silently
        # blocking every check below (none of which would match a captcha page).
        if not self._solve_recaptcha_v2_if_present(
            page, capsolver_api_key, attempt, activation_id, provider
        ):
            return False

        # Facebook can redisplay the same "Find your account" phone-entry
        # screen with a generic "Something went wrong. Please try again."
        # banner instead of navigating forward. Retry clicking Continue a
        # few times (the number is still filled in) before giving up.
        retries = 0
        while self._is_find_account_error_page(page) and retries < 3:
            retries += 1
            logger.warning(
                "Facebook showed 'Something went wrong' on the Find Account "
                f"page. Retrying Continue (attempt {retries}/3)..."
            )
            page.wait_for_timeout(2000)
            self._click_button_by_names(page, ["Continue", "Lanjutkan", "Lanjut"], timeout=10000)
            page.wait_for_timeout(2000)

        if self._is_find_account_error_page(page):
            logger.info(
                "Facebook repeatedly showed 'Something went wrong' on the "
                "Find Account page. Failing attempt."
            )
            self._fail_attempt(
                attempt, provider, activation_id, "identify_error",
                "Facebook showed 'Something went wrong. Please try again.' on "
                "the Find Account page and did not recover after retries",
            )
            return False

        if self._is_no_account_page(page):
            logger.info("Account not found.")
            self._fail_attempt(attempt, provider, activation_id, "no_account")
            return False

        # Scenario 2: multiple accounts share the same phone number
        if self._is_multiple_accounts_page(page):
            if not self._select_account_matching_phone_and_continue(page, phone_number):
                logger.info("Could not find an account matching this phone number. Failing attempt.")
                self._fail_attempt(
                    attempt, provider, activation_id, "phone_mismatch",
                    "Facebook showed an account list but none of the entries matched the phone number we submitted",
                )
                return False

            # Selecting an account also clicks its own "Continue" button, which
            # can likewise trigger a reCAPTCHA before the login-method screen shows up.
            if not self._solve_recaptcha_v2_if_present(
                page, capsolver_api_key, attempt, activation_id, provider
            ):
                return False

        # Scenario 1: choose SMS recovery, then reCAPTCHA appears after Continue
        if self._is_choose_login_method_page(page):
            if self._is_password_only_login_page(page):
                logger.info("Only 'Continue with password' is offered for this number. Failing attempt.")
                self._fail_attempt(
                    attempt, provider, activation_id, "password_prompt",
                    "Facebook only offered 'Continue with password' - no SMS/email code option available",
                )
                return False

            # Detect email-only login page: Facebook sometimes offers ONLY
            # "Get code via email" with no SMS option at all.  We have no way
            # to receive the code at an email address we don't control, so
            # fail fast here rather than letting _select_sms_and_continue try
            # (and potentially click the email option by mistake).
            if self._is_no_sms_option_page(page):
                logger.info("Only non-SMS options (e.g. email) are offered for this number. Failing attempt.")
                self._fail_attempt(
                    attempt, provider, activation_id, "no_sms_option",
                    "Facebook only offered non-SMS login options (e.g. email code) - no SMS option available",
                )
                return False

            if not self._select_sms_and_continue(page, phone_number):
                logger.info("SMS login method not offered for this number. Failing attempt.")
                self._fail_attempt(
                    attempt, provider, activation_id, "no_sms_option",
                    "Facebook did not offer a 'Get code via SMS' option for this number",
                )
                return False

            if not self._solve_recaptcha_v2_if_present(
                page, capsolver_api_key, attempt, activation_id, provider
            ):
                return False

        # ── Catch-all safety net ────────────────────────────────────────────
        # The _is_choose_login_method_page heading check above can fail if
        # Facebook uses a heading variant we haven't seen before. Run the
        # radio-button-based no-SMS heuristic one more time unconditionally
        # so the email-only case is never silently passed through.
        elif self._is_no_sms_option_page(page):
            logger.info(
                "Catch-all: login-method page with no SMS option detected "
                "(heading check did not match). Failing attempt."
            )
            self._fail_attempt(
                attempt, provider, activation_id, "no_sms_option",
                "Facebook showed a login-method page with no SMS option (heading not matched by standard check)",
            )
            return False
        else:
            # None of our detectors (no-account, multiple-accounts,
            # choose-login-method in any form, find-account-error,
            # no-sms-option) recognized this page at all. Rather than guess
            # at yet another text variation blind, log exactly what's
            # actually on the page so the real cause can be diagnosed from
            # the next run's logs instead of a screenshot.
            self._dump_page_diagnostics(page, "_handle_post_identify_flow: no known page state matched")

        return True

    def _has_recaptcha_v2(self, page) -> bool:
        # Check for reCAPTCHA in multiple ways:
        # 1. Standard iframe with recaptcha in src
        if page.locator('iframe[src*="recaptcha"]').count() > 0:
            return True
        # 2. reCAPTCHA anchor iframe (Enterprise / v2)
        if page.locator('iframe[src*="api2/anchor"]').count() > 0:
            return True
        # 3. The checkbox div itself (which the user found in the DOM)
        if page.locator('.recaptcha-checkbox-border').count() > 0:
            return True
        # 4. Any iframe inside the captcha popup
        if page.locator('[id*="recaptcha"], [class*="recaptcha"]').count() > 0:
            return True
        return False

    def _get_recaptcha_bframe(self, page):
        """
        Finds the reCAPTCHA "bframe" (the iframe that hosts the image/audio
        challenge UI), identified the same way playwright-recaptcha does -
        by URL pattern, not by language-dependent text.
        """
        for frame in page.frames:
            if re.search(r"/recaptcha/(api2|enterprise)/bframe", frame.url or ""):
                return frame
        return None

    def _click_recaptcha_action_button(self, page, timeout=4000) -> bool:
        """
        Language-independent fallback for reCAPTCHA's Skip/Next/Verify
        button. Google reuses a single button element with the stable id
        "recaptcha-verify-button" for all three states - only its visible
        text changes ("Skip"/"Next"/"Verify"), and that text is what changes
        per language.

        playwright-recaptcha (and our own button-name lists elsewhere in
        this file) match that text against a fixed list of languages, which
        doesn't scale to every language/country Facebook can render its UI
        in. Clicking by this stable id sidesteps the translation problem
        entirely for this specific button.
        """
        bframe = self._get_recaptcha_bframe(page)
        if bframe is None:
            logger.debug("_click_recaptcha_action_button: no bframe found.")
            return False
        button = bframe.locator("#recaptcha-verify-button")
        try:
            count = button.count()
            if count == 0:
                logger.debug("_click_recaptcha_action_button: button not present in bframe.")
                return False
            visible = button.is_visible()
            enabled = button.is_enabled()
            label = (button.inner_text() or "").strip()
            logger.info(
                f"_click_recaptcha_action_button: found button label={label!r} "
                f"visible={visible} enabled={enabled}"
            )
            if not (visible and enabled):
                # The button exists but Google hasn't unlocked it yet - this
                # happens while a challenge round is still awaiting tile
                # selection (the button stays disabled until the minimum
                # number of matching tiles are checked). Clicking now would
                # do nothing, so report "not clicked" and let the caller
                # decide whether to select tiles again before retrying.
                return False
            button.click(timeout=timeout)
            return True
        except (PlaywrightTimeoutError, PlaywrightError) as e:
            # Covers both a slow/unresponsive click and transient errors like
            # "Element is not attached to the DOM" / "Execution context was
            # destroyed", which happen when the bframe re-renders (e.g. a new
            # challenge round loads) between the count()/is_visible() checks
            # above and the click. Treat all of these as "click didn't land
            # this round" instead of letting them crash the whole solve flow.
            logger.warning(f"_click_recaptcha_action_button: click failed ({e}).")
            return False

    def _click_recaptcha_action_button_by_text(self, page, timeout=4000) -> bool:
        """
        Second-line fallback for the same Skip/Next/Verify button, used when
        the id-based lookup in _click_recaptcha_action_button doesn't find
        #recaptcha-verify-button (e.g. a markup change on Google's end).

        Matches purely by visible text ("verify"/"next"/"skip"), case
        insensitively - equivalent to a `page.locator("text=VERIFY")` /
        `button:has-text("Next")` approach, but scoped to the reCAPTCHA
        bframe, since a plain page.locator() can't see into iframes at all
        and would never match this button.
        """
        bframe = self._get_recaptcha_bframe(page)
        if bframe is None:
            return False
        pattern = re.compile(r"^(verify|next|skip)\b", re.I)
        try:
            button = bframe.get_by_role("button", name=pattern)
            if button.count() == 0:
                # Fall back further to any element containing that text,
                # in case it isn't exposed with an ARIA button role either.
                button = bframe.locator("text=/^(verify|next|skip)$/i")
            if button.count() == 0:
                logger.debug("_click_recaptcha_action_button_by_text: no text match found.")
                return False
            target = button.first
            if not (target.is_visible() and target.is_enabled()):
                return False
            target.click(timeout=timeout)
            return True
        except (PlaywrightTimeoutError, PlaywrightError) as e:
            logger.warning(f"_click_recaptcha_action_button_by_text: click failed ({e}).")
            return False

    def _run_with_hard_timeout(self, page, func, timeout_seconds):
        """
        Runs a zero-arg callable that blocks on Playwright's sync API, with
        a hard wall-clock timeout.

        playwright-recaptcha's solve_recaptcha() contains at least one
        internal polling loop with no timeout of its own (e.g. waiting for a
        "reload"/"payload" network response that its response-interceptor
        can silently miss) - if that happens, the call blocks forever and
        never raises, so none of our own round-retry/fallback logic below
        ever gets a chance to run, no matter how it's structured.

        Playwright's sync API can only be driven from the thread that
        created it, so func() itself can't be moved to a background thread.
        Instead, a watchdog timer runs in a background thread and forcibly
        closes the page if func() hasn't finished by the timeout. That
        immediately raises inside whatever Playwright call func() was
        blocked on (it can no longer talk to a live page), turning an
        unrecoverable hang into a normal exception our caller already knows
        how to handle. This only aborts the current phone-number attempt -
        each attempt gets its own fresh page/browser in _run_browser_flow -
        so the outer job loop simply moves on to the next number.
        """
        done = threading.Event()

        def _watchdog():
            if not done.wait(timeout_seconds):
                logger.error(
                    f"reCAPTCHA solve step exceeded its {timeout_seconds}s hard "
                    "timeout - forcibly closing the page to break the hang."
                )
                try:
                    page.close()
                except Exception:
                    pass

        watchdog_thread = threading.Thread(target=_watchdog, daemon=True)
        watchdog_thread.start()
        try:
            return func()
        finally:
            done.set()

    def _solve_recaptcha_v2_if_present(self, page, capsolver_api_key, attempt, activation_id, provider) -> bool:
        page.wait_for_timeout(2000)

        if not self._has_recaptcha_v2(page):
            return True

        logger.info("reCAPTCHA v2 detected, solving with CapSolver...")

        if not capsolver_api_key:
            logger.error("reCAPTCHA detected but CAPSOLVER_API_KEY is not configured.")
            self._fail_attempt(
                attempt, provider, activation_id, "captcha_failed",
                "CAPSOLVER_API_KEY is not configured",
            )
            return False

        # reCAPTCHA can require several successive challenge rounds (solving
        # one set of tiles can reveal new tiles that also match, which Google
        # then asks you to select too). A single solve_recaptcha() call only
        # handles one round, so loop, re-invoking the CapSolver-backed solver
        # fresh each round, until the widget is actually gone or we give up.
        max_rounds = 4
        last_error = None
        page_closed_by_watchdog = False
        for round_num in range(1, max_rounds + 1):
            if page.is_closed() or not self._has_recaptcha_v2(page):
                break

            try:
                with recaptchav2.SyncSolver(page, capsolver_api_key=capsolver_api_key) as solver:
                    self._run_with_hard_timeout(
                        page,
                        lambda: solver.solve_recaptcha(wait=True, image_challenge=True),
                        timeout_seconds=60,
                    )
                logger.info(f"reCAPTCHA round {round_num}: solve_recaptcha() completed.")
            except Exception as e:
                if page.is_closed():
                    # The watchdog above forcibly closed the page because
                    # solve_recaptcha() was stuck in an internal loop that
                    # would otherwise never return. There's nothing left to
                    # retry against on this attempt - stop immediately
                    # instead of looping into more exceptions on a dead page.
                    last_error = "reCAPTCHA solve hard-timed-out and the page had to be forcibly closed"
                    logger.error(last_error)
                    page_closed_by_watchdog = True
                    break
                # playwright-recaptcha selects the CapSolver-recommended tiles
                # (a purely visual operation, unaffected by language) but then
                # looks for a "Skip"/"Next"/"Verify" button by localized text
                # to submit them - if the challenge is rendered in a language
                # it doesn't recognize, or the button was momentarily disabled
                # while it looked, that lookup raises here even though the
                # tiles were already correctly selected.
                last_error = e
                logger.warning(
                    f"reCAPTCHA round {round_num}: playwright-recaptcha didn't finish on its "
                    f"own ({e})."
                )

            if page.is_closed():
                break

            # Whether solve_recaptcha() above raised or returned cleanly, it's
            # not reliable about actually submitting the round once tiles are
            # selected - tiles can get selected correctly but the
            # Skip/Next/Verify click itself never lands (e.g. the button was
            # still disabled the instant it looked). So always try to click
            # it ourselves afterwards instead of only doing this in the
            # except branch above: first by the language-independent id
            # lookup, then by a plain-text lookup (case-insensitive
            # "verify"/"next"/"skip") as a second-line fallback.
            clicked = False
            for _ in range(5):
                if not self._has_recaptcha_v2(page):
                    break
                if self._click_recaptcha_action_button(page) or self._click_recaptcha_action_button_by_text(page):
                    clicked = True
                    page.wait_for_timeout(2000)
                    break
                page.wait_for_timeout(1500)

            if not clicked and self._has_recaptcha_v2(page):
                # Button never became clickable this round (still disabled -
                # meaning CapSolver's tile selection didn't satisfy Google,
                # or a new round of tiles appeared that nothing has selected
                # yet). Loop back to the top so the next round's fresh
                # SyncSolver call re-evaluates and selects whatever tiles are
                # currently showing.
                logger.warning(
                    f"reCAPTCHA round {round_num}: Skip/Next/Verify button did not become "
                    "clickable via id or text lookup. Will re-run the solver for another round."
                )
                continue

            page.wait_for_timeout(1500)

        if page_closed_by_watchdog or (not page.is_closed() and self._has_recaptcha_v2(page)):
            logger.error(f"Failed to solve reCAPTCHA after {max_rounds} rounds: {last_error}")
            self._fail_attempt(
                attempt, provider, activation_id, "captcha_failed",
                str(last_error) if last_error else "reCAPTCHA still present after max rounds",
            )
            return False

        logger.info("reCAPTCHA solved successfully.")

        # Facebook's own page-level button may need to be clicked again after
        # the reCAPTCHA token is injected. This varies by which screen the
        # captcha appeared on - sometimes "Continue", sometimes "Next" - so
        # try every variant this file uses elsewhere rather than guessing
        # which one applies at this particular call site.
        if self._click_button_by_names(
            page,
            ["Continue", "Next", "Submit", "OK", "Lanjutkan", "Lanjut", "Selanjutnya"],
            timeout=10000,
        ):
            page.wait_for_timeout(2000)

        return True
