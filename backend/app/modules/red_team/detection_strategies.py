"""
MITRE ATT&CK Detection Strategies integration.
Provides models and services for mapping techniques to detection strategies.
"""
import json
import logging
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional, Set

from pydantic import BaseModel, ConfigDict, Field

from app.config import settings

logger = logging.getLogger(__name__)


# ============================================================================
# Detection Strategy Models
# ============================================================================

class DetectionStrategyAnalytic(BaseModel):
    """Platform-specific analytic within a detection strategy."""
    platform: str = Field(..., description="Platform (Windows, Linux, macOS, etc.)")
    analytic_id: Optional[str] = Field(None, description="Analytic identifier")
    description: Optional[str] = Field(None, description="Analytic description")
    data_components: List[str] = Field(default_factory=list, description="Data components used")


class DetectionStrategy(BaseModel):
    """MITRE ATT&CK Detection Strategy."""
    id: str = Field(..., description="Detection strategy ID (e.g., DET0210)")
    name: str = Field(..., description="Detection strategy name")
    description: Optional[str] = Field(None, description="Strategy description")
    techniques: List[str] = Field(default_factory=list, description="MITRE ATT&CK technique IDs (T####)")
    tactics: List[str] = Field(default_factory=list, description="MITRE ATT&CK tactics")
    platforms: List[str] = Field(default_factory=list, description="Supported platforms")
    analytics: List[DetectionStrategyAnalytic] = Field(
        default_factory=list,
        description="Platform-specific analytics"
    )
    domain: str = Field(default="Enterprise", description="ATT&CK domain (Enterprise, Mobile, ICS)")
    url: Optional[str] = Field(None, description="URL to MITRE ATT&CK page")
    
    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "id": "DET0210",
                "name": "Abuse of Domain Accounts",
                "description": "Detection strategy for detecting abuse of domain accounts",
                "techniques": ["T1078", "T1078.001"],
                "tactics": ["Defense Evasion", "Persistence"],
                "platforms": ["Windows"],
                "domain": "Enterprise"
            }
        }
    )


class DetectionStrategyMapping(BaseModel):
    """Mapping between techniques and detection strategies."""
    technique_id: str = Field(..., description="MITRE ATT&CK technique ID (T####)")
    detection_strategy_ids: List[str] = Field(
        default_factory=list,
        description="List of detection strategy IDs (DET####)"
    )
    primary_strategy: Optional[str] = Field(None, description="Primary detection strategy ID")


# ============================================================================
# Detection Strategy Service
# ============================================================================

class DetectionStrategyService:
    """Service for managing and querying detection strategies."""
    
    def __init__(self, cache_file: Optional[Path] = None):
        """
        Initialize the detection strategy service.
        
        Args:
            cache_file: Optional path to cache file for detection strategies
        """
        self.strategies: Dict[str, DetectionStrategy] = {}
        self.technique_to_strategies: Dict[str, List[str]] = {}
        self.cache_file = cache_file or Path(settings.data_dir) / "detection_strategies_cache.json"
        self._load_cache()
    
    def _load_cache(self) -> None:
        """Load detection strategies from cache file."""
        try:
            logger.info(f"Loading detection strategies from: {self.cache_file}")
            logger.info(f"Cache file exists: {self.cache_file.exists()}")
            if self.cache_file.exists():
                with open(self.cache_file, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                    strategies_list = data.get("strategies", [])
                    logger.info(f"Found {len(strategies_list)} strategies in cache file")
                    for strategy_data in strategies_list:
                        try:
                            strategy = DetectionStrategy(**strategy_data)
                            self.strategies[strategy.id] = strategy
                            
                            # Build technique mapping
                            for technique_id in strategy.techniques:
                                if technique_id not in self.technique_to_strategies:
                                    self.technique_to_strategies[technique_id] = []
                                if strategy.id not in self.technique_to_strategies[technique_id]:
                                    self.technique_to_strategies[technique_id].append(strategy.id)
                        except Exception as e:
                            logger.error(f"Failed to parse strategy {strategy_data.get('id', 'unknown')}: {e}")
                            continue
                
                logger.info(f"Loaded {len(self.strategies)} detection strategies from cache")
            else:
                logger.warning(f"Cache file does not exist: {self.cache_file}")
        except Exception as e:
            logger.error(f"Failed to load detection strategies cache: {e}", exc_info=True)
            # Initialize with empty cache - will be populated via API or manual import
    
    def _save_cache(self) -> None:
        """Save detection strategies to cache file."""
        try:
            self.cache_file.parent.mkdir(parents=True, exist_ok=True)
            data = {
                "strategies": [strategy.model_dump() for strategy in self.strategies.values()],
                "last_updated": datetime.utcnow().isoformat()
            }
            with open(self.cache_file, 'w', encoding='utf-8') as f:
                json.dump(data, f, indent=2, ensure_ascii=False)
            logger.info(f"Saved {len(self.strategies)} detection strategies to cache")
        except Exception as e:
            logger.error(f"Failed to save detection strategies cache: {e}")
    
    def add_strategy(self, strategy: DetectionStrategy) -> None:
        """Add or update a detection strategy."""
        self.strategies[strategy.id] = strategy
        
        # Update technique mapping
        for technique_id in strategy.techniques:
            if technique_id not in self.technique_to_strategies:
                self.technique_to_strategies[technique_id] = []
            if strategy.id not in self.technique_to_strategies[technique_id]:
                self.technique_to_strategies[technique_id].append(strategy.id)
        
        self._save_cache()
    
    def get_strategy(self, strategy_id: str) -> Optional[DetectionStrategy]:
        """Get a detection strategy by ID."""
        return self.strategies.get(strategy_id)
    
    def get_strategies_for_technique(self, technique_id: str) -> List[DetectionStrategy]:
        """
        Get all detection strategies for a given MITRE ATT&CK technique.
        
        Args:
            technique_id: MITRE ATT&CK technique ID (e.g., "T1046")
            
        Returns:
            List of detection strategies
        """
        strategy_ids = self.technique_to_strategies.get(technique_id, [])
        return [self.strategies[sid] for sid in strategy_ids if sid in self.strategies]
    
    def get_strategies_for_techniques(self, technique_ids: List[str]) -> Dict[str, List[DetectionStrategy]]:
        """
        Get detection strategies for multiple techniques.
        
        Args:
            technique_ids: List of MITRE ATT&CK technique IDs
            
        Returns:
            Dictionary mapping technique_id -> list of detection strategies
        """
        result = {}
        for technique_id in technique_ids:
            result[technique_id] = self.get_strategies_for_technique(technique_id)
        return result
    
    def find_strategies_by_name(self, name_query: str) -> List[DetectionStrategy]:
        """Find detection strategies by name (case-insensitive partial match)."""
        query_lower = name_query.lower()
        return [
            strategy for strategy in self.strategies.values()
            if query_lower in strategy.name.lower()
        ]
    
    def get_all_strategies(self) -> List[DetectionStrategy]:
        """Get all detection strategies."""
        return list(self.strategies.values())
    
    def get_coverage_gaps(self, technique_ids: List[str]) -> List[str]:
        """
        Identify techniques that have no detection strategies.
        
        Args:
            technique_ids: List of MITRE ATT&CK technique IDs to check
            
        Returns:
            List of technique IDs that have no detection strategies
        """
        gaps = []
        for technique_id in technique_ids:
            if not self.get_strategies_for_technique(technique_id):
                gaps.append(technique_id)
        return gaps
    
    def extract_technique_id(self, mitre_technique: str) -> Optional[str]:
        """
        Extract technique ID from various formats.
        
        Args:
            mitre_technique: Technique string in various formats:
                - "T1046"
                - "T1046 - Network Service Discovery"
                - "T1046.001"
                
        Returns:
            Technique ID (e.g., "T1046") or None if not found
        """
        if not mitre_technique:
            return None
        
        # Try to extract T#### pattern
        import re
        match = re.search(r'T\d{4}(?:\.\d{3})?', mitre_technique.upper())
        if match:
            # Return base technique ID (without sub-technique)
            base_id = match.group(0).split('.')[0]
            return base_id
        
        return None
    
    def get_defensive_guidance(self, technique_id: str) -> Optional[Dict[str, str]]:
        """
        Get defensive guidance for a technique that has no detection strategies.
        Provides actionable recommendations for defenders.
        
        Args:
            technique_id: MITRE ATT&CK technique ID (e.g., "T1059")
            
        Returns:
            Dictionary with guidance fields or None if no guidance available
        """
        guidance_map = {
            "T1059": {
                "title": "Command and Scripting Interpreter",
                "what_to_check": [
                    "Monitor for unusual command-line arguments and script execution",
                    "Check for execution of PowerShell, Bash, Python, or other interpreters",
                    "Look for encoded or obfuscated commands",
                    "Monitor process creation events for interpreter processes"
                ],
                "monitoring": [
                    "Process creation logs (Sysmon Event ID 1, Windows Event 4688)",
                    "Command-line logging (Sysmon Event ID 1)",
                    "Script execution logs (PowerShell logging, bash history)",
                    "Network connections from interpreter processes"
                ],
                "prevention": [
                    "Implement application whitelisting",
                    "Restrict script execution policies",
                    "Use constrained language modes (PowerShell)",
                    "Monitor and alert on suspicious command patterns"
                ],
                "mitre_url": "https://attack.mitre.org/techniques/T1059"
            },
            "T1021": {
                "title": "Remote Services",
                "what_to_check": [
                    "Monitor for unusual remote service connections (RDP, SSH, SMB, VNC)",
                    "Check for authentication failures followed by success",
                    "Look for connections from unusual IP addresses or geographic locations",
                    "Monitor for lateral movement patterns"
                ],
                "monitoring": [
                    "Authentication logs (Windows Event 4624, 4625)",
                    "Network connection logs",
                    "Remote service access logs (RDP, SSH session logs)",
                    "Account logon patterns and anomalies"
                ],
                "prevention": [
                    "Implement network segmentation",
                    "Use multi-factor authentication for remote access",
                    "Restrict remote service access to specific IP ranges",
                    "Monitor and alert on unusual remote access patterns"
                ],
                "mitre_url": "https://attack.mitre.org/techniques/T1021"
            },
            "T1083": {
                "title": "File and Directory Discovery",
                "what_to_check": [
                    "Monitor for enumeration of system directories",
                    "Check for access to sensitive file paths",
                    "Look for directory listing commands (dir, ls, find)",
                    "Monitor for access to user profile directories"
                ],
                "monitoring": [
                    "File system access logs",
                    "Process access to sensitive directories",
                    "Command-line logging showing directory enumeration",
                    "File access patterns and anomalies"
                ],
                "prevention": [
                    "Implement file access monitoring",
                    "Restrict access to sensitive directories",
                    "Monitor and alert on unusual file enumeration patterns",
                    "Use file integrity monitoring (FIM)"
                ],
                "mitre_url": "https://attack.mitre.org/techniques/T1083"
            },
            "T1018": {
                "title": "Remote System Discovery",
                "what_to_check": [
                    "Monitor for network scanning activities",
                    "Check for ping sweeps, port scans, or network mapping",
                    "Look for tools like nmap, masscan, or custom scanners",
                    "Monitor for DNS enumeration or reverse DNS lookups"
                ],
                "monitoring": [
                    "Network traffic logs",
                    "Firewall logs showing scan patterns",
                    "DNS query logs",
                    "ICMP and connection attempt logs"
                ],
                "prevention": [
                    "Implement network segmentation",
                    "Use network monitoring and IDS/IPS",
                    "Block or rate-limit ICMP and scanning traffic",
                    "Monitor and alert on network scanning patterns"
                ],
                "mitre_url": "https://attack.mitre.org/techniques/T1018"
            },
            "T1033": {
                "title": "System Owner/User Discovery",
                "what_to_check": [
                    "Monitor for commands that enumerate user accounts",
                    "Check for whoami, who, w, or similar commands",
                    "Look for enumeration of user profiles or home directories",
                    "Monitor for access to user account databases"
                ],
                "monitoring": [
                    "Command-line logging",
                    "Process execution logs",
                    "File access to user directories",
                    "Account enumeration attempts"
                ],
                "prevention": [
                    "Implement command-line logging",
                    "Monitor for user enumeration patterns",
                    "Restrict access to user account information",
                    "Alert on suspicious user discovery activities"
                ],
                "mitre_url": "https://attack.mitre.org/techniques/T1033"
            }
        }
        
        return guidance_map.get(technique_id)


# Global service instance
_detection_strategy_service: Optional[DetectionStrategyService] = None


def get_detection_strategy_service() -> DetectionStrategyService:
    """Get or create the global detection strategy service instance."""
    global _detection_strategy_service
    if _detection_strategy_service is None:
        _detection_strategy_service = DetectionStrategyService()
    return _detection_strategy_service

def reload_detection_strategy_service() -> DetectionStrategyService:
    """Force reload the detection strategy service (useful after cache updates)."""
    global _detection_strategy_service
    _detection_strategy_service = DetectionStrategyService()
    return _detection_strategy_service

