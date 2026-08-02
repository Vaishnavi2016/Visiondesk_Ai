from flask_wtf import FlaskForm
from wtforms import StringField, PasswordField, EmailField, BooleanField
from wtforms.validators import DataRequired, Email, Length, EqualTo, ValidationError
from security import Sanitizer

class LoginForm(FlaskForm):
    """Login form with CSRF protection"""
    username = StringField('Username', validators=[
        DataRequired(message='Username is required'),
        Length(min=3, max=50, message='Username must be between 3 and 50 characters')
    ])
    password = PasswordField('Password', validators=[
        DataRequired(message='Password is required'),
        Length(min=8, message='Password must be at least 8 characters')
    ])
    remember_me = BooleanField('Remember Me')
    
    def validate_username(self, field):
        # Sanitize username
        field.data = Sanitizer.sanitize_input(field.data)


class RegisterForm(FlaskForm):
    """Registration form with CSRF protection"""
    username = StringField('Username', validators=[
        DataRequired(message='Username is required'),
        Length(min=3, max=50, message='Username must be between 3 and 50 characters'),
        # Custom validator for special characters
    ])
    email = EmailField('Email', validators=[
        DataRequired(message='Email is required'),
        Email(message='Invalid email address'),
        Length(max=100)
    ])
    password = PasswordField('Password', validators=[
        DataRequired(message='Password is required'),
        Length(min=8, message='Password must be at least 8 characters')
    ])
    confirm_password = PasswordField('Confirm Password', validators=[
        DataRequired(message='Please confirm your password'),
        EqualTo('password', message='Passwords must match')
    ])
    
    def validate_username(self, field):
        # Sanitize username
        field.data = Sanitizer.sanitize_input(field.data)
        
        # Check for special characters (allow only alphanumeric and underscore)
        if not re.match(r'^[a-zA-Z0-9_]+$', field.data):
            raise ValidationError('Username can only contain letters, numbers, and underscores')
    
    def validate_email(self, field):
        # Validate email format
        if not Sanitizer.validate_email(field.data):
            raise ValidationError('Invalid email address')


class PasswordResetRequestForm(FlaskForm):
    """Password reset request form"""
    email = EmailField('Email', validators=[
        DataRequired(message='Email is required'),
        Email(message='Invalid email address')
    ])
    
    def validate_email(self, field):
        if not Sanitizer.validate_email(field.data):
            raise ValidationError('Invalid email address')


class PasswordResetForm(FlaskForm):
    """Password reset form"""
    password = PasswordField('New Password', validators=[
        DataRequired(message='Password is required'),
        Length(min=8, message='Password must be at least 8 characters')
    ])
    confirm_password = PasswordField('Confirm Password', validators=[
        DataRequired(message='Please confirm your password'),
        EqualTo('password', message='Passwords must match')
    ])
    
    def validate_password(self, field):
        is_valid, message = Sanitizer.validate_password(field.data)
        if not is_valid:
            raise ValidationError(message)