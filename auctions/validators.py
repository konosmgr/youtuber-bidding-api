
import re
from django.core.exceptions import ValidationError
from django.utils.translation import gettext as _

class SpecialCharacterValidator:
    """
    Validates that the password contains at least one special character.
    """
    
    def __init__(self, special_chars=r'[!@#$%^&*()_+\-=\[\]{};\':"\\|,.<>\/?]'):
        self.special_chars = special_chars
    
    def validate(self, password, user=None):
        if not re.search(self.special_chars, password):
            raise ValidationError(
                _("Password must contain at least one special character."),
                code='password_no_special_char',
            )
    
    def get_help_text(self):
        return _("Your password must contain at least one special character.")


class UppercaseValidator:
    """
    Validates that the password contains at least one uppercase letter.
    """
    
    def validate(self, password, user=None):
        if not any(char.isupper() for char in password):
            raise ValidationError(
                _("Password must contain at least one uppercase letter."),
                code='password_no_uppercase',
            )
    
    def get_help_text(self):
        return _("Your password must contain at least one uppercase letter.")


class LowercaseValidator:
    """
    Validates that the password contains at least one lowercase letter.
    """
    
    def validate(self, password, user=None):
        if not any(char.islower() for char in password):
            raise ValidationError(
                _("Password must contain at least one lowercase letter."),
                code='password_no_lowercase',
            )
    
    def get_help_text(self):
        return _("Your password must contain at least one lowercase letter.")


class NumberValidator:
    """
    Validates that the password contains at least one number.
    """
    
    def validate(self, password, user=None):
        if not any(char.isdigit() for char in password):
            raise ValidationError(
                _("Password must contain at least one number."),
                code='password_no_number',
            )
    
    def get_help_text(self):
        return _("Your password must contain at least one number.")