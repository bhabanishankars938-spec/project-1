from django import forms
from django.contrib.auth.forms import UserCreationForm
from .models import User
from .validators import (
    validate_and_normalize_email,
    validate_and_normalize_phone,
    COUNTRY_CODES,
)


class SignUpForm(UserCreationForm):
    """
    Enterprise Registration Form enforcing:
    1. Full Name
    2. Valid Email Address
    3. Valid Mobile Number with Country Code (+91 default)
    4. Password & Confirm Password
    5. User Role (OWNER strictly forbidden)
    """
    PUBLIC_ROLE_CHOICES = (
        (User.Role.CANDIDATE, "Student / Candidate (Looking for Jobs & Internships)"),
        (User.Role.RECRUITER, "HR / Tech Recruiter (Posting Jobs & Hiring)"),
        (User.Role.COMPANY_ADMIN, "Company Admin (Enterprise Hiring & Team Administration)"),
        (User.Role.FREELANCER, "Freelancer (Finding Projects & Contracts)"),
    )

    full_name = forms.CharField(
        label="Full Name",
        max_length=150,
        required=True,
        widget=forms.TextInput(
            attrs={"placeholder": "e.g. Priya Sharma", "class": "form-input", "autofocus": True}
        ),
    )

    email = forms.CharField(
        label="Email Address",
        required=True,
        error_messages={
            "required": "Please enter a valid email address.",
        },
        widget=forms.EmailInput(
            attrs={"placeholder": "e.g. priya.sharma@example.com", "class": "form-input"}
        ),
    )

    country_code = forms.ChoiceField(
        label="Country",
        choices=[(c[0], c[1]) for c in COUNTRY_CODES],
        initial="+91",
        widget=forms.Select(attrs={"class": "form-input country-select"}),
        required=False,
    )

    phone_number = forms.CharField(
        label="Mobile Number",
        required=True,
        widget=forms.TextInput(
            attrs={"placeholder": "98765 43210", "class": "form-input"}
        ),
    )

    role = forms.ChoiceField(
        label="Account Type",
        choices=PUBLIC_ROLE_CHOICES,
        initial=User.Role.CANDIDATE,
        widget=forms.RadioSelect(attrs={"class": "role-radio"}),
    )

    agree_terms = forms.BooleanField(
        label="Terms & Privacy Agreement",
        required=False,
        initial=True,
        widget=forms.CheckboxInput(attrs={"class": "form-checkbox"}),
    )

    class Meta:
        model = User
        fields = ("full_name", "username", "email", "country_code", "phone_number", "role")

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["username"].widget.attrs.update(
            {"placeholder": "Choose a unique username", "class": "form-input"}
        )
        if "password1" in self.fields:
            self.fields["password1"].widget.attrs.update(
                {"placeholder": "Create a strong password (min. 8 characters)", "class": "form-input"}
            )
        if "password2" in self.fields:
            self.fields["password2"].widget.attrs.update(
                {"placeholder": "Confirm password", "class": "form-input"}
            )

    def clean_email(self):
        raw_email = self.cleaned_data.get("email")
        is_valid, normalized, err = validate_and_normalize_email(raw_email)
        if not is_valid:
            raise forms.ValidationError(err)
        return normalized

    def clean_phone_number(self):
        raw_phone = self.cleaned_data.get("phone_number")
        country_code = self.cleaned_data.get("country_code", "+91")
        is_valid, e164_phone, err = validate_and_normalize_phone(raw_phone, country_code=country_code)
        if not is_valid:
            raise forms.ValidationError(err)
        return e164_phone

    def clean_role(self):
        role = str(self.cleaned_data.get("role", "")).strip().upper()
        # Enforce strict server-side security gate against privilege escalation
        if role in (User.Role.OWNER, "OWNER", "ADMIN", "SUPERADMIN", "SUPERUSER"):
            raise forms.ValidationError(
                "Security Alert: The Platform Owner role cannot be selected via public registration."
            )
        valid_roles = [r[0] for r in self.PUBLIC_ROLE_CHOICES]
        if role not in valid_roles:
            raise forms.ValidationError("Please select a valid account role.")
        return role

    def clean(self):
        cleaned_data = super().clean()
        role = str(cleaned_data.get("role", "")).strip().upper()
        if role in (User.Role.OWNER, "OWNER", "ADMIN", "SUPERADMIN", "SUPERUSER"):
            self.add_error("role", "Security Alert: Privilege escalation denied.")
        if "agree_terms" in self.data and not cleaned_data.get("agree_terms"):
            self.add_error("agree_terms", "Please accept the Terms of Service and Privacy Policy to create an account.")
        return cleaned_data

    def save(self, commit=True):
        user = super().save(commit=False)
        full_name = self.cleaned_data.get("full_name", "").strip()
        parts = full_name.split(" ", 1)
        user.first_name = parts[0]
        user.last_name = parts[1] if len(parts) > 1 else ""
        user.email = self.cleaned_data.get("email")
        user.phone_number = self.cleaned_data.get("phone_number")
        assigned_role = str(self.cleaned_data.get("role", User.Role.CANDIDATE)).strip().upper()
        if assigned_role in (User.Role.OWNER, "OWNER", "ADMIN", "SUPERADMIN", "SUPERUSER"):
            assigned_role = User.Role.CANDIDATE
        user.role = assigned_role
        
        from django.conf import settings
        require_otp = getattr(settings, "UNIFIED_REQUIRE_OTP", False)
        if require_otp:
            # Accounts start inactive until dual OTP verification succeeds
            user.is_active = False
            user.is_email_verified = False
            user.is_phone_verified = False
        else:
            user.is_active = True
            user.is_email_verified = True
            user.is_phone_verified = True
        user.is_staff = False
        user.is_superuser = False

        if commit:
            user.save()
        return user


class StudentSignUpForm(SignUpForm):
    """Dedicated Student / Candidate registration."""
    role = forms.CharField(widget=forms.HiddenInput(), required=False, initial=User.Role.CANDIDATE)

    def clean_role(self):
        return User.Role.CANDIDATE

    def save(self, commit=True):
        user = super().save(commit=False)
        user.role = User.Role.CANDIDATE
        if commit:
            user.save()
        return user


class HRSignUpForm(SignUpForm):
    """Dedicated HR / Recruiter registration."""
    company_name = forms.CharField(
        max_length=160,
        required=False,
        widget=forms.TextInput(attrs={"placeholder": "e.g. Acme Technologies", "class": "form-input"}),
    )
    role = forms.CharField(widget=forms.HiddenInput(), required=False, initial=User.Role.RECRUITER)

    def clean_role(self):
        return User.Role.RECRUITER

    def save(self, commit=True):
        user = super().save(commit=False)
        user.role = User.Role.RECRUITER
        if commit:
            user.save()
        return user


class FreelancerSignUpForm(SignUpForm):
    """Dedicated Freelancer registration."""
    headline = forms.CharField(
        max_length=160,
        required=False,
        widget=forms.TextInput(attrs={"placeholder": "e.g. Full-Stack Python & React Developer", "class": "form-input"}),
    )
    role = forms.CharField(widget=forms.HiddenInput(), required=False, initial=User.Role.FREELANCER)

    def clean_role(self):
        return User.Role.FREELANCER

    def save(self, commit=True):
        user = super().save(commit=False)
        user.role = User.Role.FREELANCER
        if commit:
            user.save()
        return user


# ==============================================================================
# OTP VERIFICATION & CONTACT UPDATE FORMS
# ==============================================================================

class VerifySingleOTPForm(forms.Form):
    """Submits 6-digit OTP code for either Email or SMS channel."""
    otp_code = forms.CharField(
        max_length=6,
        min_length=6,
        required=True,
        widget=forms.TextInput(
            attrs={
                "placeholder": "123456",
                "class": "form-input otp-digit-group",
                "maxlength": "6",
                "pattern": "[0-9]{6}",
                "inputmode": "numeric",
                "autocomplete": "one-time-code",
            }
        ),
    )


class ChangeEmailForm(forms.Form):
    new_email = forms.CharField(
        label="New Email Address",
        required=True,
        error_messages={
            "required": "Please enter a valid email address.",
        },
        widget=forms.EmailInput(attrs={"placeholder": "new.email@example.com", "class": "form-input"}),
    )

    def __init__(self, *args, user_id=None, **kwargs):
        self.user_id = user_id
        super().__init__(*args, **kwargs)

    def clean_new_email(self):
        raw = self.cleaned_data.get("new_email")
        is_valid, normalized, err = validate_and_normalize_email(raw, exclude_user_id=self.user_id)
        if not is_valid:
            raise forms.ValidationError(err)
        return normalized


class ChangePhoneForm(forms.Form):
    country_code = forms.ChoiceField(
        label="Country",
        choices=[(c[0], c[1]) for c in COUNTRY_CODES],
        initial="+91",
        widget=forms.Select(attrs={"class": "form-input"}),
        required=False,
    )
    new_phone_number = forms.CharField(
        label="New Mobile Number",
        required=True,
        widget=forms.TextInput(attrs={"placeholder": "98765 43210", "class": "form-input"}),
    )

    def __init__(self, *args, user_id=None, **kwargs):
        self.user_id = user_id
        super().__init__(*args, **kwargs)

    def clean_new_phone_number(self):
        raw = self.cleaned_data.get("new_phone_number")
        code = self.cleaned_data.get("country_code", "+91")
        is_valid, e164, err = validate_and_normalize_phone(raw, country_code=code, exclude_user_id=self.user_id)
        if not is_valid:
            raise forms.ValidationError(err)
        return e164


class ForgotPasswordRequestForm(forms.Form):
    """Initiates password reset lookup by Username, Email, or Mobile Phone."""
    identifier = forms.CharField(
        label="Username, Email, or Phone Number",
        required=True,
        widget=forms.TextInput(
            attrs={
                "placeholder": "Enter username, email, or registered phone number",
                "class": "form-input",
                "autofocus": True,
            }
        ),
    )


class ResetPasswordWithOTPForm(forms.Form):
    """Submits 6-digit OTP and new password with confirmation."""
    otp_code = forms.CharField(
        label="6-Digit Verification Code (OTP)",
        max_length=6,
        min_length=6,
        required=True,
        widget=forms.TextInput(
            attrs={
                "placeholder": "123456",
                "class": "form-input",
                "style": "letter-spacing: 0.35em; font-size: 20px; font-weight: 700; text-align: center;",
                "maxlength": "6",
                "pattern": "[0-9]{6}",
            }
        ),
    )
    new_password1 = forms.CharField(
        label="New Password",
        widget=forms.PasswordInput(
            attrs={"placeholder": "Enter a strong new password (min. 8 characters)", "class": "form-input"}
        ),
        min_length=8,
    )
    new_password2 = forms.CharField(
        label="Confirm New Password",
        widget=forms.PasswordInput(
            attrs={"placeholder": "Re-enter new password", "class": "form-input"}
        ),
        min_length=8,
    )

    def clean(self):
        cleaned_data = super().clean()
        p1 = cleaned_data.get("new_password1")
        p2 = cleaned_data.get("new_password2")
        if p1 and p2 and p1 != p2:
            raise forms.ValidationError("The two passwords do not match. Please try again.")
        return cleaned_data
