"""Email service for sending notifications via Microsoft Graph API (Outlook)."""
from __future__ import annotations

import os
from datetime import datetime, time
from typing import Any, Dict, List, Optional

try:
    from msal import ConfidentialClientApplication
    MSAL_AVAILABLE = True
except ImportError:
    MSAL_AVAILABLE = False

import requests


class EmailService:
    """Service for sending emails via Microsoft Graph API."""

    def __init__(
        self,
        tenant_id: str,
        client_id: str,
        client_secret: str,
        from_email: str,
    ):
        """Initialize the email service with Azure credentials.
        
        Args:
            tenant_id: Azure tenant ID
            client_id: Azure client ID
            client_secret: Azure client secret
            from_email: Email address (UPN) to send from - must be a valid user in your Azure tenant
        """
        if not MSAL_AVAILABLE:
            raise RuntimeError(
                "msal library is not available. Install it with: pip install msal"
            )
        
        if not from_email or "@" not in from_email:
            raise ValueError(
                "from_email must be a valid email address (UPN). "
                "Microsoft Graph API requires an actual user email address, not a client ID."
            )
        
        self.tenant_id = tenant_id
        self.client_id = client_id
        self.client_secret = client_secret
        self.from_email = from_email
        
        # Microsoft Graph API endpoints
        self.authority = f"https://login.microsoftonline.com/{tenant_id}"
        self.graph_endpoint = "https://graph.microsoft.com/v1.0"
        
        # Initialize MSAL app
        self.app = ConfidentialClientApplication(
            client_id=client_id,
            client_credential=client_secret,
            authority=self.authority,
        )
    
    @classmethod
    def from_env(cls) -> EmailService:
        """Create EmailService instance from environment variables.
        
        Requires:
            AZURE_TENANT_ID: Azure tenant ID
            AZURE_CLIENT_ID: Azure client ID
            AZURE_CLIENT_SECRET: Azure client secret
            EMAIL_FROM: Email address (UPN) to send from - must be a valid user in your Azure tenant
        
        Raises:
            RuntimeError: If required environment variables are missing
        """
        tenant_id = os.getenv("AZURE_TENANT_ID", "").strip()
        client_id = os.getenv("AZURE_CLIENT_ID", "").strip()
        client_secret = os.getenv("AZURE_CLIENT_SECRET", "").strip()
        from_email = os.getenv("EMAIL_FROM", "").strip()
        
        if not tenant_id or not client_id or not client_secret:
            raise RuntimeError(
                "AZURE_TENANT_ID, AZURE_CLIENT_ID, and AZURE_CLIENT_SECRET environment variables are required"
            )
        
        if not from_email:
            raise RuntimeError(
                "EMAIL_FROM environment variable is required. "
                "This must be a valid email address (UPN) of a user in your Azure tenant. "
                "The Azure app must have 'Mail.Send' permission for this user."
            )
        
        return cls(tenant_id, client_id, client_secret, from_email)
    
    def _get_access_token(self) -> str:
        """Get access token for Microsoft Graph API.
        
        Returns:
            Access token string
            
        Raises:
            RuntimeError: If authentication fails
        """
        try:
            # Request token for Microsoft Graph API
            result = self.app.acquire_token_for_client(
                scopes=["https://graph.microsoft.com/.default"]
            )
            
            if "access_token" in result:
                return result["access_token"]
            else:
                error = result.get("error_description", result.get("error", "Unknown error"))
                raise RuntimeError(f"Failed to acquire access token: {error}")
        except Exception as e:
            raise RuntimeError(f"Error acquiring access token: {e}") from e
    
    def send_email(
        self,
        to_recipients: List[str],
        subject: str,
        body_html: str,
        body_text: Optional[str] = None,
        cc_recipients: Optional[List[str]] = None,
    ) -> bool:
        """Send an email via Microsoft Graph API.
        
        Args:
            to_recipients: List of email addresses to send to
            subject: Email subject
            body_html: HTML email body
            body_text: Plain text email body (optional, will use body_html if not provided)
            cc_recipients: List of email addresses to CC (optional)
            
        Returns:
            True if email was sent successfully, False otherwise
        """
        if not to_recipients:
            raise ValueError("At least one recipient is required")
        
        # Get access token
        access_token = self._get_access_token()
        
        # Prepare email message
        message = {
            "message": {
                "subject": subject,
                "body": {
                    "contentType": "HTML",
                    "content": body_html,
                },
                "toRecipients": [
                    {"emailAddress": {"address": email}} for email in to_recipients
                ],
            }
        }
        
        # Add CC recipients if provided
        if cc_recipients:
            message["message"]["ccRecipients"] = [
                {"emailAddress": {"address": email}} for email in cc_recipients
            ]
        
        # Add plain text body if provided
        if body_text:
            # Note: Microsoft Graph API doesn't support separate plain text body
            # We'll include it in the HTML body as a fallback
            pass
        
        # Send email via Microsoft Graph API
        # Note: This requires:
        # 1. The app to have "Mail.Send" application permission (not delegated)
        # 2. Admin consent granted for the permission
        # 3. The from_email must be a valid user principal name (UPN) in your Azure tenant
        # 4. The app must be granted permission to send mail on behalf of that user
        url = f"{self.graph_endpoint}/users/{self.from_email}/sendMail"
        
        headers = {
            "Authorization": f"Bearer {access_token}",
            "Content-Type": "application/json",
        }
        
        try:
            response = requests.post(url, json=message, headers=headers, timeout=30)
            response.raise_for_status()
            return True
        except requests.exceptions.RequestException as e:
            print(f"Error sending email: {e}")
            if hasattr(e, 'response') and e.response is not None:
                print(f"Response status: {e.response.status_code}")
                print(f"Response body: {e.response.text}")
            return False
    
    def send_test_email(
        self,
        to_recipients: List[str],
        cc_recipients: Optional[List[str]] = None,
    ) -> bool:
        """Send a test email.
        
        Args:
            to_recipients: List of email addresses to send to
            cc_recipients: List of email addresses to CC (optional)
            
        Returns:
            True if email was sent successfully, False otherwise
        """
        subject = "Dashboard Alert System - Test Email"
        body_html = """
        <html>
        <body style="font-family: Arial, sans-serif; line-height: 1.6; color: #333;">
            <h2 style="color: #0ea5e9;">Dashboard Alert System Test</h2>
            <p>This is a test email from the Dashboard Alert System.</p>
            <p>If you received this email, your email configuration is working correctly.</p>
            <hr style="border: none; border-top: 1px solid #e5e7eb; margin: 20px 0;">
            <p style="font-size: 12px; color: #6b7280;">
                This is an automated test message. Please do not reply.
            </p>
        </body>
        </html>
        """
        
        return self.send_email(
            to_recipients=to_recipients,
            subject=subject,
            body_html=body_html,
            cc_recipients=cc_recipients,
        )
    
    def send_alert_report(
        self,
        to_recipients: List[str],
        month_start: date,
        month_end: date,
        internal_external_imbalance: Optional[Dict[str, Any]] = None,
        cc_recipients: Optional[List[str]] = None,
    ) -> bool:
        """Send an alert report email.
        
        Args:
            to_recipients: List of email addresses to send to
            month_start: Start date of the month
            month_end: End date of the month
            internal_external_imbalance: Internal/external imbalance data (optional)
            cc_recipients: List of email addresses to CC (optional)
            
        Returns:
            True if email was sent successfully, False otherwise
        """
        month_name = month_start.strftime("%B %Y")
        subject = f"Dashboard Alert Report - {month_name}"
        
        # Build HTML body
        body_parts = []
        body_parts.append(f"""
        <html>
        <body style="font-family: Arial, sans-serif; line-height: 1.6; color: #333; max-width: 800px; margin: 0 auto; padding: 20px;">
            <h1 style="color: #0ea5e9; border-bottom: 2px solid #0ea5e9; padding-bottom: 10px;">
                Dashboard Alert Report
            </h1>
            <p style="font-size: 14px; color: #6b7280; margin-bottom: 30px;">
                Report for <strong>{month_name}</strong>
            </p>
        """)
        
        # Add internal/external imbalance section if provided
        if internal_external_imbalance and internal_external_imbalance.get("count", 0) > 0:
            imbalance_count = internal_external_imbalance["count"]
            projects = internal_external_imbalance["projects"]
            
            body_parts.append(f"""
            <div style="margin-bottom: 30px;">
                <h2 style="color: #dc2626; font-size: 18px; margin-bottom: 15px;">
                    Internal vs External Hours Imbalance
                </h2>
                <p style="margin-bottom: 15px;">
                    <strong>{imbalance_count}</strong> project{'s' if imbalance_count != 1 else ''} {'have' if imbalance_count != 1 else 'has'} been detected with imbalanced internal vs external hours.
                </p>
                <table style="width: 100%; border-collapse: collapse; border: 1px solid #e5e7eb; margin-top: 15px;">
                    <thead>
                        <tr style="background-color: #f9fafb;">
                            <th style="padding: 12px; text-align: left; border: 1px solid #e5e7eb; font-weight: 600;">Project</th>
                            <th style="padding: 12px; text-align: left; border: 1px solid #e5e7eb; font-weight: 600;">Market</th>
                            <th style="padding: 12px; text-align: left; border: 1px solid #e5e7eb; font-weight: 600;">Agreement Type</th>
                            <th style="padding: 12px; text-align: right; border: 1px solid #e5e7eb; font-weight: 600;">Imbalance Degree</th>
                        </tr>
                    </thead>
                    <tbody>
            """)
            
            for project in projects:
                project_name = project.get("project_name", "Unknown")
                market = project.get("market", "Unknown")
                agreement_type = project.get("agreement_type", "Unknown")
                imbalance_degree = project.get("imbalance_degree", 0.0)
                imbalance_display = f"{imbalance_degree:.1f}h"
                
                body_parts.append(f"""
                        <tr>
                            <td style="padding: 10px; border: 1px solid #e5e7eb;">{project_name}</td>
                            <td style="padding: 10px; border: 1px solid #e5e7eb;">{market}</td>
                            <td style="padding: 10px; border: 1px solid #e5e7eb;">{agreement_type}</td>
                            <td style="padding: 10px; border: 1px solid #e5e7eb; text-align: right; color: #dc2626; font-weight: 600;">{imbalance_display}</td>
                        </tr>
                """)
            
            body_parts.append("""
                    </tbody>
                </table>
            </div>
            """)
        
        body_parts.append("""
            <hr style="border: none; border-top: 1px solid #e5e7eb; margin: 30px 0;">
            <p style="font-size: 12px; color: #6b7280;">
                This is an automated report from the Dashboard Alert System. Please do not reply.
            </p>
        </body>
        </html>
        """)
        
        body_html = "".join(body_parts)
        
        return self.send_email(
            to_recipients=to_recipients,
            subject=subject,
            body_html=body_html,
            cc_recipients=cc_recipients,
        )
