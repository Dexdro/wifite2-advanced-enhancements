#!/usr/bin/env python
# -*- coding: utf-8 -*-

"""
PMKID Optimizer Module

Implements intelligent PMKID capture optimization strategies to maximize
success rates while minimizing AP lockout risk.

Features:
- Adaptive extraction intervals based on capture rate
- Multi-AP simultaneous monitoring
- Intelligent retry logic with exponential backoff
- Rate limiting detection and recovery
- Capture health monitoring
"""

import os
import time
import threading
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Tuple
from ..util.logger import log_debug, log_info, log_warning, log_error
from ..util.color import Color
from ..config import Configuration


class PMKIDCapture:
    """Represents a single PMKID capture session with health tracking."""
    
    def __init__(self, bssid: str, essid: str = ""):
        self.bssid = bssid
        self.essid = essid
        self.start_time = time.time()
        self.last_extraction = 0
        self.capture_count = 0
        self.extraction_attempts = 0
        self.failed_extractions = 0
        self.last_hash = None
        self.is_healthy = True
        self.consecutive_failures = 0


class PMKIDOptimizer:
    """
    Manages intelligent PMKID capture optimization and multi-AP monitoring.
    
    Optimizes extraction intervals, detects stalled captures, and manages
    multiple target networks simultaneously with adaptive strategies.
    """
    
    def __init__(self):
        self.captures: Dict[str, PMKIDCapture] = {}
        self.lock = threading.Lock()
        self.start_time = time.time()
        self.global_stats = {
            'total_extracted': 0,
            'total_attempts': 0,
            'total_failures': 0,
            'avg_extraction_time': 0,
            'active_targets': 0
        }
        self.extraction_history: List[Tuple[float, str, bool]] = []
        
    def register_target(self, bssid: str, essid: str = "") -> PMKIDCapture:
        """Register a new target for PMKID capture."""
        with self.lock:
            if bssid not in self.captures:
                capture = PMKIDCapture(bssid, essid)
                self.captures[bssid] = capture
                log_info('PMKIDOptimizer', f'Registered target: {bssid} ({essid})')
                return capture
            return self.captures[bssid]
    
    def get_optimal_extraction_interval(self, bssid: str) -> float:
        """
        Calculate optimal extraction interval based on capture health.
        
        Faster intervals for healthy captures, slower for struggling ones.
        Returns interval in seconds.
        """
        if bssid not in self.captures:
            return Configuration.pmkid_extraction_interval or 5.0
        
        capture = self.captures[bssid]
        
        # Base interval from config (default 5 seconds)
        base_interval = Configuration.pmkid_extraction_interval or 5.0
        
        # Healthy captures: Use aggressive 3-5 second intervals
        if capture.is_healthy and capture.consecutive_failures == 0:
            optimal = max(2.0, base_interval * 0.6)  # 60% of base interval
        
        # Struggling captures: Exponential backoff
        elif capture.consecutive_failures > 0:
            backoff_factor = min(2 ** capture.consecutive_failures, 8)  # Max 8x backoff
            optimal = base_interval * backoff_factor
        
        # Normal captures: Standard interval
        else:
            optimal = base_interval
        
        return optimal
    
    def record_extraction_attempt(self, bssid: str, success: bool, 
                                 extraction_time: float = 0):
        """Record an extraction attempt and update statistics."""
        with self.lock:
            if bssid not in self.captures:
                return
            
            capture = self.captures[bssid]
            capture.extraction_attempts += 1
            self.global_stats['total_attempts'] += 1
            
            if success:
                capture.capture_count += 1
                capture.consecutive_failures = 0  # Reset failure counter
                capture.last_extraction = time.time()
                self.global_stats['total_extracted'] += 1
                
                # Update running average extraction time
                if self.global_stats['avg_extraction_time'] == 0:
                    self.global_stats['avg_extraction_time'] = extraction_time
                else:
                    # Exponential moving average (70% old, 30% new)
                    self.global_stats['avg_extraction_time'] = \
                        (self.global_stats['avg_extraction_time'] * 0.7) + \
                        (extraction_time * 0.3)
                
                log_debug('PMKIDOptimizer', 
                         f'✓ Extracted PMKID for {bssid} (attempt #{capture.extraction_attempts})')
            else:
                capture.failed_extractions += 1
                capture.consecutive_failures += 1
                self.global_stats['total_failures'] += 1
                
                log_debug('PMKIDOptimizer', 
                         f'✗ Failed extraction for {bssid} (consecutive: {capture.consecutive_failures})')
            
            # Detect unhealthy captures (more failures than successes)
            failure_rate = capture.failed_extractions / max(1, capture.extraction_attempts)
            if failure_rate > 0.7 and capture.extraction_attempts > 3:
                capture.is_healthy = False
                log_warning('PMKIDOptimizer', 
                           f'Capture health degraded for {bssid} (failure rate: {failure_rate:.1%})')
            elif failure_rate < 0.3:
                capture.is_healthy = True
            
            # Record in history for analysis
            self.extraction_history.append((time.time(), bssid, success))
    
    def should_continue_targeting(self, bssid: str, max_duration: int = 0) -> bool:
        """
        Determine if we should continue targeting a specific AP.
        
        Considers:
        - Maximum duration limits
        - Consecutive failure thresholds
        - Capture success rate
        
        Args:
            bssid: Target BSSID
            max_duration: Maximum duration in seconds (0 = no limit)
        
        Returns:
            True if should continue, False if should abandon
        """
        if bssid not in self.captures:
            return True
        
        capture = self.captures[bssid]
        elapsed = time.time() - capture.start_time
        
        # Check duration limit
        if max_duration > 0 and elapsed > max_duration:
            log_warning('PMKIDOptimizer', 
                       f'Reached duration limit for {bssid} ({elapsed:.0f}s)')
            return False
        
        # Check if completely stuck (5+ consecutive failures)
        if capture.consecutive_failures >= 5:
            log_warning('PMKIDOptimizer', 
                       f'Too many consecutive failures for {bssid}, abandoning')
            return False
        
        # Allow more failures for short capture times
        if elapsed < 10:
            return True
        
        return True
    
    def get_adaptive_parameters(self, bssid: str) -> Dict:
        """
        Get optimized attack parameters for a target.
        
        Returns dictionary with:
        - extraction_interval: Optimal time between extractions
        - deauth_intensity: Recommended deauth packet count
        - should_continue: Whether to continue targeting
        """
        interval = self.get_optimal_extraction_interval(bssid)
        should_continue = self.should_continue_targeting(bssid)
        
        # Adjust deauth intensity based on health
        if bssid in self.captures:
            capture = self.captures[bssid]
            if capture.is_healthy:
                deauth_intensity = 10  # Aggressive deauth for healthy captures
            elif capture.consecutive_failures > 2:
                deauth_intensity = 3  # Conservative for struggling
            else:
                deauth_intensity = 5  # Balanced
        else:
            deauth_intensity = 5
        
        return {
            'extraction_interval': interval,
            'deauth_intensity': deauth_intensity,
            'should_continue': should_continue,
            'bssid': bssid
        }
    
    def get_summary(self) -> str:
        """Get formatted summary of PMKID capture stats."""
        elapsed = time.time() - self.start_time
        
        summary = (
            f"\n{Color.s('{C}═══════════════════════════════════════════{W}')}\n"
            f"{Color.s('{G}PMKID Capture Summary{W}')}\n"
            f"{Color.s('{C}═══════════════════════════════════════════{W}')}\n"
            f"Duration: {Color.s('{C}')} {elapsed:.0f}s\n"
            f"Targets Registered: {len(self.captures)}\n"
            f"Total Extractions: {Color.s('{G}')} {self.global_stats['total_extracted']}\n"
            f"Success Rate: {Color.s('{G}')} {(self.global_stats['total_extracted'] / max(1, self.global_stats['total_attempts']) * 100):.1f}%\n"
            f"Avg Extraction Time: {self.global_stats['avg_extraction_time']:.2f}s\n"
        )
        
        # Per-target stats
        if self.captures:
            summary += f"\n{Color.s('{C}Per-Target Stats:{W}')}\n"
            for bssid, capture in self.captures.items():
                status = Color.s('{G}✓ Healthy') if capture.is_healthy else Color.s('{R}✗ Unhealthy')
                summary += (f"  {bssid} ({capture.essid}): "
                           f"Extracted={capture.capture_count}, "
                           f"Failures={capture.failed_extractions}, "
                           f"Status={status}\n")
        
        return summary
    
    @staticmethod
    def enable_aggressive_mode() -> Dict:
        """
        Get recommended parameters for aggressive PMKID capture.
        
        Used when quick extraction is needed and AP lockout risk is acceptable.
        """
        return {
            'extraction_interval': 2.0,  # Every 2 seconds
            'deauth_interval': 1,         # Deauth every 1 second
            'max_clients_per_deauth': 5,  # Hit multiple clients
            'client_deauth_count': 3,     # 3 packets per client
            'broadcast_deauth': True,     # Also broadcast deauth
            'timeout': 60                 # 60 second timeout
        }
    
    @staticmethod
    def enable_stealth_mode() -> Dict:
        """
        Get recommended parameters for stealthy PMKID capture.
        
        Minimizes detection risk and AP rate limiting.
        """
        return {
            'extraction_interval': 10.0,  # Every 10 seconds
            'deauth_interval': 5,          # Deauth every 5 seconds
            'max_clients_per_deauth': 2,  # Single client at a time
            'client_deauth_count': 1,     # 1 packet per client
            'broadcast_deauth': False,    # No broadcast deauth
            'timeout': 300                # 5 minute timeout
        }


# Global optimizer instance
_optimizer_instance: Optional[PMKIDOptimizer] = None


def get_optimizer() -> PMKIDOptimizer:
    """Get or create the global PMKID optimizer instance."""
    global _optimizer_instance
    if _optimizer_instance is None:
        _optimizer_instance = PMKIDOptimizer()
    return _optimizer_instance
