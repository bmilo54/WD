STATUS_CHOICES = (
    ("pending", "Pending"),
    ("running", "Running"),
    ("success", "Success"),
    ("partial", "Partial"),
    ("failed", "Failed"),
)

FAIL_REASON_CHOICES = (
    ("no_account", "No Facebook Account Found"),
    ("timeout", "SMS Timeout"),
    ("wrong_length", "Code Length not 6"),
    ("password_prompt", "Facebook asked for current password"),
    ("captcha_failed", "reCAPTCHA solve failed"),
    ("no_sms_option", "SMS Login Method Not Offered"),
    ("otp_rejected", "OTP Code Rejected by Facebook"),
    ("two_factor_required", "Two-Factor Authenticator App Code Required"),
    ("phone_mismatch", "Displayed Account/Contact Did Not Match Submitted Phone Number"),
    ("identify_error", "Facebook Showed 'Something Went Wrong' on Find Account Page"),
    ("other", "Other Error"),
)

FLOW_CHOICES = (
    ("success", "Success"),
    ("failed", "Failed"),
)