"""
Secure Contact Form Handler
Handles contact form submissions with rate limiting, validation, and email notifications.
"""

import os
import re
from datetime import datetime, timedelta
from flask import Blueprint, jsonify, request
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
import smtplib
from typing import Dict, Optional, Tuple
import html
import logging

import resend

from data_store import is_supabase_database_configured, save_contact_message
from seo import SUPPORT_EMAIL

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Create Blueprint
contact_bp = Blueprint('contact', __name__)

# Rate limiting storage (in production, use Redis or similar)
# Format: {ip_address: {'count': int, 'reset_time': datetime}}
rate_limit_store: Dict[str, Dict] = {}

# Configuration
MAX_REQUESTS_PER_HOUR = 5
MAX_MESSAGE_LENGTH = 2000
MAX_EMAIL_LENGTH = 254
MAX_SUBJECT_LENGTH = 200

# Email configuration (load from environment variables)
RESEND_API_KEY = os.getenv("RESEND_API_KEY", "").strip()
CONTACT_FROM_EMAIL = os.getenv(
    "CONTACT_FROM_EMAIL",
    os.getenv("RESEND_FROM_EMAIL", f"Welcome to Trades <{SUPPORT_EMAIL}>"),
).strip()
SMTP_SERVER = os.getenv('SMTP_SERVER', 'smtp.gmail.com')
SMTP_PORT = int(os.getenv('SMTP_PORT', '587'))
SMTP_USERNAME = os.getenv('SMTP_USERNAME')
SMTP_PASSWORD = os.getenv('SMTP_PASSWORD')
# Support multiple recipients separated by comma
CONTACT_EMAILS = os.getenv("CONTACT_EMAIL", SUPPORT_EMAIL)

# Google reCAPTCHA configuration
RECAPTCHA_SECRET_KEY = os.getenv('RECAPTCHA_SECRET_KEY')
RECAPTCHA_SITE_KEY = os.getenv('RECAPTCHA_SITE_KEY')  # This will be exposed to frontend (it's public)
RECAPTCHA_VERIFY_URL = 'https://www.google.com/recaptcha/api/siteverify'


def get_client_ip() -> str:
    """Get client IP address, considering proxies."""
    if request.headers.get('X-Forwarded-For'):
        # Get the first IP from the X-Forwarded-For header
        return request.headers.get('X-Forwarded-For').split(',')[0].strip()
    elif request.headers.get('X-Real-IP'):
        return request.headers.get('X-Real-IP')
    return request.remote_addr


def check_rate_limit(ip: str) -> Tuple[bool, Optional[int]]:
    """
    Check if the IP has exceeded rate limit.
    Returns: (is_allowed, seconds_until_reset)
    """
    current_time = datetime.now()
    
    # Clean up old entries
    expired_ips = [
        ip_addr for ip_addr, data in rate_limit_store.items()
        if data['reset_time'] < current_time
    ]
    for ip_addr in expired_ips:
        del rate_limit_store[ip_addr]
    
    # Check current IP
    if ip not in rate_limit_store:
        rate_limit_store[ip] = {
            'count': 1,
            'reset_time': current_time + timedelta(hours=1)
        }
        return True, None
    
    ip_data = rate_limit_store[ip]
    
    if current_time >= ip_data['reset_time']:
        # Reset the counter
        rate_limit_store[ip] = {
            'count': 1,
            'reset_time': current_time + timedelta(hours=1)
        }
        return True, None
    
    if ip_data['count'] >= MAX_REQUESTS_PER_HOUR:
        seconds_left = int((ip_data['reset_time'] - current_time).total_seconds())
        return False, seconds_left
    
    # Increment counter
    ip_data['count'] += 1
    return True, None


def validate_email(email: str) -> bool:
    """Validate email format."""
    if not email or len(email) > MAX_EMAIL_LENGTH:
        return False
    
    # RFC 5322 compliant email regex (simplified)
    pattern = r'^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$'
    return re.match(pattern, email) is not None


def sanitize_input(text: str, max_length: int) -> str:
    """Sanitize user input to prevent XSS and injection attacks."""
    if not text:
        return ""
    
    # Limit length
    text = text[:max_length]
    
    # Remove null bytes
    text = text.replace('\x00', '')
    
    # Escape HTML entities
    text = html.escape(text)
    
    # Remove control characters except newlines and tabs
    text = ''.join(char for char in text if char in '\n\t' or (char.isprintable() and ord(char) >= 32))
    
    return text.strip()


def validate_honeypot() -> bool:
    """
    Check honeypot field (invisible to humans, visible to bots).
    If filled, it's likely a bot.
    """
    honeypot = request.json.get('website', '')
    return honeypot == ''


def verify_recaptcha(token: str) -> Tuple[bool, Optional[float]]:
    """
    Verify Google reCAPTCHA v3 token.
    Returns: (is_valid, score)
    Score ranges from 0.0 (bot) to 1.0 (human). Recommended threshold: 0.5
    """
    if not RECAPTCHA_SECRET_KEY:
        logger.warning("reCAPTCHA secret key not configured - skipping verification")
        return True, None
    
    try:
        import requests as req
        response = req.post(RECAPTCHA_VERIFY_URL, data={
            'secret': RECAPTCHA_SECRET_KEY,
            'response': token
        }, timeout=5)
        
        result = response.json()
        
        if not result.get('success'):
            logger.warning(f"reCAPTCHA verification failed: {result.get('error-codes')}")
            return False, None
        
        score = result.get('score', 0.0)
        logger.info(f"reCAPTCHA score: {score}")
        
        # Return success if score is above threshold (0.5 is recommended by Google)
        return score >= 0.5, score
        
    except Exception as e:
        logger.error(f"reCAPTCHA verification error: {str(e)}")
        # Fail open (allow submission) if reCAPTCHA service is down
        return True, None


def _parse_recipient_emails(recipient_emails: str) -> list[str]:
    return [email.strip() for email in recipient_emails.split(',') if email.strip()]


def _build_contact_email_content(
    subject: str,
    message: str,
    sender_email: str,
) -> tuple[str, str, str]:
    sanitized_subject = sanitize_input(subject, MAX_SUBJECT_LENGTH)
    client_ip = get_client_ip()
    timestamp = datetime.now().isoformat()

    text_content = f"""Contact Form Submission

From: {sender_email}
Subject: {subject}

Message:
{message}

---
Sent from Welcome to Trades Contact Form
IP Address: {client_ip}
Timestamp: {timestamp}
"""

    html_content = f"""
<html>
  <body style="font-family: Arial, sans-serif; line-height: 1.6; color: #333;">
    <div style="max-width: 600px; margin: 0 auto; padding: 20px; border: 1px solid #ddd; border-radius: 5px;">
      <h2 style="color: #e53935; border-bottom: 2px solid #e53935; padding-bottom: 10px;">Contact Form Submission</h2>

      <p><strong>From:</strong> {html.escape(sender_email)}</p>
      <p><strong>Subject:</strong> {html.escape(subject)}</p>

      <div style="background-color: #f9f9f9; padding: 15px; border-left: 4px solid #e53935; margin: 20px 0;">
        <p><strong>Message:</strong></p>
        <p style="white-space: pre-wrap;">{html.escape(message)}</p>
      </div>

      <div style="margin-top: 30px; padding-top: 20px; border-top: 1px solid #ddd; font-size: 0.9em; color: #666;">
        <p>Sent from Welcome to Trades Contact Form</p>
        <p>IP Address: {html.escape(client_ip)}</p>
        <p>Timestamp: {timestamp}</p>
      </div>
    </div>
  </body>
</html>
"""
    return sanitized_subject, text_content, html_content


def _send_email_via_resend(
    *,
    recipients: list[str],
    subject: str,
    text_content: str,
    html_content: str,
    sender_email: str,
) -> bool:
    if not RESEND_API_KEY:
        return False

    try:
        resend.api_key = RESEND_API_KEY
        resend.Emails.send(
            {
                "from": CONTACT_FROM_EMAIL,
                "to": recipients,
                "reply_to": sender_email,
                "subject": subject,
                "html": html_content,
                "text": text_content,
            }
        )
        logger.info("Contact form email sent via Resend from %s", sender_email)
        return True
    except Exception as exc:
        logger.error("Resend delivery failed: %s", exc)
        return False


def _send_email_via_smtp(
    *,
    recipients: list[str],
    subject: str,
    text_content: str,
    html_content: str,
    sender_email: str,
) -> bool:
    if not SMTP_USERNAME or not SMTP_PASSWORD:
        return False

    try:
        msg = MIMEMultipart('alternative')
        msg['Subject'] = subject
        msg['From'] = SMTP_USERNAME
        msg['To'] = ', '.join(recipients)
        msg['Reply-To'] = sender_email

        msg.attach(MIMEText(text_content, 'plain', 'utf-8'))
        msg.attach(MIMEText(html_content, 'html', 'utf-8'))

        with smtplib.SMTP(SMTP_SERVER, SMTP_PORT, timeout=20) as server:
            server.starttls()
            server.login(SMTP_USERNAME, SMTP_PASSWORD)
            server.send_message(msg)

        logger.info("Contact form email sent via SMTP from %s", sender_email)
        return True
    except Exception as exc:
        logger.error("SMTP delivery failed: %s", exc)
        return False


def send_email(recipient_emails: str, subject: str, message: str, sender_email: str) -> bool:
    """
    Send email notification securely to multiple recipients.
    Prefers Resend (HTTPS) on Railway; falls back to SMTP for local dev.
    """
    recipients = _parse_recipient_emails(recipient_emails)
    if not recipients:
        logger.error("No valid recipient email addresses")
        return False

    sanitized_subject, text_content, html_content = _build_contact_email_content(
        subject=subject,
        message=message,
        sender_email=sender_email,
    )

    if RESEND_API_KEY:
        return _send_email_via_resend(
            recipients=recipients,
            subject=sanitized_subject,
            text_content=text_content,
            html_content=html_content,
            sender_email=sender_email,
        )

    if SMTP_USERNAME and SMTP_PASSWORD:
        return _send_email_via_smtp(
            recipients=recipients,
            subject=sanitized_subject,
            text_content=text_content,
            html_content=html_content,
            sender_email=sender_email,
        )

    logger.error(
        "No email delivery configured. Set RESEND_API_KEY (recommended on Railway) "
        "or SMTP_USERNAME/SMTP_PASSWORD."
    )
    return False


@contact_bp.route('/api/contact', methods=['POST'])
def handle_contact_form():
    """
    Handle contact form submissions securely.
    """
    try:
        # Check if request is JSON
        if not request.is_json:
            return jsonify({'error': 'Invalid content type. Expected application/json'}), 400
        
        data = request.get_json(silent=True) or {}

        # Get client IP
        client_ip = get_client_ip()
        
        # Check rate limit
        allowed, seconds_left = check_rate_limit(client_ip)
        if not allowed:
            logger.warning(f"Rate limit exceeded for IP: {client_ip}")
            return jsonify({
                'error': f'Too many requests. Please try again in {seconds_left} seconds.'
            }), 429
        
        # Validate honeypot (bot protection)
        if not validate_honeypot():
            logger.warning(f"Honeypot triggered for IP: {client_ip}")
            # Return success to fool bots
            return jsonify({'success': True, 'message': 'Thank you for your message!'}), 200
        
        recaptcha_token = data.get('recaptcha_token', '')
        if RECAPTCHA_SECRET_KEY and not recaptcha_token:
            return jsonify({'error': 'reCAPTCHA verification required'}), 400

        is_valid, score = verify_recaptcha(recaptcha_token)
        if not is_valid:
            logger.warning(f"reCAPTCHA failed for IP: {client_ip}, score: {score}")
            return jsonify({'error': 'reCAPTCHA verification failed. Please try again.'}), 400

        email = data.get('email', '').strip()
        subject = data.get('subject', '').strip()
        message = data.get('message', '').strip()
        
        # Validate email
        if not validate_email(email):
            return jsonify({'error': 'Invalid email address'}), 400
        
        # Validate subject
        if not subject or len(subject) < 3:
            return jsonify({'error': 'Subject must be at least 3 characters'}), 400
        
        if len(subject) > MAX_SUBJECT_LENGTH:
            return jsonify({'error': f'Subject must be less than {MAX_SUBJECT_LENGTH} characters'}), 400
        
        # Validate message
        if not message or len(message) < 10:
            return jsonify({'error': 'Message must be at least 10 characters'}), 400
        
        if len(message) > MAX_MESSAGE_LENGTH:
            return jsonify({'error': f'Message must be less than {MAX_MESSAGE_LENGTH} characters'}), 400
        
        # Sanitize inputs
        email = sanitize_input(email, MAX_EMAIL_LENGTH)
        subject = sanitize_input(subject, MAX_SUBJECT_LENGTH)
        message = sanitize_input(message, MAX_MESSAGE_LENGTH)

        email_sent = send_email(
            recipient_emails=CONTACT_EMAILS,
            subject=f"Contact Form: {subject}",
            message=message,
            sender_email=email,
        )

        delivery_status = 'emailed' if email_sent else 'stored_only'
        db_saved = False

        if is_supabase_database_configured():
            try:
                save_contact_message(
                    email=email,
                    subject=subject,
                    message=message,
                    ip_address=client_ip,
                    recaptcha_score=score,
                    delivery_status=delivery_status,
                )
                db_saved = True
            except Exception as db_error:
                logger.error(f"Failed to store contact message from {email}: {db_error}")

        if not email_sent and not db_saved:
            logger.error(f"Failed to deliver contact form from {email}")
            return jsonify({
                'error': 'Failed to send message. Please try again later or email us directly.'
            }), 500

        if not email_sent and db_saved:
            logger.warning(f"Contact form stored without email delivery from {email}")
        elif not email_sent:
            logger.error(f"Contact form failed email delivery and database save from {email}")
        
        # Log successful submission
        logger.info(f"Contact form submitted successfully from {email} (IP: {client_ip})")
        
        return jsonify({
            'success': True,
            'message': 'Thank you for your message! We received it and will get back to you soon.'
        }), 200
        
    except Exception as e:
        logger.error(f"Error handling contact form: {str(e)}")
        return jsonify({
            'error': 'An unexpected error occurred. Please try again later.'
        }), 500


PRICING_OPTIONS = {
    "7_days_100": "$100 for 7 days",
    "30_days_200": "$200 for 30 days",
}


def build_job_posting_message(data: dict) -> str:
    pricing_label = PRICING_OPTIONS.get(data.get("pricing_option", ""), data.get("pricing_option", ""))
    lines = [
        f"Company: {data.get('company_name', '')}",
        f"Job title: {data.get('job_title', '')}",
        f"Tags / stack: {data.get('tags') or '—'}",
        f"Salary range: {data.get('salary_range') or '—'}",
        "",
        "Job description:",
        data.get("job_description", ""),
        "",
        "How to apply:",
        data.get("apply_method", ""),
        "",
        f"Invoice email: {data.get('invoice_email', '')}",
        f"Pricing option: {pricing_label}",
    ]
    if data.get("questions"):
        lines.extend(["", "Questions / comments:", data["questions"]])
    return "\n".join(lines)


@contact_bp.route('/api/post-job', methods=['POST'])
def handle_post_job_form():
    """Handle employer job posting submissions."""
    try:
        if not request.is_json:
            return jsonify({'error': 'Invalid content type. Expected application/json'}), 400

        data = request.get_json(silent=True) or {}
        client_ip = get_client_ip()

        allowed, seconds_left = check_rate_limit(client_ip)
        if not allowed:
            return jsonify({
                'error': f'Too many requests. Please try again in {seconds_left} seconds.'
            }), 429

        if not validate_honeypot():
            return jsonify({
                'success': True,
                'message': 'Thank you! We received your job posting request.'
            }), 200

        recaptcha_token = data.get('recaptcha_token', '')
        if RECAPTCHA_SECRET_KEY and not recaptcha_token:
            return jsonify({'error': 'reCAPTCHA verification required'}), 400

        is_valid, score = verify_recaptcha(recaptcha_token)
        if not is_valid:
            return jsonify({'error': 'reCAPTCHA verification failed. Please try again.'}), 400

        company_name = sanitize_input(data.get('company_name', '').strip(), 120)
        job_title = sanitize_input(data.get('job_title', '').strip(), 160)
        tags = sanitize_input(data.get('tags', '').strip(), 240)
        salary_range = sanitize_input(data.get('salary_range', '').strip(), 120)
        job_description = sanitize_input(data.get('job_description', '').strip(), MAX_MESSAGE_LENGTH)
        apply_method = sanitize_input(data.get('apply_method', '').strip(), 1000)
        invoice_email = data.get('invoice_email', '').strip()
        questions = sanitize_input(data.get('questions', '').strip(), 1000)
        pricing_option = data.get('pricing_option', '').strip()

        if not company_name or not job_title:
            return jsonify({'error': 'Company name and job title are required.'}), 400
        if not job_description or len(job_description) < 20:
            return jsonify({'error': 'Job description must be at least 20 characters.'}), 400
        if not apply_method or len(apply_method) < 5:
            return jsonify({'error': 'Please tell us how candidates should apply.'}), 400
        if not validate_email(invoice_email):
            return jsonify({'error': 'Please enter a valid company email for invoicing.'}), 400
        if pricing_option not in PRICING_OPTIONS:
            return jsonify({'error': 'Please choose a pricing option.'}), 400

        invoice_email = sanitize_input(invoice_email, MAX_EMAIL_LENGTH)
        pricing_label = PRICING_OPTIONS[pricing_option]
        subject = f"Job Posting: {company_name} — {job_title} ({pricing_label})"
        message = build_job_posting_message({
            "company_name": company_name,
            "job_title": job_title,
            "tags": tags,
            "salary_range": salary_range,
            "job_description": job_description,
            "apply_method": apply_method,
            "invoice_email": invoice_email,
            "questions": questions,
            "pricing_option": pricing_option,
        })

        email_sent = send_email(
            recipient_emails=CONTACT_EMAILS,
            subject=subject,
            message=message,
            sender_email=invoice_email,
        )

        delivery_status = 'emailed' if email_sent else 'stored_only'
        db_saved = False

        if is_supabase_database_configured():
            try:
                save_contact_message(
                    email=invoice_email,
                    subject=subject,
                    message=message,
                    ip_address=client_ip,
                    recaptcha_score=score,
                    delivery_status=delivery_status,
                )
                db_saved = True
            except Exception as db_error:
                logger.error(f"Failed to store job posting from {invoice_email}: {db_error}")

        if not email_sent and not db_saved:
            return jsonify({
                "error": f"Failed to submit your posting. Please try again or email {SUPPORT_EMAIL}."
            }), 500

        logger.info(f"Job posting submitted by {invoice_email} (IP: {client_ip})")
        return jsonify({
            'success': True,
            'message': 'Thank you! We received your job posting request and will follow up with an invoice shortly.'
        }), 200

    except Exception as e:
        logger.error(f"Error handling job posting form: {str(e)}")
        return jsonify({
            'error': 'An unexpected error occurred. Please try again later.'
        }), 500


@contact_bp.route('/api/contact/config', methods=['GET'])
def get_config():
    """Return public configuration for frontend (reCAPTCHA site key)."""
    return jsonify({
        'recaptcha_site_key': RECAPTCHA_SITE_KEY,
        'recaptcha_enabled': bool(RECAPTCHA_SECRET_KEY)
    }), 200


@contact_bp.route('/api/contact/health', methods=['GET'])
def health_check():
    """Health check endpoint."""
    return jsonify({'status': 'healthy', 'timestamp': datetime.now().isoformat()}), 200
