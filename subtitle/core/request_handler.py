# -*- coding: utf-8 -*-
"""
Facade for the refactored request_handler module.
This file is kept for backward compatibility.
"""
from network.request_handler import (
    AsyncRateLimitedSession,
    LoadBalancedSession,
    SmartLoadBalancer
)

__all__ = [
    "AsyncRateLimitedSession",
    "LoadBalancedSession",
    "SmartLoadBalancer"
]
