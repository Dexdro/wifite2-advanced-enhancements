#!/usr/bin/env python
# -*- coding: utf-8 -*-

"""
Integration Examples for Advanced Attack Enhancements

This module shows how to integrate the new optimization modules into
existing wifite2 attack classes with minimal changes.

Usage:
    from wifite.util.attack_enhancements import SmartPMKIDAttack, SmartDeauthAttack
    
    attack = SmartPMKIDAttack(target)
    attack.run()
"""

import time
from typing import Optional
from .pmkid_optimizer import get_optimizer
from .deauth_coordinator import get_coordinator
from .attack_orchestrator import get_orchestrator, AttackMethod
from .rate_limit_detector import get_detector
from ..util.logger import log_info, log_warning
from ..util.color import Color


class AttackEnhancementsMixin:
    """
    Mixin class to add enhancement capabilities to any attack class.
    
    Usage:
        class SmartAttack(AttackEnhancementsMixin, OriginalAttack):
            pass
    """
    
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.optimizer = None
        self.coordinator = None
        self.orchestrator = None
        self.detector = None
        self.enhancement_enabled = True
    
    def enable_enhancements(self):
        """Enable optimization enhancements."""
        self.optimizer = get_optimizer()
        self.coordinator = get_coordinator()
        self.orchestrator = get_orchestrator()
        self.detector = get_detector()
        self.enhancement_enabled = True
        log_info('AttackEnhancements', f'Enhancements enabled for {self.target.bssid}')
    
    def disable_enhancements(self):
        """Disable optimization enhancements (revert to original behavior)."""
        self.enhancement_enabled = False
        log_info('AttackEnhancements', f'Enhancements disabled for {self.target.bssid}')
    
    def check_rate_limiting(self) -> bool:
        """
        Check if AP is rate limited and handle recovery.
        
        Returns:
            True if AP is healthy, False if in lockout
        """
        if not self.enhancement_enabled or not self.detector:
            return True
        
        if self.detector.is_ap_locked_out(self.target.bssid):
            duration = self.detector.get_lockout_duration(self.target.bssid)
            Color.pl('{!} {R}AP Rate Limited{W}: Locked out for {O}%.0fs{W}' % duration)
            
            # Try recovery strategies
            strategies = self.detector.get_recovery_strategy(self.target.bssid)
            for strategy in strategies:
                self.detector.attempt_recovery(self.target.bssid, strategy)
            
            return False
        
        return True
    
    def log_enhancement_summary(self):
        """Log summary of enhancement statistics."""
        if not self.enhancement_enabled:
            return
        
        if self.optimizer:
            log_info('AttackEnhancements', self.optimizer.get_summary())
        if self.coordinator:
            log_info('AttackEnhancements', self.coordinator.get_summary())
        if self.detector:
            log_info('AttackEnhancements', self.detector.get_summary())


class SmartPMKIDExtraction:
    """
    Helper class for smart PMKID extraction with optimizer integration.
    
    Usage:
        extractor = SmartPMKIDExtraction(target)
        success, result = extractor.extract_with_optimization()
    """
    
    def __init__(self, target):
        self.target = target
        self.optimizer = get_optimizer()
        self.detector = get_detector()
        self.optimizer.register_target(target.bssid, target.essid if target.essid_known else "Unknown")
        self.detector.register_ap(target.bssid)
    
    def get_extraction_interval(self) -> float:
        """Get adaptive extraction interval."""
        return self.optimizer.get_optimal_extraction_interval(self.target.bssid)
    
    def should_continue(self) -> bool:
        """Check if extraction should continue."""
        return self.optimizer.should_continue_targeting(self.target.bssid)
    
    def record_extraction(self, success: bool, extraction_time: float = 0):
        """Record extraction attempt."""
        self.optimizer.record_extraction_attempt(
            self.target.bssid, 
            success=success, 
            extraction_time=extraction_time
        )
    
    def handle_rate_limiting(self) -> bool:
        """Handle rate limiting if detected."""
        if self.detector.is_ap_locked_out(self.target.bssid):
            log_warning('SmartPMKIDExtraction', 
                       f'Rate limiting detected on {self.target.bssid}')
            strategies = self.detector.get_recovery_strategy(self.target.bssid)
            for strategy in strategies:
                self.detector.attempt_recovery(self.target.bssid, strategy)
            return False
        return True


class SmartDeauthManager:
    """
    Helper class for smart deauthentication with coordinator integration.
    
    Usage:
        deauth = SmartDeauthManager(target)
        while deauth.should_continue():
            if deauth.can_deauth_now():
                strategy = deauth.get_strategy()
                # Perform deauth with strategy parameters
                deauth.record_result(success=True)
            time.sleep(deauth.get_wait_interval())
    """
    
    def __init__(self, target):
        self.target = target
        self.coordinator = get_coordinator()
        self.coordinator.register_target(target.bssid)
    
    def can_deauth_now(self) -> bool:
        """Check if ready to deauth."""
        return self.coordinator.can_deauth_now(self.target.bssid)
    
    def get_strategy(self) -> dict:
        """Get recommended deauth strategy."""
        return self.coordinator.get_deauth_strategy(self.target.bssid)
    
    def get_wait_interval(self) -> float:
        """Get wait interval before next deauth."""
        return self.coordinator.get_recommended_interval(self.target.bssid)
    
    def should_continue(self, max_attempts: int = 0) -> bool:
        """Check if should continue deauthing."""
        return self.coordinator.should_continue_deauth(self.target.bssid, max_attempts)
    
    def record_result(self, success: bool, response_time: float = 0):
        """Record deauth result."""
        self.coordinator.record_deauth_attempt(
            self.target.bssid,
            success=success,
            response_time=response_time
        )


class SmartMethodOrchestration:
    """
    Helper class for orchestrating multiple attack methods.
    
    Usage:
        orchestration = SmartMethodOrchestration([target1, target2])
        for target, method in orchestration.get_next_method():
            if orchestration.can_execute(target, method):
                # Execute attack
                orchestration.record_result(target, method, success=True)
    """
    
    def __init__(self, targets, max_concurrent: int = 3):
        self.targets = targets
        self.orchestrator = get_orchestrator(max_concurrent)
        
        for target in targets:
            self.orchestrator.register_target(target.bssid, target.essid if target.essid_known else "Unknown")
    
    def add_method_for_target(self, target, method: AttackMethod):
        """Add attack method for target."""
        self.orchestrator.add_attack_method(target.bssid, method)
    
    def can_execute(self, target, method: AttackMethod) -> bool:
        """Check if method can run now."""
        return self.orchestrator.can_start_method(target.bssid, method)
    
    def should_switch_method(self, target, method: AttackMethod, 
                            timeout: int = 120) -> bool:
        """Check if should switch to different method."""
        return self.orchestrator.should_switch_methods(target.bssid, method, timeout)
    
    def record_activity(self, target, method: AttackMethod):
        """Record activity for method."""
        self.orchestrator.record_method_activity(target.bssid, method)
    
    def record_result(self, target, method: AttackMethod, success: bool, 
                     result: Optional[dict] = None):
        """Record method result."""
        orchestrator_target = self.orchestrator.targets[target.bssid]
        orchestrator_target.set_method_result(method, success, result)
    
    def get_method_sequence(self, target) -> list:
        """Get recommended method sequence."""
        return self.orchestrator.get_recommended_method_sequence(target.bssid)
    
    def get_campaign_summary(self) -> str:
        """Get campaign summary."""
        return self.orchestrator.get_campaign_summary()


# Convenience functions

def create_smart_pmkid_attack(pmkid_attack_class):
    """
    Factory function to create a smart PMKID attack class.
    
    Usage:
        SmartPMKID = create_smart_pmkid_attack(AttackPMKID)
        attack = SmartPMKID(target)
        attack.enable_enhancements()
        attack.run()
    """
    class SmartPMKID(AttackEnhancementsMixin, pmkid_attack_class):
        def run(self):
            self.enable_enhancements()
            
            extractor = SmartPMKIDExtraction(self.target)
            
            Color.pl('{+} {C}Starting Smart PMKID Attack{W}')
            
            while extractor.should_continue():
                # Check for rate limiting
                if not extractor.handle_rate_limiting():
                    Color.pl('{!} {O}AP rate limited, waiting for recovery...{W}')
                    time.sleep(30)
                    continue
                
                # Extract PMKID with optimized interval
                start = time.time()
                success = self.run_pmkid_extraction()  # Original method
                extraction_time = time.time() - start
                
                extractor.record_extraction(success, extraction_time)
                
                if success:
                    Color.pl('{+} {G}PMKID extracted successfully!{W}')
                    break
                
                # Wait with adaptive interval
                interval = extractor.get_extraction_interval()
                Color.pl('{*} {C}Waiting %.1f seconds before next attempt...{W}' % interval)
                time.sleep(interval)
            
            self.log_enhancement_summary()
    
    return SmartPMKID


def create_smart_wpa_attack(wpa_attack_class):
    """
    Factory function to create a smart WPA handshake attack class.
    
    Usage:
        SmartWPA = create_smart_wpa_attack(AttackWPA)
        attack = SmartWPA(target)
        attack.enable_enhancements()
        attack.run()
    """
    class SmartWPA(AttackEnhancementsMixin, wpa_attack_class):
        def run(self):
            self.enable_enhancements()
            
            deauth_manager = SmartDeauthManager(self.target)
            
            Color.pl('{+} {C}Starting Smart WPA Handshake Attack{W}')
            
            while deauth_manager.should_continue(max_attempts=100):
                # Check rate limiting
                if not self.check_rate_limiting():
                    Color.pl('{!} {O}Waiting for AP recovery...{W}')
                    time.sleep(30)
                    continue
                
                # Get deauth strategy
                strategy = deauth_manager.get_strategy()
                Color.pl('{*} {D}Deauth strategy: {C}%d targets, interval=%.1fs{W}' 
                        % (strategy['target_clients'], strategy['interval']))
                
                # Wait for optimal timing
                if not deauth_manager.can_deauth_now():
                    time.sleep(0.1)
                    continue
                
                # Execute deauth with optimized parameters
                success = self.perform_deauth(
                    client_count=strategy['target_clients'],
                    use_broadcast=strategy['use_broadcast']
                )  # Original method
                
                deauth_manager.record_result(success, response_time=0.1)
                
                # Check for handshake
                if self.check_handshake_capture():
                    Color.pl('{+} {G}Handshake captured!{W}')
                    break
                
                # Wait before next attempt
                time.sleep(deauth_manager.get_wait_interval())
            
            self.log_enhancement_summary()
    
    return SmartWPA


# Example integration code

if __name__ == '__main__':
    # This shows how to use the smart attack classes
    
    # For PMKID
    # SmartPMKID = create_smart_pmkid_attack(AttackPMKID)
    # smart_pmkid = SmartPMKID(target)
    # smart_pmkid.run()
    
    # For WPA
    # SmartWPA = create_smart_wpa_attack(AttackWPA)
    # smart_wpa = SmartWPA(target)
    # smart_wpa.run()
    
    # For multi-vector campaigns
    # orchestration = SmartMethodOrchestration(targets, max_concurrent=3)
    # orchestration.add_method_for_target(target1, AttackMethod.PMKID)
    # orchestration.add_method_for_target(target1, AttackMethod.WPA_HANDSHAKE)
    # orchestration.add_method_for_target(target2, AttackMethod.PMKID_PASSIVE)
    
    pass
