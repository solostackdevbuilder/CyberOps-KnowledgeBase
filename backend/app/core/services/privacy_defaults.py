"""
Built-in sensitive defaults for privacy replacement.
These defaults stay local and are never sent externally.
"""
from app.models_settings import (
    SensitiveDefaultsConfig,
    SensitiveKeywordRule,
    SensitiveRegexRule,
    SensitiveRuleSeverity,
)


def get_default_sensitive_config() -> SensitiveDefaultsConfig:
    """Return built-in keyword + regex protections enabled by default."""
    return SensitiveDefaultsConfig(
        enabled=True,
        keyword_rules=[
            SensitiveKeywordRule(id="kw-jwt", name="JWT token marker", keyword="jwt", replacement="[REDACTED_JWT]", severity=SensitiveRuleSeverity.HIGH),
            SensitiveKeywordRule(id="kw-cookie", name="Cookie marker", keyword="cookie", replacement="[REDACTED_COOKIE]", severity=SensitiveRuleSeverity.HIGH),
            SensitiveKeywordRule(id="kw-set-cookie", name="Set-Cookie header", keyword="set-cookie", replacement="[REDACTED_SET_COOKIE]", severity=SensitiveRuleSeverity.CRITICAL),
            SensitiveKeywordRule(id="kw-sessionid", name="SessionID marker", keyword="sessionid", replacement="[REDACTED_SESSION_ID]", severity=SensitiveRuleSeverity.CRITICAL),
            SensitiveKeywordRule(id="kw-sid", name="SID marker", keyword="sid=", replacement="[REDACTED_SID]", severity=SensitiveRuleSeverity.HIGH),
            SensitiveKeywordRule(id="kw-authorization", name="Authorization header", keyword="authorization:", replacement="[REDACTED_AUTH_HEADER]", severity=SensitiveRuleSeverity.CRITICAL),
            SensitiveKeywordRule(id="kw-bearer", name="Bearer token marker", keyword="bearer ", replacement="[REDACTED_BEARER]", severity=SensitiveRuleSeverity.CRITICAL),
            SensitiveKeywordRule(id="kw-refresh-token", name="Refresh token marker", keyword="refresh_token", replacement="[REDACTED_REFRESH_TOKEN]", severity=SensitiveRuleSeverity.CRITICAL),
            SensitiveKeywordRule(id="kw-csrf-token", name="CSRF token marker", keyword="csrf", replacement="[REDACTED_CSRF]", severity=SensitiveRuleSeverity.HIGH),
            SensitiveKeywordRule(id="kw-okta", name="Okta marker", keyword="okta", replacement="[REDACTED_OKTA]", severity=SensitiveRuleSeverity.HIGH),
            SensitiveKeywordRule(id="kw-ssws", name="Okta SSWS token marker", keyword="ssws", replacement="[REDACTED_OKTA_TOKEN]", severity=SensitiveRuleSeverity.CRITICAL),
            SensitiveKeywordRule(id="kw-auth0", name="Auth0 marker", keyword="auth0", replacement="[REDACTED_AUTH0]", severity=SensitiveRuleSeverity.MEDIUM),
            SensitiveKeywordRule(id="kw-cognito", name="Cognito marker", keyword="cognito", replacement="[REDACTED_COGNITO]", severity=SensitiveRuleSeverity.MEDIUM),
            SensitiveKeywordRule(id="kw-entra", name="Entra/AzureAD marker", keyword="entra", replacement="[REDACTED_ENTRA]", severity=SensitiveRuleSeverity.MEDIUM),
            SensitiveKeywordRule(id="kw-x-api-key", name="X-Api-Key header", keyword="x-api-key", replacement="[REDACTED_API_KEY_HEADER]", severity=SensitiveRuleSeverity.CRITICAL),
            SensitiveKeywordRule(id="kw-x-auth-token", name="X-Auth-Token header", keyword="x-auth-token", replacement="[REDACTED_AUTH_TOKEN_HEADER]", severity=SensitiveRuleSeverity.CRITICAL),
            SensitiveKeywordRule(id="kw-secret-key", name="Secret key marker", keyword="secret_key", replacement="[REDACTED_SECRET_KEY]", severity=SensitiveRuleSeverity.CRITICAL),
            SensitiveKeywordRule(id="kw-aws-access", name="AWS access key marker", keyword="aws_access_key_id", replacement="[REDACTED_AWS_ACCESS_KEY]", severity=SensitiveRuleSeverity.CRITICAL),
            SensitiveKeywordRule(id="kw-aws-secret", name="AWS secret key marker", keyword="aws_secret_access_key", replacement="[REDACTED_AWS_SECRET_KEY]", severity=SensitiveRuleSeverity.CRITICAL),
            SensitiveKeywordRule(id="kw-private-key", name="Private key marker", keyword="private key", replacement="[REDACTED_PRIVATE_KEY]", severity=SensitiveRuleSeverity.CRITICAL),
            SensitiveKeywordRule(id="kw-webhook-secret", name="Webhook secret marker", keyword="webhook_secret", replacement="[REDACTED_WEBHOOK_SECRET]", severity=SensitiveRuleSeverity.HIGH),
        ],
        regex_rules=[
            SensitiveRegexRule(id="rx-jwt", name="JWT token structure", pattern=r"\beyJ[A-Za-z0-9_-]{10,}\.[A-Za-z0-9_-]{10,}\.[A-Za-z0-9_-]{10,}\b", replacement="[REDACTED_JWT]", severity=SensitiveRuleSeverity.CRITICAL),
            SensitiveRegexRule(id="rx-aws-akia", name="AWS access key ID", pattern=r"\bAKIA[0-9A-Z]{16}\b", replacement="[REDACTED_AWS_ACCESS_KEY_ID]", severity=SensitiveRuleSeverity.CRITICAL),
            SensitiveRegexRule(id="rx-aws-secret", name="AWS secret access key format", pattern=r"(?i)\baws_secret_access_key\s*[:=]\s*[A-Za-z0-9/\+=]{32,}\b", replacement="aws_secret_access_key=[REDACTED_AWS_SECRET]", severity=SensitiveRuleSeverity.CRITICAL),
            SensitiveRegexRule(id="rx-aws-session-token", name="AWS session token", pattern=r"(?i)\baws_session_token\s*[:=]\s*[A-Za-z0-9/\+=]{20,}\b", replacement="aws_session_token=[REDACTED_AWS_SESSION_TOKEN]", severity=SensitiveRuleSeverity.CRITICAL),
            SensitiveRegexRule(id="rx-bearer-header", name="Bearer authorization value", pattern=r"(?i)\bauthorization\s*:\s*bearer\s+[A-Za-z0-9._\-+/=]{16,}", replacement="Authorization: Bearer [REDACTED]", severity=SensitiveRuleSeverity.CRITICAL),
            SensitiveRegexRule(id="rx-cookie-header", name="Cookie header values", pattern=r"(?i)\bcookie\s*:\s*[^\r\n]{8,}", replacement="Cookie: [REDACTED_COOKIE_HEADER]", severity=SensitiveRuleSeverity.CRITICAL),
            SensitiveRegexRule(id="rx-set-cookie-header", name="Set-Cookie header values", pattern=r"(?i)\bset-cookie\s*:\s*[^\r\n]{8,}", replacement="Set-Cookie: [REDACTED_SET_COOKIE_HEADER]", severity=SensitiveRuleSeverity.CRITICAL),
            SensitiveRegexRule(id="rx-ssws-token", name="Okta SSWS token", pattern=r"(?i)\bSSWS\s+[A-Za-z0-9._\-]{16,}", replacement="SSWS [REDACTED_OKTA_TOKEN]", severity=SensitiveRuleSeverity.CRITICAL),
            SensitiveRegexRule(id="rx-github-token", name="GitHub token format", pattern=r"\bgh[pousr]_[A-Za-z0-9]{20,}\b", replacement="[REDACTED_GITHUB_TOKEN]", severity=SensitiveRuleSeverity.CRITICAL),
            SensitiveRegexRule(id="rx-slack-token", name="Slack token format", pattern=r"\bxox[baprs]-[A-Za-z0-9-]{12,}\b", replacement="[REDACTED_SLACK_TOKEN]", severity=SensitiveRuleSeverity.CRITICAL),
            SensitiveRegexRule(id="rx-openai-key", name="OpenAI API key format", pattern=r"\bsk-[A-Za-z0-9]{20,}\b", replacement="[REDACTED_OPENAI_KEY]", severity=SensitiveRuleSeverity.CRITICAL),
            SensitiveRegexRule(id="rx-stripe-key", name="Stripe secret key format", pattern=r"\bsk_live_[A-Za-z0-9]{16,}\b", replacement="[REDACTED_STRIPE_KEY]", severity=SensitiveRuleSeverity.CRITICAL),
            SensitiveRegexRule(id="rx-gcp-private-key", name="GCP private key block", pattern=r"-----BEGIN PRIVATE KEY-----[\s\S]*?-----END PRIVATE KEY-----", replacement="[REDACTED_PRIVATE_KEY_BLOCK]", severity=SensitiveRuleSeverity.CRITICAL),
            SensitiveRegexRule(id="rx-ssh-private-key", name="SSH private key block", pattern=r"-----BEGIN (?:RSA|OPENSSH|EC) PRIVATE KEY-----[\s\S]*?-----END (?:RSA|OPENSSH|EC) PRIVATE KEY-----", replacement="[REDACTED_SSH_PRIVATE_KEY_BLOCK]", severity=SensitiveRuleSeverity.CRITICAL),
            SensitiveRegexRule(id="rx-rfc1918-ip", name="Private RFC1918 IP address", pattern=r"\b(?:10\.\d{1,3}\.\d{1,3}\.\d{1,3}|192\.168\.\d{1,3}\.\d{1,3}|172\.(?:1[6-9]|2\d|3[0-1])\.\d{1,3}\.\d{1,3})\b", replacement="[REDACTED_PRIVATE_IP]", severity=SensitiveRuleSeverity.MEDIUM),
            SensitiveRegexRule(id="rx-dsn-credentials", name="Credentialed DSN", pattern=r"(?i)\b(?:postgres(?:ql)?|mysql|mongodb(?:\+srv)?):\/\/[^:\s]+:[^@\s]+@[^\s]+", replacement="[REDACTED_DSN]", severity=SensitiveRuleSeverity.CRITICAL),
            SensitiveRegexRule(id="rx-session-cookie-name", name="Session cookie assignment", pattern=r"(?i)\b(?:connect\.sid|jsessionid|phpsessid|_session)\s*=\s*[^;\s]{8,}", replacement="[REDACTED_SESSION_COOKIE]", severity=SensitiveRuleSeverity.CRITICAL),
            SensitiveRegexRule(id="rx-azure-sas", name="Azure SAS token query", pattern=r"(?i)(?:\?|&)(?:sig|se|sp|sv|spr|sr)=[^&\s]{6,}", replacement="[REDACTED_AZURE_SAS_PARAM]", severity=SensitiveRuleSeverity.HIGH),
            SensitiveRegexRule(id="rx-gcp-api-key", name="GCP API key style", pattern=r"\bAIza[0-9A-Za-z\-_]{20,}\b", replacement="[REDACTED_GCP_API_KEY]", severity=SensitiveRuleSeverity.CRITICAL),
            SensitiveRegexRule(id="rx-webhook-url-secret", name="Webhook URL with token", pattern=r"https?:\/\/[^\s]*(?:webhook|hooks)[^\s]*\/[A-Za-z0-9._\-]{12,}", replacement="[REDACTED_WEBHOOK_URL]", severity=SensitiveRuleSeverity.HIGH),
        ],
    )
