"""
Event notifier for sending webhook notifications when events occur.
"""
import logging
from typing import Optional

from app.core.storage.settings_store import SettingsStore
from app.integrations.notifications import send_teams_notification, send_slack_notification

logger = logging.getLogger(__name__)


async def notify_event(event_type: str, event_data: dict) -> None:
    """
    Send webhook notification for an event if webhooks are enabled.
    
    Args:
        event_type: Type of event (e.g., "operation.created", "session.created")
        event_data: Event data to include in notification
    """
    try:
        settings_store = SettingsStore()
        settings = await settings_store.load_settings()
        
        # Check if webhooks are enabled
        if not settings.webhook_config or not settings.webhook_config.enabled:
            return
        
        # Format message based on event type
        message = _format_event_message(event_type, event_data)
        
        # Send to Teams if configured
        if settings.webhook_config.teams_webhook_url:
            try:
                await send_teams_notification(settings.webhook_config.teams_webhook_url, message)
            except Exception as e:
                logger.error(f"Failed to send Teams notification for {event_type}: {e}")
        
        # Send to Slack if configured
        if settings.webhook_config.slack_webhook_url:
            try:
                await send_slack_notification(settings.webhook_config.slack_webhook_url, message)
            except Exception as e:
                logger.error(f"Failed to send Slack notification for {event_type}: {e}")
                
    except Exception as e:
        logger.error(f"Failed to send event notification for {event_type}: {e}", exc_info=True)


def _format_event_message(event_type: str, event_data: dict) -> dict:
    """
    Format event data into a notification message.
    
    Args:
        event_type: Type of event
        event_data: Event data
        
    Returns:
        Formatted message dict
    """
    # Extract common fields
    title = event_data.get("title") or event_data.get("name") or "RedTeam Knowledge Base"
    text = event_data.get("text") or event_data.get("description") or ""
    
    # Format based on event type
    if event_type == "operation.created":
        return {
            "text": f"🆕 New Operation Created: {event_data.get('name', 'Unknown')}",
            "title": "Operation Created",
            "summary": f"Operation '{event_data.get('name', 'Unknown')}' was created",
            "sections": [
                {
                    "activityTitle": f"🆕 Operation: {event_data.get('name', 'Unknown')}",
                    "text": event_data.get("description", "No description provided"),
                    "facts": [
                        {"name": "Operation ID", "value": event_data.get("id", "N/A")},
                        {"name": "Status", "value": event_data.get("status", "active")},
                    ]
                }
            ]
        }
    
    elif event_type == "operation.updated":
        return {
            "text": f"📝 Operation Updated: {event_data.get('name', 'Unknown')}",
            "title": "Operation Updated",
            "summary": f"Operation '{event_data.get('name', 'Unknown')}' was updated",
            "sections": [
                {
                    "activityTitle": f"📝 Operation Updated: {event_data.get('name', 'Unknown')}",
                    "text": f"Status: {event_data.get('status', 'N/A')}",
                    "facts": [
                        {"name": "Operation ID", "value": event_data.get("id", "N/A")},
                        {"name": "Status", "value": event_data.get("status", "active")},
                    ]
                }
            ]
        }
    
    elif event_type == "session.created":
        return {
            "text": f"📋 New Session Created: {event_data.get('title', 'Unknown')}",
            "title": "Session Created",
            "summary": f"Session '{event_data.get('title', 'Unknown')}' was created",
            "sections": [
                {
                    "activityTitle": f"📋 Session: {event_data.get('title', 'Unknown')}",
                    "text": event_data.get("description", "No description provided"),
                    "facts": [
                        {"name": "Session ID", "value": event_data.get("id", "N/A")},
                        {"name": "Operation", "value": event_data.get("operation_name", "N/A")},
                        {"name": "Operator", "value": event_data.get("operator_name", "N/A")},
                    ]
                }
            ]
        }
    
    elif event_type == "session.updated":
        return {
            "text": f"✏️ Session Updated: {event_data.get('title', 'Unknown')}",
            "title": "Session Updated",
            "summary": f"Session '{event_data.get('title', 'Unknown')}' was updated",
            "sections": [
                {
                    "activityTitle": f"✏️ Session Updated: {event_data.get('title', 'Unknown')}",
                    "text": event_data.get("description", ""),
                    "facts": [
                        {"name": "Session ID", "value": event_data.get("id", "N/A")},
                        {"name": "Operation", "value": event_data.get("operation_name", "N/A")},
                    ]
                }
            ]
        }
    
    elif event_type == "session.screenshot_uploaded":
        return {
            "text": f"📸 Screenshot Uploaded to Session: {event_data.get('session_title', 'Unknown')}",
            "title": "Screenshot Uploaded",
            "summary": f"Screenshot uploaded to session '{event_data.get('session_title', 'Unknown')}'",
            "sections": [
                {
                    "activityTitle": f"📸 Screenshot Uploaded",
                    "text": f"Session: {event_data.get('session_title', 'Unknown')}",
                    "facts": [
                        {"name": "Session ID", "value": event_data.get("session_id", "N/A")},
                        {"name": "Filename", "value": event_data.get("filename", "N/A")},
                    ]
                }
            ]
        }
    
    elif event_type == "insights.generated":
        return {
            "text": f"💡 Insights Generated for Operation: {event_data.get('operation_name', 'Unknown')}",
            "title": "Insights Generated",
            "summary": f"AI insights generated for operation '{event_data.get('operation_name', 'Unknown')}'",
            "sections": [
                {
                    "activityTitle": f"💡 Insights Generated",
                    "text": f"Operation: {event_data.get('operation_name', 'Unknown')}",
                    "facts": [
                        {"name": "Operation ID", "value": event_data.get("operation_id", "N/A")},
                        {"name": "Sessions Analyzed", "value": str(event_data.get("session_count", 0))},
                    ]
                }
            ]
        }
    
    else:
        # Generic event format
        return {
            "text": f"🔔 {event_type}: {title}",
            "title": event_type.replace(".", " ").title(),
            "summary": text or f"Event: {event_type}",
        }



