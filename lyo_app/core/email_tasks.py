"""
Email background tasks using Celery.
Handles sending verification emails and password reset emails.
"""

import smtplib
import logging
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from datetime import datetime
from celery import Celery
from lyo_app.core.config import settings
from lyo_app.core.security_utils import get_safe_token_for_logging

logger = logging.getLogger(__name__)

# Initialize Celery app
celery_app = Celery(
    "lyo_app",
    broker=settings.celery_broker_url,
    backend=settings.celery_result_backend
)

# Configure Celery
celery_app.conf.update(
    task_serializer='json',
    accept_content=['json'],
    result_serializer='json',
    timezone='UTC',
    enable_utc=True,
    task_track_started=True,
    task_acks_late=True,
    worker_prefetch_multiplier=1,
)


def create_email_message(to_email: str, subject: str, html_body: str) -> MIMEMultipart:
    """
    Create email message with proper headers.
    
    Args:
        to_email: Recipient email address
        subject: Email subject
        html_body: HTML email body
        
    Returns:
        MIMEMultipart email message
    """
    msg = MIMEMultipart('alternative')
    msg['From'] = settings.smtp_from_email
    msg['To'] = to_email
    msg['Subject'] = subject
    msg['Date'] = datetime.utcnow().strftime('%a, %d %b %Y %H:%M:%S +0000')
    
    # Attach HTML body
    html_part = MIMEText(html_body, 'html')
    msg.attach(html_part)
    
    return msg


def send_email_via_smtp(msg: MIMEMultipart) -> bool:
    """
    Send email via SMTP server.
    
    Args:
        msg: Email message to send
        
    Returns:
        True if successful, False otherwise
    """
    try:
        with smtplib.SMTP(settings.smtp_server, settings.smtp_port) as server:
            if settings.smtp_use_tls:
                server.starttls()
            
            if settings.smtp_username and settings.smtp_password:
                server.login(settings.smtp_username, settings.smtp_password)
            
            server.send_message(msg)
            return True
            
    except Exception as e:
        logger.error(f"SMTP error: {str(e)}")
        return False


@celery_app.task(bind=True, max_retries=3, default_retry_delay=60)
def send_verification_email_background(self, email: str, verification_url: str, user_name: str):
    """
    Background task to send verification email.
    
    Args:
        email: Recipient email address
        verification_url: Email verification URL with token
        user_name: User's display name
        
    Returns:
        True if successful, False otherwise
    """
    try:
        # Log safely (don't log the actual URL with token)
        safe_token = get_safe_token_for_logging(verification_url.split('token=')[-1] if 'token=' in verification_url else '')
        logger.info(f"Sending verification email to {email[:3]}*** with token hash {safe_token}")
        
        subject = "Verify Your LyoApp Account"
        html_body = f"""
        <!DOCTYPE html>
        <html>
        <head>
            <meta charset="utf-8">
            <title>Verify Your Email</title>
            <style>
                body {{ font-family: Arial, sans-serif; line-height: 1.6; color: #333; }}
                .container {{ max-width: 600px; margin: 0 auto; padding: 20px; }}
                .header {{ text-align: center; margin-bottom: 30px; }}
                .button {{ 
                    display: inline-block; 
                    padding: 12px 30px; 
                    background-color: #007bff; 
                    color: white; 
                    text-decoration: none; 
                    border-radius: 5px; 
                    margin: 20px 0;
                }}
                .footer {{ margin-top: 30px; font-size: 12px; color: #666; }}
            </style>
        </head>
        <body>
            <div class="container">
                <div class="header">
                    <h1>Welcome to LyoApp, {user_name}!</h1>
                </div>
                
                <p>Thank you for signing up for LyoApp. To complete your registration and verify your email address, please click the button below:</p>
                
                <div style="text-align: center;">
                    <a href="{verification_url}" class="button">Verify Email Address</a>
                </div>
                
                <p>If the button doesn't work, you can copy and paste this link into your browser:</p>
                <p style="word-break: break-all; color: #007bff;">{verification_url}</p>
                
                <p><strong>Important:</strong> This verification link will expire in 24 hours for security reasons.</p>
                
                <div class="footer">
                    <p>If you didn't create an account with LyoApp, please ignore this email.</p>
                    <p>This is an automated email. Please do not reply to this message.</p>
                </div>
            </div>
        </body>
        </html>
        """
        
        # Create and send email
        msg = create_email_message(email, subject, html_body)
        success = send_email_via_smtp(msg)
        
        if success:
            logger.info(f"Verification email sent successfully to {email[:3]}***")
            return True
        else:
            logger.error(f"Failed to send verification email to {email[:3]}***")
            raise Exception("SMTP delivery failed")
            
    except Exception as e:
        logger.error(f"Verification email task failed: {str(e)}")
        
        # Retry with exponential backoff
        if self.request.retries < self.max_retries:
            countdown = 2 ** self.request.retries * 60  # 1, 2, 4 minutes
            logger.info(f"Retrying verification email in {countdown} seconds...")
            raise self.retry(countdown=countdown)
        
        return False


@celery_app.task(bind=True, max_retries=3, default_retry_delay=60)
def send_password_reset_email_background(self, email: str, reset_url: str, user_name: str):
    """
    Background task to send password reset email.
    
    Args:
        email: Recipient email address
        reset_url: Password reset URL with token
        user_name: User's display name
        
    Returns:
        True if successful, False otherwise
    """
    try:
        # Log safely
        safe_token = get_safe_token_for_logging(reset_url.split('token=')[-1] if 'token=' in reset_url else '')
        logger.info(f"Sending password reset email to {email[:3]}*** with token hash {safe_token}")
        
        subject = "Reset Your LyoApp Password"
        html_body = f"""
        <!DOCTYPE html>
        <html>
        <head>
            <meta charset="utf-8">
            <title>Password Reset</title>
            <style>
                body {{ font-family: Arial, sans-serif; line-height: 1.6; color: #333; }}
                .container {{ max-width: 600px; margin: 0 auto; padding: 20px; }}
                .header {{ text-align: center; margin-bottom: 30px; }}
                .button {{ 
                    display: inline-block; 
                    padding: 12px 30px; 
                    background-color: #dc3545; 
                    color: white; 
                    text-decoration: none; 
                    border-radius: 5px; 
                    margin: 20px 0;
                }}
                .footer {{ margin-top: 30px; font-size: 12px; color: #666; }}
                .warning {{ background-color: #fff3cd; padding: 15px; border-radius: 5px; margin: 20px 0; }}
            </style>
        </head>
        <body>
            <div class="container">
                <div class="header">
                    <h1>Password Reset Request</h1>
                </div>
                
                <p>Hi {user_name},</p>
                
                <p>We received a request to reset your LyoApp password. If you made this request, click the button below to reset your password:</p>
                
                <div style="text-align: center;">
                    <a href="{reset_url}" class="button">Reset Password</a>
                </div>
                
                <p>If the button doesn't work, you can copy and paste this link into your browser:</p>
                <p style="word-break: break-all; color: #dc3545;">{reset_url}</p>
                
                <div class="warning">
                    <p><strong>Security Notice:</strong></p>
                    <ul>
                        <li>This password reset link will expire in 1 hour</li>
                        <li>If you didn't request this reset, please ignore this email</li>
                        <li>Your password will remain unchanged until you create a new one</li>
                    </ul>
                </div>
                
                <div class="footer">
                    <p>For security reasons, this link can only be used once.</p>
                    <p>This is an automated email. Please do not reply to this message.</p>
                    <p>If you need help, please contact our support team.</p>
                </div>
            </div>
        </body>
        </html>
        """
        
        # Create and send email
        msg = create_email_message(email, subject, html_body)
        success = send_email_via_smtp(msg)
        
        if success:
            logger.info(f"Password reset email sent successfully to {email[:3]}***")
            return True
        else:
            logger.error(f"Failed to send password reset email to {email[:3]}***")
            raise Exception("SMTP delivery failed")
            
    except Exception as e:
        logger.error(f"Password reset email task failed: {str(e)}")
        
        # Retry with exponential backoff
        if self.request.retries < self.max_retries:
            countdown = 2 ** self.request.retries * 60  # 1, 2, 4 minutes
            logger.info(f"Retrying password reset email in {countdown} seconds...")
            raise self.retry(countdown=countdown)
        
        return False


@celery_app.task
def send_welcome_email_background(email: str, user_name: str):
    """
    Background task to send welcome email to new users.
    
    Args:
        email: Recipient email address
        user_name: User's display name
        
    Returns:
        True if successful, False otherwise
    """
    try:
        logger.info(f"Sending welcome email to {email[:3]}***")
        
        subject = "Welcome to LyoApp!"
        html_body = f"""
        <!DOCTYPE html>
        <html>
        <head>
            <meta charset="utf-8">
            <title>Welcome to LyoApp</title>
            <style>
                body {{ font-family: Arial, sans-serif; line-height: 1.6; color: #333; }}
                .container {{ max-width: 600px; margin: 0 auto; padding: 20px; }}
                .header {{ text-align: center; margin-bottom: 30px; }}
                .feature {{ margin: 15px 0; padding: 10px; background-color: #f8f9fa; border-radius: 5px; }}
                .footer {{ margin-top: 30px; font-size: 12px; color: #666; }}
            </style>
        </head>
        <body>
            <div class="container">
                <div class="header">
                    <h1>Welcome to LyoApp, {user_name}! 🎉</h1>
                </div>
                
                <p>Congratulations! Your email has been verified and your account is now active.</p>
                
                <h2>What you can do with LyoApp:</h2>
                
                <div class="feature">
                    <h3>📚 Learn & Grow</h3>
                    <p>Access personalized learning paths and track your progress.</p>
                </div>
                
                <div class="feature">
                    <h3>👥 Connect & Share</h3>
                    <p>Join communities, share insights, and learn from others.</p>
                </div>
                
                <div class="feature">
                    <h3>🏆 Earn Achievements</h3>
                    <p>Complete challenges, earn XP, and climb the leaderboards.</p>
                </div>
                
                <p>Ready to get started? Log in to your account and explore what LyoApp has to offer!</p>
                
                <div class="footer">
                    <p>If you have any questions, don't hesitate to reach out to our support team.</p>
                    <p>Thank you for choosing LyoApp!</p>
                </div>
            </div>
        </body>
        </html>
        """
        
        # Create and send email
        msg = create_email_message(email, subject, html_body)
        success = send_email_via_smtp(msg)
        
        if success:
            logger.info(f"Welcome email sent successfully to {email[:3]}***")
            return True
        else:
            logger.error(f"Failed to send welcome email to {email[:3]}***")
            return False
            
    except Exception as e:
        logger.error(f"Welcome email task failed: {str(e)}")
        return False
