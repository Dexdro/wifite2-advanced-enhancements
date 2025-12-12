#!/usr/bin/env python
# -*- coding: utf-8 -*-

"""
Intelligent Deauthentication Coordinator

Manages deauthentication timing and intensity to avoid triggering AP rate limiting
or lockout. Implements adaptive algorithms based on AP response patterns.

Features:
- Smart deauth interval calculation
- AP response monitoring
- Rate limit detection
- Automatic backoff when AP stops responding
- Client-specific targeting
"""

import time
import threading
from typing import Dict, List, Optional, Set
from datetime import datetime, timedelta
from enum import Enum
from ..util.logger import log_debug, log_info, log_warning
from ..util.color import Color


class APResponseState(Enum):
    """Represents the current state of AP response."""
    HEALTHY = "healthy"          # AP responding normally
    DEGRADED = "degraded"        # AP responding slowly
    RATE_LIMITED = "rate_limited"  # AP showing rate limiting signs
    UNRESPONSIVE = "unresponsive"  # AP not responding


class DeauthStats:
    """Statistics for a single AP's deauth responses."""
    
    def __init__(self, bssid: str):
        self.bssid = bssid
        self.deauth_attempts = 0
        self.successful_deauths = 0
        self.failed_deauths = 0
        self.last_deauth_time = 0
        self.response_times: List[float] = []
        self.consecutive_failures = 0
        self.state = APResponseState.HEALTHY
        self.lockout_detected = False
        self.lockout_recovery_time = None
        
        # Time windows for analysis
        self.window_start = time.time()
        self.deauths_in_window = 0


class DeauthCoordinator:
    """
    Coordinates deauthentication attacks across multiple targets
    to maximize success while minimizing AP lockout risk.
    """
    
    def __init__(self):
        self.stats: Dict[str, DeauthStats] = {}
        self.lock = threading.Lock()
        self.global_start = time.time()
        self.rate_limit_threshold = 5  # 5+ consecutive failures = rate limiting
        
        # Configuration
        self.min_deauth_interval = 1.0   # Minimum 1 second between deauth attempts
        self.max_deauth_interval = 30.0  # Maximum 30 seconds (backoff limit)
        self.deauth_window = 5.0         # 5 second analysis window
    
    def register_target(self, bssid: str) -> DeauthStats:
        """Register a new deauth target."""
        with self.lock:
            if bssid not in self.stats:
                self.stats[bssid] = DeauthStats(bssid)
                log_info('DeauthCoordinator', f'Registered deauth target: {bssid}')
            return self.stats[bssid]
    
    def record_deauth_attempt(self, bssid: str, success: bool, 
                             response_time: float = 0, is_broadcast: bool = False) -> None:
        """
        Record a deauthentication attempt result.
        
        Args:
            bssid: Target BSSID
            success: Whether deauth was successful (beacon detected after deauth)
            response_time: Time until client disconnected (seconds)
            is_broadcast: Whether it was a broadcast deauth
        """
        with self.lock:
            if bssid not in self.stats:
                self.register_target(bssid)
            
            stats = self.stats[bssid]
            stats.deauth_attempts += 1
            stats.deauths_in_window += 1
            
            if success:
                stats.successful_deauths += 1
                stats.consecutive_failures = 0
                stats.response_times.append(response_time)
                
                # Limit response time tracking to last 100 attempts
                if len(stats.response_times) > 100:
                    stats.response_times.pop(0)
                
                log_debug('DeauthCoordinator', 
                         f'✓ Deauth success for {bssid} (response: {response_time:.2f}s)')
            else:
                stats.failed_deauths += 1
                stats.consecutive_failures += 1
                
                log_debug('DeauthCoordinator', 
                         f'✗ Deauth failed for {bssid} (consecutive: {stats.consecutive_failures})')
            
            # Check for rate limiting or lockout
            self._update_ap_state(bssid)
            stats.last_deauth_time = time.time()
    
    def _update_ap_state(self, bssid: str) -> None:
        """Update AP response state based on recent statistics."""
        stats = self.stats[bssid]
        
        # Check time window
        elapsed = time.time() - stats.window_start
        if elapsed > self.deauth_window:
            stats.window_start = time.time()
            stats.deauths_in_window = 0
        
        # Determine state
        if stats.consecutive_failures >= self.rate_limit_threshold:
            stats.state = APResponseState.UNRESPONSIVE
            if not stats.lockout_detected:
                stats.lockout_detected = True
                stats.lockout_recovery_time = time.time() + 30  # Try again in 30s
                log_warning('DeauthCoordinator', 
                           f'AP lockout detected for {bssid}, activating recovery')
        
        elif stats.consecutive_failures >= 3:
            stats.state = APResponseState.RATE_LIMITED
        
        elif stats.consecutive_failures > 0:
            stats.state = APResponseState.DEGRADED
        
        else:
            stats.state = APResponseState.HEALTHY
            stats.lockout_detected = False
            stats.lockout_recovery_time = None
        
        # Check deauth rate limit (too many deauths in short window)
        if stats.deauths_in_window > 15:  # More than 15 in 5 second window
            stats.state = APResponseState.RATE_LIMITED
    
    def get_recommended_interval(self, bssid: str) -> float:
        """
        Get recommended interval before next deauth attempt.
        
        Implements exponential backoff when AP is rate-limited or unresponsive.
        """
        if bssid not in self.stats:
            return self.min_deauth_interval
        
        stats = self.stats[bssid]
        
        # If in lockout recovery, wait longer
        if stats.lockout_detected and stats.lockout_recovery_time:
            wait_time = stats.lockout_recovery_time - time.time()
            if wait_time > 0:
                return wait_time
        
        # Exponential backoff based on state
        if stats.state == APResponseState.HEALTHY:
            # Aggressive for healthy APs
            interval = max(1.0, self.min_deauth_interval * 0.5)
        
        elif stats.state == APResponseState.DEGRADED:
            # Increase interval for degraded APs
            backoff = min(2 ** stats.consecutive_failures, 8)
            interval = self.min_deauth_interval * backoff
        
        elif stats.state == APResponseState.RATE_LIMITED:
            # Strong backoff for rate-limited APs
            interval = self.min_deauth_interval * 5
        
        else:  # UNRESPONSIVE
            # Maximum backoff
            interval = self.max_deauth_interval
        
        return min(interval, self.max_deauth_interval)
    
    def can_deauth_now(self, bssid: str) -> bool:
        """Check if enough time has passed to attempt deauth."""
        if bssid not in self.stats:
            return True
        
        stats = self.stats[bssid]
        interval = self.get_recommended_interval(bssid)
        elapsed = time.time() - stats.last_deauth_time
        
        return elapsed >= interval
    
    def get_optimal_target_count(self, bssid: str) -> int:
        """
        Get recommended number of clients to deauth.
        
        Healthier APs can handle more deauth attempts at once.
        """
        if bssid not in self.stats:
            return 5
        
        stats = self.stats[bssid]
        
        if stats.state == APResponseState.HEALTHY:
            return 10  # Aggressive targeting
        elif stats.state == APResponseState.DEGRADED:
            return 5   # Moderate targeting
        elif stats.state == APResponseState.RATE_LIMITED:
            return 2   # Conservative targeting
        else:  # UNRESPONSIVE
            return 1   # Single target only
    
    def should_use_broadcast_deauth(self, bssid: str) -> bool:
        """Determine if broadcast deauth is safe for this AP."""
        if bssid not in self.stats:
            return True
        
        stats = self.stats[bssid]
        
        # Only use broadcast for healthy APs
        return stats.state == APResponseState.HEALTHY and not stats.lockout_detected
    
    def is_ap_locked_out(self, bssid: str) -> bool:
        """Check if AP is currently in lockout state."""
        if bssid not in self.stats:
            return False
        
        return self.stats[bssid].lockout_detected
    
    def should_continue_deauth(self, bssid: str, max_attempts: int = 0) -> bool:
        """
        Determine if deauth should continue for this target.
        
        Args:
            bssid: Target BSSID
            max_attempts: Maximum deauth attempts (0 = no limit)
        
        Returns:
            True if should continue, False if should stop
        """
        if bssid not in self.stats:
            return True
        
        stats = self.stats[bssid]
        
        # Check attempt limit
        if max_attempts > 0 and stats.deauth_attempts >= max_attempts:
            return False
        
        # Don't continue if completely unresponsive for too long
        if stats.state == APResponseState.UNRESPONSIVE:
            time_in_lockout = time.time() - (
                stats.lockout_recovery_time - 30 if stats.lockout_recovery_time else 0
            )
            if time_in_lockout > 60:  # 60+ seconds in lockout
                return False
        
        return True
    
    def get_deauth_strategy(self, bssid: str) -> Dict:
        """
        Get complete deauthentication strategy for a target.
        
        Returns dictionary with all recommended parameters.
        """
        if bssid not in self.stats:
            self.register_target(bssid)
        
        stats = self.stats[bssid]
        interval = self.get_recommended_interval(bssid)
        target_count = self.get_optimal_target_count(bssid)
        broadcast = self.should_use_broadcast_deauth(bssid)
        can_continue = self.should_continue_deauth(bssid)
        
        success_rate = (stats.successful_deauths / max(1, stats.deauth_attempts)) * 100
        
        return {
            'bssid': bssid,
            'interval': interval,
            'target_clients': target_count,
            'use_broadcast': broadcast,
            'should_continue': can_continue,
            'is_locked_out': stats.lockout_detected,
            'state': stats.state.value,
            'success_rate': success_rate,
            'total_attempts': stats.deauth_attempts,
            'consecutive_failures': stats.consecutive_failures
        }
    
    def get_summary(self) -> str:
        """Get formatted summary of deauth statistics."""
        elapsed = time.time() - self.global_start
        total_attempts = sum(s.deauth_attempts for s in self.stats.values())
        total_success = sum(s.successful_deauths for s in self.stats.values())
        
        summary = (
            f"\n{Color.s('{C}═══════════════════════════════════════════{W}')}\n"
            f"{Color.s('{G}Deauthentication Summary{W}')}\n"
            f"{Color.s('{C}═══════════════════════════════════════════{W}')}\n"
            f"Duration: {elapsed:.0f}s\n"
            f"Total Deauth Attempts: {total_attempts}\n"
            f"Successful Deauths: {Color.s('{G}')} {total_success}\n"
            f"Success Rate: {Color.s('{G}')} {(total_success / max(1, total_attempts) * 100):.1f}%\n"
        )
        
        if self.stats:
            summary += f"\n{Color.s('{C}Per-Target Stats:{W}')}\n"
            for bssid, stats in self.stats.items():
                state_color = {
                    APResponseState.HEALTHY: '{G}',
                    APResponseState.DEGRADED: '{Y}',
                    APResponseState.RATE_LIMITED: '{O}',
                    APResponseState.UNRESPONSIVE: '{R}'
                }.get(stats.state, '{W}')
                
                state_str = Color.s(f'{state_color}{stats.state.value}{Color.s("{W}")}')
                rate = (stats.successful_deauths / max(1, stats.deauth_attempts) * 100)
                summary += (f"  {bssid}: Attempts={stats.deauth_attempts}, "
                           f"Success={stats.successful_deauths}, "
                           f"Rate={rate:.0f}%, "
                           f"State={state_str}\n")
        
        return summary


# Global coordinator instance
_coordinator_instance: Optional[DeauthCoordinator] = None


def get_coordinator() -> DeauthCoordinator:
    """Get or create the global deauth coordinator instance."""
    global _coordinator_instance
    if _coordinator_instance is None:
        _coordinator_instance = DeauthCoordinator()
    return _coordinator_instance
