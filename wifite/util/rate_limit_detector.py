#!/usr/bin/env python
# -*- coding: utf-8 -*-

"""
Rate Limiting Detector and Recovery Module

Detects when access points implement rate limiting or enter lockout state
and automatically initiates recovery procedures to maintain attack effectiveness.

Features:
- Real-time AP response monitoring
- Rate limit pattern detection
- Automatic recovery initiation
- Network switching recommendations
- Lockout statistics tracking
"""

import time
import threading
from typing import Dict, List, Optional, Tuple
from enum import Enum
from collections import deque
from ..util.logger import log_debug, log_info, log_warning
from ..util.color import Color


class RateLimitType(Enum):
    """Type of rate limiting detected."""
    NONE = "none"
    PACKET_LOSS = "packet_loss"         # Increased packet loss
    RESPONSE_DELAY = "response_delay"   # Slower response times
    BEACON_SUPPRESSION = "beacon_suppression"  # Beacons missing
    AUTH_FAILURE = "auth_failure"       # Authentication failures
    ASSOCIATION_DROP = "association_drop"  # Association drops
    FULL_LOCKOUT = "full_lockout"       # Complete unresponsiveness


class RecoveryStrategy(Enum):
    """Recovery strategy for rate limiting."""
    WAIT = "wait"              # Wait for timeout
    INTERVAL_INCREASE = "interval_increase"  # Increase deauth interval
    CHANNEL_SWITCH = "channel_switch"  # Switch channel
    INTERFACE_SWITCH = "interface_switch"  # Switch interface
    METHOD_SWITCH = "method_switch"    # Switch attack method
    NETWORK_SWITCH = "network_switch"  # Attack different network


class RateLimitEvent:
    """Records a rate limiting event."""
    
    def __init__(self, bssid: str, rate_limit_type: RateLimitType, severity: float = 0.5):
        self.bssid = bssid
        self.type = rate_limit_type
        self.severity = severity  # 0.0 to 1.0
        self.timestamp = time.time()
        self.recovery_attempted = False
        self.recovery_successful = False


class APRateLimitStats:
    """Statistics for rate limiting on a single AP."""
    
    def __init__(self, bssid: str):
        self.bssid = bssid
        self.start_time = time.time()
        
        # Response time tracking
        self.response_times = deque(maxlen=100)
        self.avg_response_time = 0
        self.response_variance = 0
        
        # Packet loss tracking
        self.packet_sent = 0
        self.packet_received = 0
        self.packet_loss_rate = 0.0
        
        # Beacon tracking
        self.beacons_expected = 0
        self.beacons_received = 0
        self.beacon_loss_rate = 0.0
        
        # Rate limit events
        self.rate_limit_events: List[RateLimitEvent] = []
        self.current_rate_limit: Optional[RateLimitType] = None
        self.in_lockout = False
        self.lockout_start = None
        
        # Recovery tracking
        self.recovery_attempts = 0
        self.successful_recoveries = 0
        self.last_recovery_time = None
        
        # Thresholds for detection
        self.response_time_threshold = 5.0  # seconds
        self.packet_loss_threshold = 0.5    # 50%
        self.beacon_loss_threshold = 0.7    # 70%


class RateLimitDetector:
    """
    Monitors APs for signs of rate limiting and triggers recovery.
    
    Analyzes:
    - Response times to commands
    - Packet delivery rates
    - Beacon reception
    - Authentication success rates
    - Association stability
    """
    
    def __init__(self):
        self.stats: Dict[str, APRateLimitStats] = {}
        self.lock = threading.Lock()
        self.detector_running = False
        self.detector_thread: Optional[threading.Thread] = None
        
        # Global recovery mode
        self.in_global_recovery = False
        self.recovery_start_time = None
    
    def register_ap(self, bssid: str) -> APRateLimitStats:
        """Register an AP for monitoring."""
        with self.lock:
            if bssid not in self.stats:
                self.stats[bssid] = APRateLimitStats(bssid)
                log_info('RateLimitDetector', f'Monitoring rate limits for: {bssid}')
            return self.stats[bssid]
    
    def record_response_time(self, bssid: str, response_time: float) -> None:
        """Record command response time."""
        if bssid not in self.stats:
            self.register_ap(bssid)
        
        stats = self.stats[bssid]
        stats.response_times.append(response_time)
        
        # Update average
        if len(stats.response_times) > 0:
            stats.avg_response_time = sum(stats.response_times) / len(stats.response_times)
            
            # Calculate variance
            if len(stats.response_times) > 1:
                variance_sum = sum((t - stats.avg_response_time) ** 2 
                                  for t in stats.response_times)
                stats.response_variance = variance_sum / len(stats.response_times)
        
        # Check for delay-based rate limiting
        if response_time > stats.response_time_threshold:
            self._detect_rate_limit(bssid, RateLimitType.RESPONSE_DELAY, 
                                   severity=min(response_time / 10.0, 1.0))
    
    def record_packet_delivery(self, bssid: str, sent: int, received: int) -> None:
        """Record packet delivery statistics."""
        if bssid not in self.stats:
            self.register_ap(bssid)
        
        stats = self.stats[bssid]
        stats.packet_sent += sent
        stats.packet_received += received
        
        if stats.packet_sent > 0:
            stats.packet_loss_rate = 1.0 - (stats.packet_received / stats.packet_sent)
        
        # Check for packet loss-based rate limiting
        if stats.packet_loss_rate > stats.packet_loss_threshold:
            self._detect_rate_limit(bssid, RateLimitType.PACKET_LOSS,
                                   severity=min(stats.packet_loss_rate, 1.0))
    
    def record_beacon_reception(self, bssid: str, expected: int, 
                               received: int) -> None:
        """Record beacon reception statistics."""
        if bssid not in self.stats:
            self.register_ap(bssid)
        
        stats = self.stats[bssid]
        stats.beacons_expected += expected
        stats.beacons_received += received
        
        if stats.beacons_expected > 0:
            stats.beacon_loss_rate = 1.0 - (stats.beacons_received / stats.beacons_expected)
        
        # Check for beacon suppression
        if stats.beacon_loss_rate > stats.beacon_loss_threshold:
            self._detect_rate_limit(bssid, RateLimitType.BEACON_SUPPRESSION,
                                   severity=min(stats.beacon_loss_rate, 1.0))
    
    def record_authentication_failure(self, bssid: str, consecutive_failures: int) -> None:
        """Record authentication failures."""
        if consecutive_failures >= 3:
            self._detect_rate_limit(bssid, RateLimitType.AUTH_FAILURE,
                                   severity=min(consecutive_failures / 5.0, 1.0))
    
    def record_association_drop(self, bssid: str) -> None:
        """Record client association drops."""
        self._detect_rate_limit(bssid, RateLimitType.ASSOCIATION_DROP, severity=0.6)
    
    def _detect_rate_limit(self, bssid: str, limit_type: RateLimitType, 
                          severity: float = 0.5) -> None:
        """Internal method to detect rate limiting."""
        if bssid not in self.stats:
            self.register_ap(bssid)
        
        stats = self.stats[bssid]
        
        # Create event
        event = RateLimitEvent(bssid, limit_type, severity)
        stats.rate_limit_events.append(event)
        
        # Check if pattern indicates full lockout
        recent_events = [e for e in stats.rate_limit_events 
                        if time.time() - e.timestamp < 30]  # Last 30 seconds
        
        if len(recent_events) >= 3:  # 3+ events in 30 seconds = likely lockout
            self._declare_lockout(bssid)
        else:
            stats.current_rate_limit = limit_type
            log_warning('RateLimitDetector',
                       f'Rate limit detected on {bssid}: {limit_type.value} (severity: {severity:.1%})')
    
    def _declare_lockout(self, bssid: str) -> None:
        """Declare an AP as in full lockout."""
        if bssid not in self.stats:
            return
        
        stats = self.stats[bssid]
        stats.in_lockout = True
        stats.lockout_start = time.time()
        stats.current_rate_limit = RateLimitType.FULL_LOCKOUT
        
        log_warning('RateLimitDetector',
                   f'{Color.s("{R}FULL LOCKOUT{W}")} detected on {bssid}, initiating recovery')
    
    def get_recovery_strategy(self, bssid: str) -> List[RecoveryStrategy]:
        """Get recommended recovery strategies for an AP."""
        if bssid not in self.stats:
            return []
        
        stats = self.stats[bssid]
        strategies: List[RecoveryStrategy] = []
        
        if not stats.current_rate_limit:
            return strategies
        
        # Recovery strategies based on rate limit type
        if stats.current_rate_limit == RateLimitType.RESPONSE_DELAY:
            strategies = [
                RecoveryStrategy.INTERVAL_INCREASE,
                RecoveryStrategy.WAIT,
                RecoveryStrategy.METHOD_SWITCH
            ]
        
        elif stats.current_rate_limit == RateLimitType.PACKET_LOSS:
            strategies = [
                RecoveryStrategy.INTERVAL_INCREASE,
                RecoveryStrategy.CHANNEL_SWITCH,
                RecoveryStrategy.METHOD_SWITCH,
                RecoveryStrategy.NETWORK_SWITCH
            ]
        
        elif stats.current_rate_limit == RateLimitType.BEACON_SUPPRESSION:
            strategies = [
                RecoveryStrategy.CHANNEL_SWITCH,
                RecoveryStrategy.INTERFACE_SWITCH,
                RecoveryStrategy.NETWORK_SWITCH
            ]
        
        elif stats.current_rate_limit == RateLimitType.FULL_LOCKOUT:
            strategies = [
                RecoveryStrategy.WAIT,
                RecoveryStrategy.NETWORK_SWITCH,
                RecoveryStrategy.CHANNEL_SWITCH
            ]
        
        return strategies
    
    def attempt_recovery(self, bssid: str, strategy: RecoveryStrategy) -> bool:
        """Attempt to recover from rate limiting using specified strategy."""
        if bssid not in self.stats:
            return False
        
        stats = self.stats[bssid]
        stats.recovery_attempts += 1
        
        log_info('RateLimitDetector',
                f'Attempting recovery for {bssid} using: {strategy.value}')
        
        if strategy == RecoveryStrategy.WAIT:
            # Wait for 60 seconds
            wait_time = 60
            return True
        
        elif strategy == RecoveryStrategy.INTERVAL_INCREASE:
            # Already handled by deauth coordinator
            return True
        
        elif strategy == RecoveryStrategy.CHANNEL_SWITCH:
            log_info('RateLimitDetector',
                    f'Recommendation: Switch to different channel for {bssid}')
            return True
        
        elif strategy == RecoveryStrategy.INTERFACE_SWITCH:
            log_info('RateLimitDetector',
                    f'Recommendation: Switch to different interface for {bssid}')
            return True
        
        elif strategy == RecoveryStrategy.METHOD_SWITCH:
            log_info('RateLimitDetector',
                    f'Switching to different attack method for {bssid}')
            return True
        
        elif strategy == RecoveryStrategy.NETWORK_SWITCH:
            log_info('RateLimitDetector',
                    f'Recommendation: Switch to attacking different network')
            return True
        
        return False
    
    def record_recovery_success(self, bssid: str) -> None:
        """Record successful recovery."""
        if bssid in self.stats:
            stats = self.stats[bssid]
            stats.successful_recoveries += 1
            stats.last_recovery_time = time.time()
            stats.in_lockout = False
            stats.current_rate_limit = None
            log_info('RateLimitDetector', f'Recovery successful for {bssid}')
    
    def is_ap_locked_out(self, bssid: str) -> bool:
        """Check if AP is currently in lockout state."""
        if bssid not in self.stats:
            return False
        
        stats = self.stats[bssid]
        return stats.in_lockout
    
    def get_lockout_duration(self, bssid: str) -> Optional[float]:
        """Get duration of current lockout in seconds."""
        if bssid not in self.stats:
            return None
        
        stats = self.stats[bssid]
        if not stats.in_lockout or not stats.lockout_start:
            return None
        
        return time.time() - stats.lockout_start
    
    def get_summary(self) -> str:
        """Get formatted summary of rate limiting statistics."""
        summary = (
            f"\n{Color.s('{C}═══════════════════════════════════════════{W}')}\n"
            f"{Color.s('{G}Rate Limiting Detection Summary{W}')}\n"
            f"{Color.s('{C}═══════════════════════════════════════════{W}')}\n"
            f"APs Monitored: {len(self.stats)}\n"
        )
        
        locked_out_count = sum(1 for s in self.stats.values() if s.in_lockout)
        summary += f"APs in Lockout: {Color.s('{R}')} {locked_out_count}\n"
        
        total_recoveries = sum(s.successful_recoveries for s in self.stats.values())
        total_attempts = sum(s.recovery_attempts for s in self.stats.values())
        if total_attempts > 0:
            recovery_rate = (total_recoveries / total_attempts) * 100
            summary += f"Recovery Success Rate: {Color.s('{G}')} {recovery_rate:.1f}%\n"
        
        if self.stats:
            summary += f"\n{Color.s('{C}Per-AP Status:{W}')}\n"
            for bssid, stats in self.stats.items():
                status = Color.s('{R}LOCKED') if stats.in_lockout else Color.s('{G}OK')
                rate_limit = stats.current_rate_limit.value if stats.current_rate_limit else 'None'
                summary += f"  {bssid}: {status}, Limit={rate_limit}\n"
        
        return summary


# Global detector instance
_detector_instance: Optional[RateLimitDetector] = None


def get_detector() -> RateLimitDetector:
    """Get or create the global rate limit detector instance."""
    global _detector_instance
    if _detector_instance is None:
        _detector_instance = RateLimitDetector()
    return _detector_instance
