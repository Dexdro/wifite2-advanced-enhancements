# Wifite2 Advanced Enhancements - Implementation Guide

## Quick Start

The advanced attack enhancements have been successfully integrated into wifite2. This guide shows you how to activate and use them.

---

## Overview of New Components

### 🎯 Core Modules Added

1. **PMKID Optimizer** - Smart extraction with adaptive intervals
2. **Deauth Coordinator** - Intelligent deauth timing to avoid lockout
3. **Attack Orchestrator** - Multi-method parallel execution
4. **Rate Limit Detector** - AP lockout detection and recovery

### 📁 File Locations

```
wifite/
├── util/
│   ├── pmkid_optimizer.py           (NEW) - PMKID optimization
│   ├── deauth_coordinator.py         (NEW) - Deauth coordination
│   ├── attack_orchestrator.py        (NEW) - Multi-vector orchestration
│   ├── rate_limit_detector.py        (NEW) - Rate limiting detection
│   └── attack_enhancements.py        (NEW) - Integration helpers
└── docs/
    └── ADVANCED_ATTACK_ENHANCEMENTS.md (NEW) - Detailed documentation
```

---

## Integration Steps

### Step 1: Enable Enhancements in Existing Attack Classes

The simplest way to use enhancements is with the provided mixin class:

```python
# In wifite/attack/pmkid.py (or wpa.py)

from ..util.attack_enhancements import AttackEnhancementsMixin

class AttackPMKID(AttackEnhancementsMixin, Attack):
    def __init__(self, target):
        super().__init__(target)
        # ... existing code ...
        self.enable_enhancements()  # Enable on init
    
    def run(self):
        # Use optimizer for extraction timing
        optimizer = self.optimizer
        detector = self.detector
        
        # ... existing attack code ...
```

### Step 2: Use Helper Classes for Specific Features

For PMKID attacks:
```python
from wifite.util.attack_enhancements import SmartPMKIDExtraction

extractor = SmartPMKIDExtraction(target)

while extractor.should_continue():
    if extractor.handle_rate_limiting():
        success = extract_pmkid()
        extractor.record_extraction(success)
        time.sleep(extractor.get_extraction_interval())
```

For deauthentication:
```python
from wifite.util.attack_enhancements import SmartDeauthManager

deauth = SmartDeauthManager(target)

while deauth.should_continue():
    if deauth.can_deauth_now():
        strategy = deauth.get_strategy()
        perform_deauth(deauth_count=strategy['target_clients'])
        deauth.record_result(success=True)
    time.sleep(deauth.get_wait_interval())
```

### Step 3: Multi-Vector Orchestration

For running multiple attacks:
```python
from wifite.util.attack_enhancements import SmartMethodOrchestration
from wifite.util.attack_orchestrator import AttackMethod

orchestration = SmartMethodOrchestration(targets)

# Add methods for each target
for target in targets:
    orchestration.add_method_for_target(target, AttackMethod.PMKID)
    orchestration.add_method_for_target(target, AttackMethod.WPA_HANDSHAKE)
    orchestration.add_method_for_target(target, AttackMethod.EVILTWIN)

# Execute with automatic scheduling
for target in targets:
    for method in orchestration.get_method_sequence(target):
        if orchestration.can_execute(target, method):
            execute_attack(target, method)
            orchestration.record_result(target, method, success=True)
            orchestration.record_activity(target, method)
```

---

## Configuration

### Default Parameters

These can be customized in `wifite/config.py`:

```python
class Configuration:
    # PMKID settings
    pmkid_extraction_interval = 5.0      # Default interval between extractions
    pmkid_aggressive_mode = False        # Enable aggressive fast extraction
    pmkid_stealth_mode = False          # Enable stealth slow extraction
    
    # Deauthentication settings
    deauth_min_interval = 1.0            # Minimum wait between deauth attempts
    deauth_max_interval = 30.0           # Maximum backoff
    deauth_rate_limit_threshold = 5      # Failures before rate limit declared
    
    # Orchestration settings
    max_concurrent_attacks = 3           # Maximum parallel attack methods
    attack_timeout = 120                 # Seconds before method timeout
    
    # Rate limiting settings
    rate_limit_response_threshold = 5.0  # Response time threshold (seconds)
    rate_limit_packet_loss_threshold = 0.5  # Packet loss threshold (50%)
    rate_limit_beacon_threshold = 0.7    # Beacon loss threshold (70%)
```

### Enabling Aggressive Mode

For faster PMKID extraction on healthy APs:

```python
from wifite.util.pmkid_optimizer import PMKIDOptimizer

params = PMKIDOptimizer.enable_aggressive_mode()
# {
#     'extraction_interval': 2.0,
#     'deauth_interval': 1,
#     'max_clients_per_deauth': 5,
#     'client_deauth_count': 3,
#     'broadcast_deauth': True,
#     'timeout': 60
# }
```

### Enabling Stealth Mode

For evading AP defenses:

```python
from wifite.util.pmkid_optimizer import PMKIDOptimizer

params = PMKIDOptimizer.enable_stealth_mode()
# {
#     'extraction_interval': 10.0,
#     'deauth_interval': 5,
#     'max_clients_per_deauth': 2,
#     'client_deauth_count': 1,
#     'broadcast_deauth': False,
#     'timeout': 300
# }
```

---

## Usage Examples

### Example 1: Smart PMKID Attack

```python
#!/usr/bin/env python
from wifite.util.attack_enhancements import SmartPMKIDExtraction
from wifite.util.rate_limit_detector import get_detector

class OptimizedPMKIDAttack:
    def __init__(self, target):
        self.target = target
        self.extractor = SmartPMKIDExtraction(target)
        self.detector = get_detector()
        self.max_duration = 300  # 5 minutes
        self.start_time = time.time()
    
    def run(self):
        while self.extractor.should_continue():
            elapsed = time.time() - self.start_time
            if elapsed > self.max_duration:
                break
            
            # Check for rate limiting
            if not self.extractor.handle_rate_limiting():
                time.sleep(30)
                continue
            
            # Extract with optimal timing
            result = self.extract_pmkid()
            self.extractor.record_extraction(success=result['success'], 
                                            extraction_time=result['time'])
            
            if result['success']:
                print(f"[+] PMKID extracted in {result['time']:.1f}s")
                return True
            
            # Adaptive wait
            interval = self.extractor.get_extraction_interval()
            print(f"[*] Waiting {interval:.1f}s before next attempt...")
            time.sleep(interval)
        
        return False
```

### Example 2: Intelligent Deauth

```python
#!/usr/bin/env python
from wifite.util.attack_enhancements import SmartDeauthManager

class OptimizedDeauthAttack:
    def __init__(self, target):
        self.target = target
        self.deauth = SmartDeauthManager(target)
        self.max_attempts = 50
    
    def run(self):
        attempt = 0
        while self.deauth.should_continue(max_attempts=self.max_attempts):
            attempt += 1
            
            # Get optimized strategy
            strategy = self.deauth.get_strategy()
            
            if not self.deauth.can_deauth_now():
                time.sleep(0.1)
                continue
            
            # Deauth with recommended parameters
            print(f"[*] Attempt {attempt}: Deauthing {strategy['target_clients']} clients")
            success = self.perform_deauth(strategy)
            
            self.deauth.record_result(success, response_time=0.1)
            
            # Check for handshake
            if self.check_handshake():
                print(f"[+] Handshake captured in {attempt} attempts!")
                return True
            
            # Wait with adaptive interval
            wait_time = self.deauth.get_wait_interval()
            print(f"[*] Waiting {wait_time:.1f}s (AP state: {strategy['state']})")
            time.sleep(wait_time)
        
        return False
```

### Example 3: Multi-Vector Campaign

```python
#!/usr/bin/env python
from wifite.util.attack_enhancements import SmartMethodOrchestration
from wifite.util.attack_orchestrator import AttackMethod

class MultiVectorCampaign:
    def __init__(self, targets):
        self.targets = targets
        self.orchestration = SmartMethodOrchestration(targets, max_concurrent=3)
        
        # Register all methods for all targets
        for target in targets:
            self.orchestration.add_method_for_target(target, AttackMethod.PMKID_PASSIVE)
            self.orchestration.add_method_for_target(target, AttackMethod.PMKID)
            self.orchestration.add_method_for_target(target, AttackMethod.WPA_HANDSHAKE)
            self.orchestration.add_method_for_target(target, AttackMethod.WPS_PIXIE)
    
    def run(self):
        successful_targets = 0
        
        for target in self.targets:
            print(f"\n[+] Attacking {target.bssid} ({target.essid})")
            
            # Get recommended method sequence
            methods = self.orchestration.get_method_sequence(target)
            
            for method in methods:
                # Check if can run
                if not self.orchestration.can_execute(target, method):
                    print(f"[-] Cannot execute {method.value}, conflicts detected")
                    continue
                
                # Check if should switch (timeout/stalled)
                if self.orchestration.should_switch_method(target, method, timeout=60):
                    print(f"[*] Switching from {method.value} (timeout)")
                    continue
                
                print(f"[*] Trying {method.value}...")
                
                # Execute attack
                success, result = self.execute_method(target, method)
                self.orchestration.record_result(target, method, success, result)
                self.orchestration.record_activity(target, method)
                
                if success:
                    print(f"[+] {method.value} successful!")
                    successful_targets += 1
                    break
        
        # Print summary
        print(self.orchestration.get_campaign_summary())
        print(f"\n[+] {successful_targets}/{len(self.targets)} targets cracked")
```

---

## Monitoring & Debugging

### View Statistics

```python
from wifite.util.pmkid_optimizer import get_optimizer
from wifite.util.deauth_coordinator import get_coordinator
from wifite.util.attack_orchestrator import get_orchestrator
from wifite.util.rate_limit_detector import get_detector

# During or after attack
print(get_optimizer().get_summary())
print(get_coordinator().get_summary())
print(get_orchestrator().get_campaign_summary())
print(get_detector().get_summary())
```

### Enable Verbose Logging

```python
import logging
from wifite.util import logger

logger.set_verbosity(2)  # 0=quiet, 1=normal, 2=verbose, 3=debug

# Now all log messages will show
```

### Debug Specific AP

```python
from wifite.util.deauth_coordinator import get_coordinator

coordinator = get_coordinator()
strategy = coordinator.get_deauth_strategy('AA:BB:CC:DD:EE:FF')

print(f"AP State: {strategy['state']}")
print(f"Success Rate: {strategy['success_rate']:.1%}")
print(f"Consecutive Failures: {strategy['consecutive_failures']}")
print(f"Recommended Interval: {strategy['interval']:.1f}s")
print(f"Target Clients: {strategy['target_clients']}")
print(f"Locked Out: {strategy['is_locked_out']}")
```

---

## Troubleshooting

### PMKID extraction is slow

**Problem**: Extraction takes 10+ seconds

**Solutions**:
1. Check if AP is rate limiting:
   ```python
   if detector.is_ap_locked_out(bssid):
       print("AP is locked out!")
   ```
2. Enable aggressive mode if AP is healthy:
   ```python
   params = PMKIDOptimizer.enable_aggressive_mode()
   ```
3. Reduce extraction interval:
   ```python
   Configuration.pmkid_extraction_interval = 2.0
   ```

### AP keeps locking out

**Problem**: AP becomes unresponsive after 30 seconds

**Solutions**:
1. Use stealth mode:
   ```python
   params = PMKIDOptimizer.enable_stealth_mode()
   ```
2. Reduce deauth intensity:
   ```python
   Configuration.deauth_min_interval = 2.0
   ```
3. Switch to passive PMKID (zero packet injection):
   ```python
   orchestration.add_method_for_target(target, AttackMethod.PMKID_PASSIVE)
   ```

### Multiple methods interfering

**Problem**: Methods are causing conflicts

**Solutions**:
1. Check compatibility:
   ```python
   if orchestrator.can_run_concurrently(method1, method2):
       print("Compatible")
   ```
2. Reduce concurrent attacks:
   ```python
   orchestrator = get_orchestrator(max_concurrent=1)
   ```
3. Check incompatible pairs:
   ```python
   # PMKID + WPA_HANDSHAKE are incompatible
   # EVILTWIN + WPA_HANDSHAKE are incompatible
   # WPA3_SAE + WPA_HANDSHAKE are incompatible
   ```

### Recovery not working

**Problem**: AP doesn't recover from lockout

**Solutions**:
1. Try different recovery strategy:
   ```python
   strategies = detector.get_recovery_strategy(bssid)
   for strategy in strategies:
       detector.attempt_recovery(bssid, strategy)
   ```
2. Manually wait longer:
   ```python
   time.sleep(60)  # Wait 60 seconds
   ```
3. Switch to different network and come back later

---

## Performance Tips

### For Maximum Speed
- Use aggressive mode on healthy APs
- Enable parallel PMKID extraction (multiple APs)
- Use broadcast deauth on WPA2 networks
- Increase max concurrent attacks to 4-5

### For Maximum Stealth
- Use stealth mode
- Reduce deauth frequency (2-5 second intervals)
- Single client targeting
- Avoid broadcast deauth
- Use passive PMKID when possible

### For Balanced Performance
- Use default settings
- Adaptive intervals based on AP health
- Automatic method switching
- Mixed PMKID + WPA approach

---

## Advanced Configuration

### Custom PMKID Parameters

```python
from wifite.util.pmkid_optimizer import PMKIDOptimizer

# Custom aggressive settings
custom_params = {
    'extraction_interval': 1.5,        # Very fast
    'deauth_interval': 0.5,             # Very aggressive
    'max_clients_per_deauth': 10,       # Many targets
    'client_deauth_count': 5,           # Multiple packets
    'broadcast_deauth': True,           # Always broadcast
    'timeout': 30                       # Quick timeout
}
```

### Custom Rate Limit Thresholds

```python
from wifite.util.rate_limit_detector import get_detector

detector = get_detector()
stats = detector.register_ap('AA:BB:CC:DD:EE:FF')
stats.response_time_threshold = 10.0   # 10 second threshold
stats.packet_loss_threshold = 0.8      # 80% packet loss threshold
stats.beacon_loss_threshold = 0.9      # 90% beacon loss threshold
```

---

## Next Steps

1. **Test the enhancements** on various AP models
2. **Tune parameters** based on your hardware and targets
3. **Monitor statistics** to identify optimization opportunities
4. **Report issues** with specific AP models for further tuning

---

## Support & Issues

For issues, feature requests, or improvements:
- Check the main README.md for general support
- Review docs/ADVANCED_ATTACK_ENHANCEMENTS.md for detailed docs
- Test with verbose logging enabled for debugging
- Report findings with AP model, encryption type, and error logs

---

**Last Updated**: December 2025  
**Version**: 1.0  
**Compatibility**: Wifite2 2.9.9+, Python 3.9+
