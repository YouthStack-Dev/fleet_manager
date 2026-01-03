"""
Push Notification Schemas for API validation
"""
from pydantic import BaseModel, Field, validator
from typing import Optional, Dict, Any
from datetime import datetime


class DeviceTokenRequest(BaseModel):
    """Request schema for device token registration"""
    fcm_token: str = Field(..., min_length=140, max_length=200, description="Firebase Cloud Messaging token")
    platform: str = Field(..., description="Platform: 'web' or 'app'")
    device_type: Optional[str] = Field(None, description="Device type: ios, android, chrome, firefox, safari")
    device_id: Optional[str] = Field(None, description="Unique device fingerprint")
    app_version: Optional[str] = Field(None, description="App version")
    device_model: Optional[str] = Field(None, description="Device model")
    
    @validator('platform')
    def validate_platform(cls, v):
        if v not in ['web', 'app']:
            raise ValueError("Platform must be 'web' or 'app'")
        return v
    
    @validator('fcm_token')
    def validate_token(cls, v):
        if not v or len(v) < 140:
            raise ValueError("Invalid FCM token format")
        return v
    
    class Config:
        json_schema_extra = {
            "example": {
                "fcm_token": "eXNV8h0O2RY:APA91bG...",
                "platform": "app",
                "device_type": "android",
                "device_id": "abc123device",
                "app_version": "1.0.0",
                "device_model": "Samsung Galaxy S23"
            }
        }


class DeviceTokenResponse(BaseModel):
    """Response schema for device token registration"""
    success: bool
    message: str
    session_id: Optional[int] = None
    
    class Config:
        json_schema_extra = {
            "example": {
                "success": True,
                "message": "Device token registered successfully",
                "session_id": 12345
            }
        }


class PushNotificationRequest(BaseModel):
    """Request schema for sending push notification (admin use)"""
    user_type: str = Field(..., description="User type: admin, employee, vendor, driver")
    user_id: int = Field(..., gt=0, description="User ID")
    title: str = Field(..., min_length=1, max_length=100, description="Notification title")
    body: str = Field(..., min_length=1, max_length=500, description="Notification body")
    data: Optional[Dict[str, str]] = Field(None, description="Additional data payload")
    priority: str = Field(default="high", description="Priority: 'high' or 'normal'")
    
    @validator('user_type')
    def validate_user_type(cls, v):
        if v not in ['admin', 'employee', 'vendor', 'driver']:
            raise ValueError("Invalid user_type")
        return v
    
    @validator('priority')
    def validate_priority(cls, v):
        if v not in ['high', 'normal']:
            raise ValueError("Priority must be 'high' or 'normal'")
        return v
    
    class Config:
        json_schema_extra = {
            "example": {
                "user_type": "employee",
                "user_id": 123,
                "title": "Shift Reminder",
                "body": "Your shift starts in 30 minutes",
                "data": {"shift_id": "456", "location": "Office A"},
                "priority": "high"
            }
        }


class BatchPushNotificationRequest(BaseModel):
    """Request schema for batch push notifications"""
    recipients: list[Dict[str, Any]] = Field(..., description="List of recipients with user_type and user_id")
    title: str = Field(..., min_length=1, max_length=100)
    body: str = Field(..., min_length=1, max_length=500)
    data: Optional[Dict[str, str]] = None
    priority: str = Field(default="high")
    
    @validator('recipients')
    def validate_recipients(cls, v):
        if not v:
            raise ValueError("Recipients list cannot be empty")
        for r in v:
            if 'user_type' not in r or 'user_id' not in r:
                raise ValueError("Each recipient must have user_type and user_id")
        return v
    
    class Config:
        json_schema_extra = {
            "example": {
                "recipients": [
                    {"user_type": "employee", "user_id": 123},
                    {"user_type": "driver", "user_id": 456}
                ],
                "title": "System Maintenance",
                "body": "Scheduled maintenance at 10 PM tonight",
                "priority": "high"
            }
        }


class SessionInfoResponse(BaseModel):
    """Response schema for session information"""
    user_type: str
    user_id: int
    total_sessions: int
    active_sessions: int
    inactive_sessions: int
    active_platforms: list[str]
    sessions: list[Dict[str, Any]]
    
    class Config:
        json_schema_extra = {
            "example": {
                "user_type": "employee",
                "user_id": 123,
                "total_sessions": 5,
                "active_sessions": 2,
                "inactive_sessions": 3,
                "active_platforms": ["web", "app"],
                "sessions": []
            }
        }


class NotificationResult(BaseModel):
    """Response schema for notification send result"""
    success: bool
    message: Optional[str] = None
    success_count: Optional[int] = None
    failure_count: Optional[int] = None
    no_session_count: Optional[int] = None
    error: Optional[str] = None
    
    class Config:
        json_schema_extra = {
            "example": {
                "success": True,
                "success_count": 98,
                "failure_count": 2,
                "no_session_count": 0,
                "message": "Notifications sent successfully"
            }
        }
