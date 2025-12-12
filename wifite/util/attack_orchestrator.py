#!/usr/bin/env python
# -*- coding: utf-8 -*-

"""
Multi-Vector Attack Orchestrator

Manages simultaneous attack coordination across multiple methods (PMKID, WPA,
Passive Monitor) to maximize success while minimizing AP resource exhaustion.

Features:
- Parallel attack execution with conflict prevention
- Intelligent method prioritization
- Resource sharing and coordination
- Attack health monitoring
- Automatic method switching on failure
"""

import time
import threading
from enum import Enum
from typing import Dict, List, Optional, Set, Tuple
from datetime import datetime
from ..util.logger import log_debug, log_info, log_warning
from ..util.color import Color


class AttackMethod(Enum):
    """Available attack methods."""
    PMKID = "pmkid"
    PMKID_PASSIVE = "pmkid_passive"
    WPA_HANDSHAKE = "wpa_handshake"
    EVILTWIN = "eviltwin"
    WPA3_SAE = "wpa3_sae"
    WPS_PIXIE = "wps_pixie"
    WPS_PIN = "wps_pin"


class AttackMethodState(Enum):
    """State of an attack method."""
    IDLE = "idle"
    RUNNING = "running"
    PAUSED = "paused"
    SUCCESS = "success"
    FAILED = "failed"
    SKIPPED = "skipped"


class MethodStats:
    """Statistics for a single attack method."""
    
    def __init__(self, method: AttackMethod):
        self.method = method
        self.state = AttackMethodState.IDLE
        self.start_time = 0
        self.end_time = 0
        self.success = False
        self.attempts = 0
        self.consecutive_failures = 0
        self.result = None
        self.last_activity = time.time()
    
    @property
    def duration(self) -> float:
        """Get duration in seconds."""
        end = self.end_time if self.end_time > 0 else time.time()
        return max(0, end - self.start_time) if self.start_time > 0 else 0
    
    @property
    def is_active(self) -> bool:
        """Check if method is actively running."""
        return self.state == AttackMethodState.RUNNING


class AttackVector:
    """Represents a single target with multiple attack methods."""
    
    def __init__(self, bssid: str, essid: str = ""):
        self.bssid = bssid
        self.essid = essid
        self.methods: Dict[AttackMethod, MethodStats] = {}
        self.primary_method: Optional[AttackMethod] = None
        self.completed_methods: Set[AttackMethod] = set()
        self.start_time = time.time()
        self.best_result = None
        self.lock = threading.Lock()
    
    def register_method(self, method: AttackMethod) -> MethodStats:
        """Register an attack method for this target."""
        if method not in self.methods:
            self.methods[method] = MethodStats(method)
        return self.methods[method]
    
    def set_method_running(self, method: AttackMethod) -> None:
        """Mark a method as currently running."""
        with self.lock:
            if method in self.methods:
                stats = self.methods[method]
                stats.state = AttackMethodState.RUNNING
                stats.start_time = time.time()
                stats.last_activity = time.time()
    
    def set_method_result(self, method: AttackMethod, success: bool, 
                         result: Optional[Dict] = None) -> None:
        """Record the result of an attack method."""
        with self.lock:
            if method not in self.methods:
                return
            
            stats = self.methods[method]
            stats.end_time = time.time()
            stats.success = success
            stats.result = result
            
            if success:
                stats.state = AttackMethodState.SUCCESS
                stats.consecutive_failures = 0
                self.completed_methods.add(method)
                
                # Update best result if better than previous
                if self.best_result is None or \
                   (result and result.get('priority', 0) > self.best_result.get('priority', 0)):
                    self.best_result = result
            else:
                stats.state = AttackMethodState.FAILED
                stats.consecutive_failures += 1
    
    def get_active_methods(self) -> List[AttackMethod]:
        """Get list of currently active methods."""
        return [m for m, s in self.methods.items() if s.is_active]
    
    def get_completed_methods(self) -> List[AttackMethod]:
        """Get list of completed methods."""
        return [m for m, s in self.methods.items() if s.state == AttackMethodState.SUCCESS]
    
    def has_successful_result(self) -> bool:
        """Check if any method was successful."""
        return any(s.success for s in self.methods.values())


class MultiVectorOrchestrator:
    """
    Orchestrates multiple attack methods against targets.
    
    Manages:
    - Parallel execution of compatible methods
    - Conflict prevention between methods
    - Resource allocation and load balancing
    - Intelligent method switching
    - Overall campaign statistics
    """
    
    def __init__(self, max_concurrent_attacks: int = 3):
        self.targets: Dict[str, AttackVector] = {}
        self.lock = threading.Lock()
        self.max_concurrent = max_concurrent_attacks
        self.campaign_start = time.time()
        
        # Configuration for method compatibility
        self.incompatible_pairs = {
            (AttackMethod.PMKID, AttackMethod.WPA_HANDSHAKE),  # Both use deauth
            (AttackMethod.EVILTWIN, AttackMethod.WPA_HANDSHAKE),  # Both interfere
            (AttackMethod.WPA3_SAE, AttackMethod.WPA_HANDSHAKE),  # Different protocols
        }
        
        # Method priorities (higher = more important)
        self.method_priority = {
            AttackMethod.PMKID_PASSIVE: 10,  # Lowest priority, harmless
            AttackMethod.PMKID: 20,           # Lower priority
            AttackMethod.WPA_HANDSHAKE: 25,   # Medium-low priority
            AttackMethod.EVILTWIN: 30,        # Medium priority
            AttackMethod.WPA3_SAE: 35,        # Higher priority for WPA3
            AttackMethod.WPS_PIXIE: 40,       # Higher priority for WPS
            AttackMethod.WPS_PIN: 40,         # Higher priority for WPS
        }
    
    def register_target(self, bssid: str, essid: str = "") -> AttackVector:
        """Register a new target."""
        with self.lock:
            if bssid not in self.targets:
                self.targets[bssid] = AttackVector(bssid, essid)
                log_info('MultiVectorOrchestrator', f'Registered target: {bssid}')
            return self.targets[bssid]
    
    def add_attack_method(self, bssid: str, method: AttackMethod) -> MethodStats:
        """Add an attack method for a target."""
        if bssid not in self.targets:
            self.register_target(bssid)
        
        vector = self.targets[bssid]
        stats = vector.register_method(method)
        log_debug('MultiVectorOrchestrator', 
                 f'Added method {method.value} for {bssid}')
        return stats
    
    def can_run_concurrently(self, method1: AttackMethod, 
                            method2: AttackMethod) -> bool:
        """Check if two methods can run simultaneously."""
        pair = tuple(sorted([method1, method2], key=lambda x: x.value))
        return pair not in self.incompatible_pairs
    
    def get_active_methods(self, bssid: str) -> List[AttackMethod]:
        """Get currently active methods for a target."""
        if bssid not in self.targets:
            return []
        
        return self.targets[bssid].get_active_methods()
    
    def can_start_method(self, bssid: str, method: AttackMethod) -> bool:
        """
        Check if it's safe to start a method.
        
        Ensures:
        - No conflicting methods are running
        - Resource limits not exceeded
        - Method hasn't failed too many times
        """
        if bssid not in self.targets:
            return True
        
        vector = self.targets[bssid]
        active = vector.get_active_methods()
        
        # Check for conflicts
        for active_method in active:
            if not self.can_run_concurrently(method, active_method):
                log_debug('MultiVectorOrchestrator',
                         f'Cannot start {method.value}: conflicts with {active_method.value}')
                return False
        
        # Check max concurrent limit
        total_active = sum(len(self.get_active_methods(b)) 
                          for b in self.targets.keys())
        if total_active >= self.max_concurrent:
            return False
        
        # Check failure count
        if method in vector.methods:
            stats = vector.methods[method]
            if stats.consecutive_failures > 3:  # 3+ failures = skip
                return False
        
        return True
    
    def should_switch_methods(self, bssid: str, method: AttackMethod, 
                             timeout: int = 120) -> bool:
        """
        Determine if we should switch to a different method.
        
        Args:
            bssid: Target BSSID
            method: Current method
            timeout: Seconds before method timeout
        
        Returns:
            True if should switch methods
        """
        if bssid not in self.targets:
            return False
        
        vector = self.targets[bssid]
        if method not in vector.methods:
            return False
        
        stats = vector.methods[method]
        
        # Switch if method timed out
        if stats.duration > timeout:
            return True
        
        # Switch if too many failures
        if stats.consecutive_failures > 3:
            return True
        
        # Switch if no progress in 30 seconds
        idle_time = time.time() - stats.last_activity
        if idle_time > 30 and stats.attempts > 0:
            return True
        
        return False
    
    def record_method_activity(self, bssid: str, method: AttackMethod) -> None:
        """Record activity for a method (prevents idle timeout)."""
        if bssid in self.targets and method in self.targets[bssid].methods:
            self.targets[bssid].methods[method].last_activity = time.time()
    
    def get_recommended_method_sequence(self, bssid: str) -> List[AttackMethod]:
        """
        Get recommended sequence of methods for a target.
        
        Prioritizes non-interfering methods and adjusts based on target type.
        """
        if bssid not in self.targets:
            return []
        
        vector = self.targets[bssid]
        available = [m for m in vector.methods.keys() 
                    if m not in vector.completed_methods]
        
        # Sort by priority (highest first)
        available.sort(key=lambda m: self.method_priority.get(m, 0), reverse=True)
        
        return available
    
    def get_campaign_summary(self) -> str:
        """Get formatted summary of campaign statistics."""
        elapsed = time.time() - self.campaign_start
        
        total_targets = len(self.targets)
        successful_targets = sum(1 for v in self.targets.values() 
                                if v.has_successful_result())
        total_methods = sum(len(v.methods) for v in self.targets.values())
        successful_methods = sum(1 for v in self.targets.values() 
                                for m in v.methods.values() 
                                if m.success)
        
        summary = (
            f"\n{Color.s('{C}═══════════════════════════════════════════{W}')}\n"
            f"{Color.s('{G}Multi-Vector Attack Campaign Summary{W}')}\n"
            f"{Color.s('{C}═══════════════════════════════════════════{W}')}\n"
            f"Duration: {elapsed:.0f}s\n"
            f"Targets: {Color.s('{G}')} {successful_targets}/{total_targets}\n"
            f"Methods Success: {Color.s('{G}')} {successful_methods}/{total_methods}\n"
            f"Success Rate: {Color.s('{G}')} {(successful_methods / max(1, total_methods) * 100):.1f}%\n"
        )
        
        if self.targets:
            summary += f"\n{Color.s('{C}Per-Target Breakdown:{W}')}\n"
            for bssid, vector in self.targets.items():
                completed = len(vector.get_completed_methods())
                total = len(vector.methods)
                status = Color.s('{G}✓') if vector.has_successful_result() else Color.s('{R}✗')
                summary += f"  {status} {bssid} ({vector.essid}): "
                summary += f"{completed}/{total} methods successful\n"
        
        return summary


# Global orchestrator instance
_orchestrator_instance: Optional[MultiVectorOrchestrator] = None


def get_orchestrator(max_concurrent: int = 3) -> MultiVectorOrchestrator:
    """Get or create the global multi-vector orchestrator instance."""
    global _orchestrator_instance
    if _orchestrator_instance is None:
        _orchestrator_instance = MultiVectorOrchestrator(max_concurrent)
    return _orchestrator_instance
