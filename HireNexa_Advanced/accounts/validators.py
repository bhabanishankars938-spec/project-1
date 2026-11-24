import re
from django.core.validators import validate_email as django_validate_email
from django.core.exceptions import ValidationError
from django.db.models import Q
from .models import User

try:
    import phonenumbers
    from phonenumbers import PhoneNumberFormat, NumberParseException
    HAS_PHONENUMBERS = True
except ImportError:
    HAS_PHONENUMBERS = False

# Strict email regex matching standard RFC 5322 specs
EMAIL_REGEX = re.compile(
    r"^[a-zA-Z0-9_.+-]+@[a-zA-Z0-9-]+\.[a-zA-Z0-9-.]+$"
)

# Common country codes mapping
COUNTRY_CODES = [
    ("+91", "India (+91)", "IN"),
    ("+1", "United States / Canada (+1)", "US"),
    ("+44", "United Kingdom (+44)", "GB"),
    ("+971", "United Arab Emirates (+971)", "AE"),
    ("+65", "Singapore (+65)", "SG"),
    ("+61", "Australia (+61)", "AU"),
    ("+49", "Germany (+49)", "DE"),
    ("+33", "France (+33)", "FR"),
    ("+81", "Japan (+81)", "JP"),
    ("+966", "Saudi Arabia (+966)", "SA"),
]


def validate_and_normalize_email(email_str, exclude_user_id=None):
    """
    Validates email format, checks for duplicates, and normalizes.
    Returns: (is_valid: bool, normalized_email: str, error_message: str or None)
    """
    if not email_str:
        return False, "", "Please enter a valid email address."

    email = str(email_str).strip().lower()

    if not email or len(email) < 5 or len(email) > 254:
        return False, email, "Please enter a valid email address."

    if not EMAIL_REGEX.match(email):
        return False, email, "Please enter a valid email address."

    # Additional standard check
    try:
        django_validate_email(email)
    except ValidationError:
        return False, email, "Please enter a valid email address."

    # Reject invalid domain structure (e.g. user@localhost, user@.com)
    parts = email.split("@")
    if len(parts) != 2:
        return False, email, "Please enter a valid email address."
    domain = parts[1]
    if "." not in domain or domain.startswith(".") or domain.endswith(".") or len(domain.split(".")[-1]) < 2:
        return False, email, "Please enter a valid email address."

    # Check duplicates in DB
    query = User.objects.filter(email__iexact=email)
    if exclude_user_id:
        query = query.exclude(pk=exclude_user_id)

    if query.exists():
        return False, email, "This email address is already registered."

    return True, email, None


def validate_and_normalize_phone(phone_str, country_code="+91", default_region="IN", exclude_user_id=None):
    """
    Validates phone number using Google phonenumbers library with E.164 normalization.
    Returns: (is_valid: bool, e164_phone: str, error_message: str or None)
    """
    if not phone_str:
        return False, "", "Please enter a valid mobile number."

    raw = str(phone_str).strip()

    # Prepend country code if not present
    if not raw.startswith("+"):
        prefix = country_code.strip() if country_code else "+91"
        if not prefix.startswith("+"):
            prefix = f"+{prefix}"
        cleaned_digits = re.sub(r"[^\d]", "", raw)
        # If user entered 11 digits with a leading 0, strip leading 0 (e.g. 09876543210 -> 9876543210)
        if len(cleaned_digits) == 11 and cleaned_digits.startswith("0"):
            cleaned_digits = cleaned_digits[1:]
        # If user entered digits that already start with country code (e.g. 919876543210 where prefix is +91)
        prefix_digits = prefix.lstrip("+")
        if prefix_digits and cleaned_digits.startswith(prefix_digits) and len(cleaned_digits) > 10:
            cleaned_digits = cleaned_digits[len(prefix_digits):]
        candidate = f"{prefix}{cleaned_digits}"
    else:
        candidate = raw

    # Validate using phonenumbers
    if HAS_PHONENUMBERS:
        try:
            parsed = phonenumbers.parse(candidate, default_region)
            if not phonenumbers.is_possible_number(parsed) or not phonenumbers.is_valid_number(parsed):
                return False, candidate, "Please enter a valid mobile number."

            e164_phone = phonenumbers.format_number(parsed, PhoneNumberFormat.E164)

            # Extra checks for India (+91)
            if e164_phone.startswith("+91"):
                national_num = str(parsed.national_number)
                if len(national_num) != 10:
                    return False, candidate, "Please enter a valid mobile number."
                if national_num[0] not in ["6", "7", "8", "9"]:
                    return False, candidate, "Please enter a valid mobile number."
                # Reject repetitive dummy numbers like 9999999999, 0000000000
                if len(set(national_num)) == 1:
                    return False, candidate, "Please enter a valid mobile number."

        except NumberParseException:
            return False, candidate, "Please enter a valid mobile number."
    else:
        # Robust regex fallback
        digits = re.sub(r"[^\d]", "", candidate)
        if len(digits) < 10 or len(digits) > 15:
            return False, candidate, "Please enter a valid mobile number."
        e164_phone = f"+{digits}"

    # Check duplicates in DB (ignoring null or empty phones)
    # Also check without plus or matching suffixes to prevent circumvention
    digits_suffix = re.sub(r"[^\d]", "", e164_phone)[-10:]
    query = User.objects.filter(
        Q(phone_number__iexact=e164_phone)
        | Q(phone_number__endswith=digits_suffix)
    ).exclude(phone_number__isnull=True).exclude(phone_number="")
    if exclude_user_id:
        query = query.exclude(pk=exclude_user_id)

    if query.exists():
        return False, e164_phone, "This mobile number is already registered."

    return True, e164_phone, None
