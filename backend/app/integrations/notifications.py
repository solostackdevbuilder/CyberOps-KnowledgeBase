"""
Webhook notification service for sending messages to Teams and Slack.
"""
import logging
from typing import Optional

import httpx

logger = logging.getLogger(__name__)


def _is_power_automate_url(url: str) -> bool:
    """Check if the URL is a Power Automate flow URL."""
    return "powerautomate" in url.lower() or "powerplatform" in url.lower() or "logic.azure.com" in url.lower()


async def send_teams_notification(webhook_url: str, message: dict) -> bool:
    """
    Send a notification to Microsoft Teams via webhook.
    
    Args:
        webhook_url: Teams webhook URL (can be Incoming Webhook or Power Automate flow)
        message: Message payload (can be plain text or Adaptive Card format)
        
    Returns:
        True if successful, False otherwise
    """
    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            # Check if this is a Power Automate flow URL
            if _is_power_automate_url(webhook_url):
                # Power Automate flows expect a simpler JSON payload
                # The flow will format it and send to Teams
                if isinstance(message, str):
                    payload = {
                        "text": message,
                        "title": "RedTeam Knowledge Base Notification"
                    }
                else:
                    # Extract text and title from message card if available
                    text = message.get("text", "Notification from RedTeam Knowledge Base")
                    title = message.get("summary", "RedTeam Knowledge Base")
                    if "sections" in message and len(message["sections"]) > 0:
                        section = message["sections"][0]
                        text = section.get("text", text)
                        title = section.get("activityTitle", title)
                    
                    payload = {
                        "text": text,
                        "title": title,
                        "data": message  # Include full message for flow to process
                    }
            else:
                # Standard Teams Incoming Webhook format
                if isinstance(message, str):
                    payload = {
                        "text": message,
                        "@type": "MessageCard",
                        "@context": "https://schema.org/extensions"
                    }
                else:
                    payload = message
            
            response = await client.post(webhook_url, json=payload)
            response.raise_for_status()
            logger.info(f"Successfully sent Teams notification to {webhook_url}")
            return True
    except httpx.HTTPError as e:
        logger.error(f"Failed to send Teams notification: {e}")
        if hasattr(e, 'response') and e.response is not None:
            logger.error(f"Response status: {e.response.status_code}, body: {e.response.text}")
        return False
    except Exception as e:
        logger.error(f"Unexpected error sending Teams notification: {e}")
        return False


async def send_slack_notification(webhook_url: str, message: dict) -> bool:
    """
    Send a notification to Slack via webhook.
    
    Args:
        webhook_url: Slack webhook URL
        message: Message payload (can be plain text or Slack Block Kit format)
        
    Returns:
        True if successful, False otherwise
    """
    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            # If message is a string, convert to Slack format
            if isinstance(message, str):
                payload = {"text": message}
            else:
                payload = message
            
            response = await client.post(webhook_url, json=payload)
            response.raise_for_status()
            logger.info(f"Successfully sent Slack notification to {webhook_url}")
            return True
    except httpx.HTTPError as e:
        logger.error(f"Failed to send Slack notification: {e}")
        return False
    except Exception as e:
        logger.error(f"Unexpected error sending Slack notification: {e}")
        return False


async def send_test_notification(webhook_url: str, service: str = "teams") -> tuple[bool, str]:
    """
    Send a test notification to verify webhook configuration.
    
    Args:
        webhook_url: Webhook URL
        service: "teams" or "slack"
        
    Returns:
        Tuple of (success: bool, message: str)
    """
    # Check if this is a Power Automate URL
    is_power_automate = _is_power_automate_url(webhook_url)
    
    if service.lower() == "slack":
        test_message = {
            "text": "🧪 Test notification from RedTeam Knowledge Base",
            "blocks": [
                {
                    "type": "section",
                    "text": {
                        "type": "mrkdwn",
                        "text": "*✅ Webhook Test Successful*\nYour webhook is configured correctly!"
                    }
                }
            ]
        }
        success = await send_slack_notification(webhook_url, test_message)
    else:
        if is_power_automate:
            # For Power Automate, send a simpler payload
            test_message = {
                "text": "🧪 Test notification from RedTeam Knowledge Base\n\n✅ Webhook Test Successful\nYour webhook is configured correctly!\n\nThis is a test message to verify that webhook notifications are working properly.",
                "title": "✅ Webhook Test Successful",
                "summary": "Test notification from RedTeam Knowledge Base"
            }
        else:
            # Standard Teams MessageCard format
            test_message = {
                "text": "🧪 Test notification from RedTeam Knowledge Base",
                "@type": "MessageCard",
                "@context": "https://schema.org/extensions",
                "summary": "Test notification",
                "themeColor": "0078D4",
                "sections": [
                    {
                        "activityTitle": "✅ Webhook Test Successful",
                        "activitySubtitle": "Your webhook is configured correctly!",
                        "text": "This is a test message to verify that webhook notifications are working properly.",
                        "facts": [
                            {
                                "name": "Status",
                                "value": "Connected"
                            },
                            {
                                "name": "Service",
                                "value": "RedTeam Knowledge Base"
                            }
                        ]
                    }
                ]
            }
        success = await send_teams_notification(webhook_url, test_message)
    
    if success:
        if is_power_automate:
            return True, "Test notification sent to Power Automate flow! Check your Teams channel - it may take a few seconds to appear."
        else:
            return True, "Test notification sent successfully! Check your Teams/Slack channel."
    else:
        return False, "Failed to send test notification. Please check the webhook URL and try again."

