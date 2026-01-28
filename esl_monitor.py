#!/usr/bin/env python3
"""
Santa Clara Adult Education ESL Registration Monitor
Checks for registration announcements and links, sends email notifications
Designed to run on GitHub Actions
"""

import requests
from bs4 import BeautifulSoup
import json
import os
from datetime import datetime
import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart

# Configuration
URL = "https://www.santaclaraadulted.org/esl/#SignupforEnglishClasses"
STATE_FILE = "page_state.json"

# Email configuration - will be set via GitHub Secrets
GMAIL_USER = os.environ.get('GMAIL_USER')
GMAIL_APP_PASSWORD = os.environ.get('GMAIL_APP_PASSWORD')
RECIPIENT_EMAIL = os.environ.get('RECIPIENT_EMAIL')
SMS_EMAIL = os.environ.get('SMS_EMAIL', '')  # Optional


def log_message(message):
    """Log messages with timestamp"""
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    print(f"[{timestamp}] {message}")


def fetch_page_content():
    """Fetch the webpage content"""
    try:
        headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'
        }
        response = requests.get(URL, headers=headers, timeout=30)
        response.raise_for_status()
        return response.text
    except Exception as e:
        log_message(f"Error fetching page: {e}")
        return None


def extract_page_info(html_content):
    """Extract relevant information from the page"""
    soup = BeautifulSoup(html_content, 'html.parser')
    
    # Find the ESL section
    esl_section = soup.find('section', id='SignupforEnglishClasses')
    if not esl_section:
        esl_section = soup  # Fall back to whole page
    
    info = {
        'registration_text': [],
        'links': [],
        'full_text': ''
    }
    
    # Look for registration announcement keywords
    keywords = [
        'registration opens',
        'the next registration will be',
        'registration will be on',
        'register online',
        'january',
        'february',
        'march',
        'april',
        'may',
        'june',
        'july',
        'august',
        'september',
        'october',
        'november',
        'december'
    ]
    
    # Get all text from the section
    text_content = esl_section.get_text(separator=' ', strip=True)
    info['full_text'] = text_content.lower()
    
    # Check for registration-related text
    for keyword in keywords:
        if keyword in info['full_text']:
            # Find the sentence or paragraph containing this keyword
            sentences = text_content.split('.')
            for sentence in sentences:
                if keyword in sentence.lower():
                    info['registration_text'].append(sentence.strip())
    
    # Extract all links in the section
    links = esl_section.find_all('a', href=True)
    for link in links:
        href = link['href']
        link_text = link.get_text(strip=True)
        
        # Filter for likely registration links
        registration_keywords = ['register', 'registration', 'sign up', 'signup', 'enroll']
        if any(kw in link_text.lower() or kw in href.lower() for kw in registration_keywords):
            info['links'].append({
                'text': link_text,
                'url': href if href.startswith('http') else f"https://www.santaclaraadulted.org{href}"
            })
    
    return info


def load_previous_state():
    """Load the previous page state from GitHub repository"""
    if os.path.exists(STATE_FILE):
        try:
            with open(STATE_FILE, 'r') as f:
                return json.load(f)
        except Exception as e:
            log_message(f"Error loading state: {e}")
    return None


def save_current_state(state):
    """Save the current page state"""
    try:
        with open(STATE_FILE, 'w') as f:
            json.dump(state, f, indent=2)
    except Exception as e:
        log_message(f"Error saving state: {e}")


def send_email(subject, body, is_html=False):
    """Send email notification via Gmail"""
    try:
        msg = MIMEMultipart('alternative')
        msg['From'] = GMAIL_USER
        msg['To'] = RECIPIENT_EMAIL
        msg['Subject'] = subject
        
        if is_html:
            msg.attach(MIMEText(body, 'html'))
        else:
            msg.attach(MIMEText(body, 'plain'))
        
        # Send to email
        with smtplib.SMTP_SSL('smtp.gmail.com', 465) as server:
            server.login(GMAIL_USER, GMAIL_APP_PASSWORD)
            server.send_message(msg)
        
        log_message(f"Email sent: {subject}")
        
        # Optional: Send to SMS email gateway
        if SMS_EMAIL:
            try:
                sms_msg = MIMEText(f"{subject}\n\n{body[:160]}")  # SMS messages are typically limited
                sms_msg['From'] = GMAIL_USER
                sms_msg['To'] = SMS_EMAIL
                sms_msg['Subject'] = subject
                
                with smtplib.SMTP_SSL('smtp.gmail.com', 465) as server:
                    server.login(GMAIL_USER, GMAIL_APP_PASSWORD)
                    server.send_message(sms_msg)
                log_message("SMS notification sent")
            except Exception as e:
                log_message(f"Error sending SMS: {e}")
        
        return True
    except Exception as e:
        log_message(f"Error sending email: {e}")
        return False


def check_for_changes():
    """Main function to check for changes"""
    log_message("=" * 50)
    log_message("Starting page check")
    
    # Verify email configuration
    if not GMAIL_USER or not GMAIL_APP_PASSWORD or not RECIPIENT_EMAIL:
        log_message("ERROR: Email configuration missing. Check GitHub Secrets.")
        return
    
    # Fetch current page
    html_content = fetch_page_content()
    if not html_content:
        log_message("Failed to fetch page, will retry next time")
        return
    
    # Extract information
    current_info = extract_page_info(html_content)
    
    # Load previous state
    previous_state = load_previous_state()
    
    if previous_state is None:
        # First run - save state and send initialization email
        log_message("First run - initializing")
        save_current_state(current_info)
        send_email(
            "ESL Monitor Started",
            f"Monitoring has begun for Santa Clara Adult Education ESL registration.\n\n"
            f"Current links found: {len(current_info['links'])}\n"
            f"URL: {URL}\n\n"
            f"You'll receive alerts when registration announcements or new links are detected."
        )
        return
    
    # Check for changes
    changes_detected = []
    
    # Check for new registration text
    new_registration_text = [text for text in current_info['registration_text'] 
                            if text not in previous_state.get('registration_text', [])]
    
    if new_registration_text:
        changes_detected.append("REGISTRATION ANNOUNCEMENT")
        log_message(f"New registration text detected: {len(new_registration_text)} items")
    
    # Check for new links
    previous_links = {link['url'] for link in previous_state.get('links', [])}
    current_links = {link['url'] for link in current_info['links']}
    new_links = current_links - previous_links
    
    if new_links:
        changes_detected.append("NEW REGISTRATION LINK")
        log_message(f"New links detected: {len(new_links)}")
    
    # Send notification if changes detected
    if changes_detected:
        # Build email
        subject = f"🚨 ESL ALERT: {' & '.join(changes_detected)}"
        
        body_parts = ["Santa Clara Adult Education ESL Registration Update!\n\n"]
        
        if new_registration_text:
            body_parts.append("📅 NEW ANNOUNCEMENT DETECTED:\n")
            for text in new_registration_text:
                body_parts.append(f"  • {text}\n")
            body_parts.append("\n")
        
        if new_links:
            body_parts.append("🔗 NEW REGISTRATION LINKS:\n")
            new_link_objects = [link for link in current_info['links'] if link['url'] in new_links]
            for link in new_link_objects:
                body_parts.append(f"  • {link['text']}\n")
                body_parts.append(f"    {link['url']}\n")
            body_parts.append("\n")
        
        body_parts.append(f"Check the full page here:\n{URL}\n\n")
        body_parts.append(f"Detected at: {datetime.now().strftime('%Y-%m-%d %I:%M %p')}")
        
        body = "".join(body_parts)
        
        send_email(subject, body)
        
        # Update state
        save_current_state(current_info)
        log_message("State updated with new information")
    else:
        log_message("No changes detected")
    
    log_message("Check completed")


if __name__ == "__main__":
    check_for_changes()
