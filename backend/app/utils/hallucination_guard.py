"""
Hallucination Guard - Anti-hallucination validation layer for LLM outputs.

This module provides comprehensive validation to detect and prevent LLM hallucinations
in the Red Team KB application. It includes:
- MITRE ATT&CK technique validation
- Evidence grounding verification
- Fabrication detection heuristics
- Confidence-based filtering
"""
import json
import logging
import re
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from pathlib import Path
from typing import Any, Dict, List, Optional, Set, Tuple

from pydantic import BaseModel, Field

logger = logging.getLogger(__name__)


# ============================================================================
# MITRE ATT&CK Validation
# ============================================================================

class MITREValidator:
    """
    Validates MITRE ATT&CK technique IDs against the official database.
    
    This prevents the LLM from inventing non-existent technique IDs.
    """
    
    # Official MITRE ATT&CK Enterprise techniques (v14.1 - October 2023)
    # This is a comprehensive list - in production, load from MITRE STIX data
    VALID_TECHNIQUES: Set[str] = {
        # Reconnaissance
        "T1595", "T1595.001", "T1595.002", "T1595.003",
        "T1592", "T1592.001", "T1592.002", "T1592.003", "T1592.004",
        "T1589", "T1589.001", "T1589.002", "T1589.003",
        "T1590", "T1590.001", "T1590.002", "T1590.003", "T1590.004", "T1590.005", "T1590.006",
        "T1591", "T1591.001", "T1591.002", "T1591.003", "T1591.004",
        "T1598", "T1598.001", "T1598.002", "T1598.003",
        "T1597", "T1597.001", "T1597.002",
        "T1596", "T1596.001", "T1596.002", "T1596.003", "T1596.004", "T1596.005",
        "T1593", "T1593.001", "T1593.002", "T1593.003",
        "T1594",
        
        # Resource Development
        "T1583", "T1583.001", "T1583.002", "T1583.003", "T1583.004", "T1583.005", "T1583.006", "T1583.007", "T1583.008",
        "T1586", "T1586.001", "T1586.002", "T1586.003",
        "T1584", "T1584.001", "T1584.002", "T1584.003", "T1584.004", "T1584.005", "T1584.006", "T1584.007",
        "T1587", "T1587.001", "T1587.002", "T1587.003", "T1587.004",
        "T1585", "T1585.001", "T1585.002", "T1585.003",
        "T1588", "T1588.001", "T1588.002", "T1588.003", "T1588.004", "T1588.005", "T1588.006",
        "T1608", "T1608.001", "T1608.002", "T1608.003", "T1608.004", "T1608.005", "T1608.006",
        
        # Initial Access
        "T1189", "T1190", "T1133", "T1200", "T1566", "T1566.001", "T1566.002", "T1566.003",
        "T1091", "T1195", "T1195.001", "T1195.002", "T1195.003",
        "T1199", "T1078", "T1078.001", "T1078.002", "T1078.003", "T1078.004",
        
        # Execution
        "T1059", "T1059.001", "T1059.002", "T1059.003", "T1059.004", "T1059.005", "T1059.006", "T1059.007", "T1059.008", "T1059.009",
        "T1609", "T1610", "T1203", "T1559", "T1559.001", "T1559.002", "T1559.003",
        "T1106", "T1053", "T1053.001", "T1053.002", "T1053.003", "T1053.005", "T1053.006", "T1053.007",
        "T1129", "T1072", "T1569", "T1569.001", "T1569.002",
        "T1204", "T1204.001", "T1204.002", "T1204.003",
        "T1047",
        
        # Persistence
        "T1098", "T1098.001", "T1098.002", "T1098.003", "T1098.004", "T1098.005",
        "T1197", "T1547", "T1547.001", "T1547.002", "T1547.003", "T1547.004", "T1547.005", "T1547.006", 
        "T1547.007", "T1547.008", "T1547.009", "T1547.010", "T1547.012", "T1547.013", "T1547.014", "T1547.015",
        "T1037", "T1037.001", "T1037.002", "T1037.003", "T1037.004", "T1037.005",
        "T1176", "T1554", "T1136", "T1136.001", "T1136.002", "T1136.003",
        "T1543", "T1543.001", "T1543.002", "T1543.003", "T1543.004",
        "T1546", "T1546.001", "T1546.002", "T1546.003", "T1546.004", "T1546.005", "T1546.006", 
        "T1546.007", "T1546.008", "T1546.009", "T1546.010", "T1546.011", "T1546.012", "T1546.013", 
        "T1546.014", "T1546.015", "T1546.016",
        "T1133", "T1574", "T1574.001", "T1574.002", "T1574.004", "T1574.005", "T1574.006", 
        "T1574.007", "T1574.008", "T1574.009", "T1574.010", "T1574.011", "T1574.012", "T1574.013",
        "T1525", "T1556", "T1556.001", "T1556.002", "T1556.003", "T1556.004", "T1556.005", "T1556.006", "T1556.007", "T1556.008",
        "T1137", "T1137.001", "T1137.002", "T1137.003", "T1137.004", "T1137.005", "T1137.006",
        "T1542", "T1542.001", "T1542.002", "T1542.003", "T1542.004", "T1542.005",
        "T1505", "T1505.001", "T1505.002", "T1505.003", "T1505.004", "T1505.005",
        "T1205", "T1205.001", "T1205.002",
        
        # Privilege Escalation
        "T1548", "T1548.001", "T1548.002", "T1548.003", "T1548.004",
        "T1134", "T1134.001", "T1134.002", "T1134.003", "T1134.004", "T1134.005",
        "T1068", "T1484", "T1484.001", "T1484.002",
        "T1611", "T1055", "T1055.001", "T1055.002", "T1055.003", "T1055.004", "T1055.005", 
        "T1055.008", "T1055.009", "T1055.011", "T1055.012", "T1055.013", "T1055.014", "T1055.015",
        
        # Defense Evasion
        "T1612", "T1622", "T1140", "T1610", "T1006", "T1480", "T1480.001",
        "T1211", "T1222", "T1222.001", "T1222.002",
        "T1564", "T1564.001", "T1564.002", "T1564.003", "T1564.004", "T1564.005", "T1564.006", 
        "T1564.007", "T1564.008", "T1564.009", "T1564.010",
        "T1562", "T1562.001", "T1562.002", "T1562.003", "T1562.004", "T1562.006", "T1562.007", 
        "T1562.008", "T1562.009", "T1562.010",
        "T1070", "T1070.001", "T1070.002", "T1070.003", "T1070.004", "T1070.005", "T1070.006", "T1070.007", "T1070.008", "T1070.009",
        "T1202", "T1036", "T1036.001", "T1036.002", "T1036.003", "T1036.004", "T1036.005", "T1036.006", "T1036.007", "T1036.008",
        "T1556", "T1578", "T1578.001", "T1578.002", "T1578.003", "T1578.004",
        "T1112", "T1601", "T1601.001", "T1601.002",
        "T1599", "T1599.001", "T1027", "T1027.001", "T1027.002", "T1027.003", "T1027.004", "T1027.005", 
        "T1027.006", "T1027.007", "T1027.008", "T1027.009", "T1027.010", "T1027.011",
        "T1647", "T1542", "T1620", "T1207", "T1014", "T1553", "T1553.001", "T1553.002", "T1553.003", 
        "T1553.004", "T1553.005", "T1553.006",
        "T1218", "T1218.001", "T1218.002", "T1218.003", "T1218.004", "T1218.005", "T1218.007", 
        "T1218.008", "T1218.009", "T1218.010", "T1218.011", "T1218.012", "T1218.013", "T1218.014",
        "T1216", "T1216.001", "T1221", "T1205", "T1127", "T1127.001",
        "T1535", "T1550", "T1550.001", "T1550.002", "T1550.003", "T1550.004",
        "T1497", "T1497.001", "T1497.002", "T1497.003",
        "T1600", "T1600.001", "T1600.002", "T1220",
        
        # Credential Access
        "T1557", "T1557.001", "T1557.002", "T1557.003",
        "T1110", "T1110.001", "T1110.002", "T1110.003", "T1110.004",
        "T1555", "T1555.001", "T1555.002", "T1555.003", "T1555.004", "T1555.005",
        "T1212", "T1187", "T1606", "T1606.001", "T1606.002",
        "T1056", "T1056.001", "T1056.002", "T1056.003", "T1056.004",
        "T1556", "T1111", "T1621", "T1040",
        "T1003", "T1003.001", "T1003.002", "T1003.003", "T1003.004", "T1003.005", "T1003.006", "T1003.007", "T1003.008",
        "T1528", "T1558", "T1558.001", "T1558.002", "T1558.003", "T1558.004",
        "T1539", "T1552", "T1552.001", "T1552.002", "T1552.003", "T1552.004", "T1552.005", "T1552.006", "T1552.007",
        
        # Discovery
        "T1087", "T1087.001", "T1087.002", "T1087.003", "T1087.004",
        "T1010", "T1217", "T1580", "T1538", "T1526",
        "T1619", "T1613", "T1622",
        "T1482", "T1083", "T1615", "T1046", "T1135", "T1040",
        "T1201", "T1120", "T1069", "T1069.001", "T1069.002", "T1069.003",
        "T1057", "T1012", "T1018", "T1518", "T1518.001",
        "T1082", "T1614", "T1614.001", "T1016", "T1016.001",
        "T1049", "T1033", "T1007", "T1124", "T1497",
        
        # Lateral Movement
        "T1210", "T1534", "T1570",
        "T1563", "T1563.001", "T1563.002",
        "T1021", "T1021.001", "T1021.002", "T1021.003", "T1021.004", "T1021.005", "T1021.006",
        "T1091", "T1072", "T1080", "T1550",
        
        # Collection
        "T1560", "T1560.001", "T1560.002", "T1560.003",
        "T1123", "T1119", "T1115", "T1530",
        "T1602", "T1602.001", "T1602.002",
        "T1213", "T1213.001", "T1213.002", "T1213.003",
        "T1005", "T1039", "T1025", "T1074", "T1074.001", "T1074.002",
        "T1114", "T1114.001", "T1114.002", "T1114.003",
        "T1056", "T1185", "T1113", "T1125",
        
        # Command and Control
        "T1071", "T1071.001", "T1071.002", "T1071.003", "T1071.004",
        "T1092", "T1132", "T1132.001", "T1132.002",
        "T1001", "T1001.001", "T1001.002", "T1001.003",
        "T1568", "T1568.001", "T1568.002", "T1568.003",
        "T1573", "T1573.001", "T1573.002",
        "T1008", "T1105", "T1104",
        "T1095", "T1571", "T1572", "T1090", "T1090.001", "T1090.002", "T1090.003", "T1090.004",
        "T1219", "T1205", "T1102", "T1102.001", "T1102.002", "T1102.003",
        
        # Exfiltration
        "T1020", "T1020.001", "T1030", "T1048", "T1048.001", "T1048.002", "T1048.003",
        "T1041", "T1011", "T1011.001",
        "T1052", "T1052.001", "T1567", "T1567.001", "T1567.002",
        "T1029", "T1537",
        
        # Impact
        "T1531", "T1485", "T1486", "T1565", "T1565.001", "T1565.002", "T1565.003",
        "T1491", "T1491.001", "T1491.002",
        "T1561", "T1561.001", "T1561.002",
        "T1499", "T1499.001", "T1499.002", "T1499.003", "T1499.004",
        "T1495", "T1490", "T1498", "T1498.001", "T1498.002",
        "T1496", "T1489", "T1529",
    }
    
    # Tactic to technique mapping for validation
    VALID_TACTICS: Set[str] = {
        "Reconnaissance", "Resource Development", "Initial Access", "Execution",
        "Persistence", "Privilege Escalation", "Defense Evasion", "Credential Access",
        "Discovery", "Lateral Movement", "Collection", "Command and Control",
        "Exfiltration", "Impact"
    }
    
    @classmethod
    def is_valid_technique(cls, technique_id: str) -> bool:
        """Check if a technique ID is valid."""
        if not technique_id:
            return False
        
        # Normalize the technique ID
        normalized = cls.normalize_technique_id(technique_id)
        if not normalized:
            return False
        
        return normalized in cls.VALID_TECHNIQUES
    
    @classmethod
    def normalize_technique_id(cls, technique_str: str) -> Optional[str]:
        """
        Extract and normalize a technique ID from various formats.
        
        Examples:
            "T1046" -> "T1046"
            "T1046 - Network Service Discovery" -> "T1046"
            "t1046.001" -> "T1046.001"
        """
        if not technique_str:
            return None
        
        # Find T#### or T####.### pattern
        match = re.search(r'[Tt](\d{4})(?:\.(\d{3}))?', technique_str)
        if match:
            base = f"T{match.group(1)}"
            if match.group(2):
                return f"{base}.{match.group(2)}"
            return base
        
        return None
    
    @classmethod
    def is_valid_tactic(cls, tactic: str) -> bool:
        """Check if a tactic name is valid."""
        if not tactic:
            return False
        
        # Normalize and check
        normalized = tactic.strip().title()
        # Handle special cases
        normalized = normalized.replace("And", "and")
        
        return normalized in cls.VALID_TACTICS or tactic in cls.VALID_TACTICS
    
    @classmethod
    def validate_technique_tactic_pair(cls, technique_id: str, tactic: str) -> Tuple[bool, str]:
        """
        Validate that a technique-tactic pair is valid.
        
        Returns:
            Tuple of (is_valid, error_message)
        """
        errors = []
        
        if technique_id and not cls.is_valid_technique(technique_id):
            normalized = cls.normalize_technique_id(technique_id)
            if normalized:
                errors.append(f"Unknown MITRE technique: {normalized}")
            else:
                errors.append(f"Invalid technique format: {technique_id}")
        
        if tactic and not cls.is_valid_tactic(tactic):
            errors.append(f"Unknown MITRE tactic: {tactic}")
        
        if errors:
            return False, "; ".join(errors)
        
        return True, ""
    
    @classmethod
    def suggest_closest_technique(cls, invalid_id: str) -> Optional[str]:
        """Suggest the closest valid technique ID for a typo."""
        normalized = cls.normalize_technique_id(invalid_id)
        if not normalized:
            return None
        
        # Extract base technique number
        base_match = re.match(r'T(\d{4})', normalized)
        if not base_match:
            return None
        
        base_num = int(base_match.group(1))
        
        # Find closest valid technique
        closest = None
        min_diff = float('inf')
        
        for valid_tech in cls.VALID_TECHNIQUES:
            valid_match = re.match(r'T(\d{4})', valid_tech)
            if valid_match:
                valid_num = int(valid_match.group(1))
                diff = abs(valid_num - base_num)
                if diff < min_diff:
                    min_diff = diff
                    closest = valid_tech
        
        return closest if min_diff <= 10 else None


# ============================================================================
# Evidence Grounding Validator
# ============================================================================

class EvidenceGroundingValidator:
    """
    Validates that LLM claims are grounded in the provided source data.
    
    Detects when the LLM fabricates:
    - IP addresses not in the source
    - Domains not in the source
    - Tools not mentioned in terminal content
    - Commands that weren't executed
    """
    
    # Regex patterns for extracting entities
    IP_PATTERN = re.compile(r'\b(?:\d{1,3}\.){3}\d{1,3}\b')
    DOMAIN_PATTERN = re.compile(r'\b(?:[a-zA-Z0-9](?:[a-zA-Z0-9-]{0,61}[a-zA-Z0-9])?\.)+[a-zA-Z]{2,}\b')
    MAC_PATTERN = re.compile(r'\b(?:[0-9A-Fa-f]{2}[:-]){5}[0-9A-Fa-f]{2}\b')
    HASH_PATTERN = re.compile(r'\b[a-fA-F0-9]{32,64}\b')
    
    # Common security tools to check for
    KNOWN_TOOLS = {
        "nmap", "masscan", "metasploit", "msfconsole", "msfvenom", "hydra",
        "john", "hashcat", "burp", "sqlmap", "nikto", "gobuster", "dirb",
        "dirbuster", "ffuf", "wfuzz", "nuclei", "nessus", "openvas",
        "wireshark", "tcpdump", "netcat", "nc", "socat", "curl", "wget",
        "ssh", "scp", "ftp", "telnet", "rdesktop", "xfreerdp", "evil-winrm",
        "crackmapexec", "cme", "impacket", "psexec", "wmiexec", "smbexec",
        "mimikatz", "rubeus", "bloodhound", "sharphound", "powerview",
        "empire", "covenant", "cobalt", "responder", "bettercap", "ettercap",
        "aircrack", "airmon", "aireplay", "reaver", "wpscan", "droopescan",
        "enum4linux", "smbclient", "rpcclient", "ldapsearch", "kerbrute",
        "secretsdump", "GetUserSPNs", "GetNPUsers", "dnsrecon", "sublist3r",
        "amass", "subfinder", "httpx", "aquatone", "eyewitness"
    }
    
    @classmethod
    def extract_entities_from_text(cls, text: str) -> Dict[str, Set[str]]:
        """Extract all identifiable entities from text."""
        return {
            "ips": set(cls.IP_PATTERN.findall(text)),
            "domains": set(cls.DOMAIN_PATTERN.findall(text.lower())),
            "macs": set(cls.MAC_PATTERN.findall(text)),
            "hashes": set(cls.HASH_PATTERN.findall(text.lower())),
            "tools": cls._extract_tools(text)
        }
    
    @classmethod
    def _extract_tools(cls, text: str) -> Set[str]:
        """Extract security tool mentions from text."""
        text_lower = text.lower()
        found_tools = set()
        
        for tool in cls.KNOWN_TOOLS:
            # Check for tool as a word (not part of another word)
            if re.search(rf'\b{re.escape(tool)}\b', text_lower):
                found_tools.add(tool)
        
        return found_tools
    
    @classmethod
    def validate_grounding(
        cls,
        llm_response: str,
        source_context: str
    ) -> "GroundingValidationResult":
        """
        Validate that entities in the LLM response are grounded in the source.
        
        Args:
            llm_response: The LLM's output text
            source_context: The original source data provided to the LLM
            
        Returns:
            GroundingValidationResult with details about fabrications
        """
        source_entities = cls.extract_entities_from_text(source_context)
        response_entities = cls.extract_entities_from_text(llm_response)
        
        fabrications = []
        warnings = []
        
        # Check for fabricated IPs
        fabricated_ips = response_entities["ips"] - source_entities["ips"]
        # Filter out common non-fabrication IPs
        fabricated_ips = {ip for ip in fabricated_ips 
                         if not ip.startswith("127.") 
                         and not ip.startswith("0.")
                         and ip != "255.255.255.255"}
        
        if fabricated_ips:
            fabrications.append(FabricationDetail(
                entity_type="IP Address",
                fabricated_values=list(fabricated_ips),
                severity="high",
                message=f"Response contains {len(fabricated_ips)} IP(s) not found in source data"
            ))
        
        # Check for fabricated domains
        fabricated_domains = response_entities["domains"] - source_entities["domains"]
        # Filter out common domains
        common_domains = {"example.com", "localhost", "test.com", "domain.com"}
        fabricated_domains = fabricated_domains - common_domains
        
        if fabricated_domains:
            # This might be less severe as LLM might use example domains
            warnings.append(FabricationDetail(
                entity_type="Domain",
                fabricated_values=list(fabricated_domains),
                severity="medium",
                message=f"Response mentions {len(fabricated_domains)} domain(s) not in source"
            ))
        
        # Check for fabricated tools
        fabricated_tools = response_entities["tools"] - source_entities["tools"]
        if fabricated_tools:
            warnings.append(FabricationDetail(
                entity_type="Tool",
                fabricated_values=list(fabricated_tools),
                severity="low",
                message=f"Response mentions tools not explicitly in source: {fabricated_tools}"
            ))
        
        # Calculate grounding score
        total_entities = sum(len(v) for v in response_entities.values())
        fabricated_count = len(fabricated_ips) + len(fabricated_domains)
        
        if total_entities > 0:
            grounding_score = 1.0 - (fabricated_count / total_entities)
        else:
            grounding_score = 1.0
        
        return GroundingValidationResult(
            is_grounded=len(fabrications) == 0,
            grounding_score=max(0.0, grounding_score),
            fabrications=fabrications,
            warnings=warnings,
            source_entity_count=sum(len(v) for v in source_entities.values()),
            response_entity_count=total_entities
        )


@dataclass
class FabricationDetail:
    """Details about a detected fabrication."""
    entity_type: str
    fabricated_values: List[str]
    severity: str  # "high", "medium", "low"
    message: str


@dataclass
class GroundingValidationResult:
    """Result of grounding validation."""
    is_grounded: bool
    grounding_score: float  # 0.0 to 1.0
    fabrications: List[FabricationDetail]
    warnings: List[FabricationDetail]
    source_entity_count: int
    response_entity_count: int
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "is_grounded": self.is_grounded,
            "grounding_score": self.grounding_score,
            "fabrications": [
                {
                    "entity_type": f.entity_type,
                    "fabricated_values": f.fabricated_values,
                    "severity": f.severity,
                    "message": f.message
                }
                for f in self.fabrications
            ],
            "warnings": [
                {
                    "entity_type": w.entity_type,
                    "fabricated_values": w.fabricated_values,
                    "severity": w.severity,
                    "message": w.message
                }
                for w in self.warnings
            ],
            "source_entity_count": self.source_entity_count,
            "response_entity_count": self.response_entity_count
        }


# ============================================================================
# Hallucination Detection Heuristics
# ============================================================================

class HallucinationDetector:
    """
    Detects potential hallucinations using various heuristics.
    """
    
    # Phrases that often indicate hallucination or uncertainty
    UNCERTAINTY_PHRASES = [
        "i believe", "i think", "probably", "likely", "possibly", "might be",
        "could be", "it seems", "appears to", "it looks like", "presumably",
        "i assume", "i would guess", "typically", "generally", "usually",
        "in most cases", "often", "sometimes"
    ]
    
    # Phrases that indicate the LLM is making things up
    FABRICATION_INDICATORS = [
        "for example", "such as", "like", "e.g.", "i.e.",
        "hypothetically", "in theory", "theoretically",
        "let's say", "imagine", "suppose"
    ]
    
    # Phrases indicating the LLM doesn't have the information
    NO_INFO_PHRASES = [
        "i don't have", "i cannot find", "there is no", "no information",
        "not mentioned", "not specified", "unclear", "unknown",
        "i don't see", "i couldn't find", "not available"
    ]
    
    @classmethod
    def detect_hallucination_indicators(cls, response: str) -> "HallucinationAnalysis":
        """
        Analyze response for hallucination indicators.
        
        Args:
            response: LLM response text
            
        Returns:
            HallucinationAnalysis with detected indicators
        """
        response_lower = response.lower()
        
        uncertainty_found = []
        fabrication_found = []
        no_info_found = []
        
        for phrase in cls.UNCERTAINTY_PHRASES:
            if phrase in response_lower:
                uncertainty_found.append(phrase)
        
        for phrase in cls.FABRICATION_INDICATORS:
            if phrase in response_lower:
                fabrication_found.append(phrase)
        
        for phrase in cls.NO_INFO_PHRASES:
            if phrase in response_lower:
                no_info_found.append(phrase)
        
        # Calculate risk score
        risk_score = 0.0
        risk_score += len(uncertainty_found) * 0.1
        risk_score += len(fabrication_found) * 0.15
        risk_score += len(no_info_found) * 0.05  # This is actually good - LLM admits it doesn't know
        
        # Cap at 1.0
        risk_score = min(1.0, risk_score)
        
        # Determine if the LLM is being appropriately uncertain
        admits_uncertainty = len(no_info_found) > 0
        
        return HallucinationAnalysis(
            hallucination_risk_score=risk_score,
            uncertainty_phrases=uncertainty_found,
            fabrication_indicators=fabrication_found,
            admits_lack_of_info=admits_uncertainty,
            no_info_phrases=no_info_found,
            recommendation=cls._get_recommendation(risk_score, admits_uncertainty)
        )
    
    @classmethod
    def _get_recommendation(cls, risk_score: float, admits_uncertainty: bool) -> str:
        """Get recommendation based on analysis."""
        if risk_score < 0.2:
            return "Low hallucination risk - response appears confident and grounded"
        elif risk_score < 0.5:
            if admits_uncertainty:
                return "Moderate risk but LLM appropriately expresses uncertainty - verify key claims"
            return "Moderate hallucination risk - recommend manual verification of key claims"
        else:
            return "High hallucination risk - manual review strongly recommended"


@dataclass
class HallucinationAnalysis:
    """Analysis of hallucination indicators in a response."""
    hallucination_risk_score: float
    uncertainty_phrases: List[str]
    fabrication_indicators: List[str]
    admits_lack_of_info: bool
    no_info_phrases: List[str]
    recommendation: str
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "hallucination_risk_score": self.hallucination_risk_score,
            "uncertainty_phrases": self.uncertainty_phrases,
            "fabrication_indicators": self.fabrication_indicators,
            "admits_lack_of_info": self.admits_lack_of_info,
            "no_info_phrases": self.no_info_phrases,
            "recommendation": self.recommendation
        }


# ============================================================================
# Confidence Threshold Manager
# ============================================================================

class ConfidenceThresholdManager:
    """
    Manages confidence thresholds for different types of LLM outputs.
    """
    
    # Default thresholds
    DEFAULT_THRESHOLDS = {
        "faa_classification": 0.7,      # FAA action/finding classification
        "mitre_mapping": 0.8,           # MITRE technique mapping
        "severity_assessment": 0.75,    # Severity classification
        "expert_analysis": 0.6,         # General expert analysis
        "metadata_extraction": 0.65,    # Tool/target extraction
    }
    
    # Thresholds that require human review
    REVIEW_THRESHOLDS = {
        "faa_classification": 0.5,
        "mitre_mapping": 0.6,
        "severity_assessment": 0.5,
        "expert_analysis": 0.4,
        "metadata_extraction": 0.4,
    }
    
    @classmethod
    def should_accept(cls, output_type: str, confidence: float) -> bool:
        """Check if output should be automatically accepted."""
        threshold = cls.DEFAULT_THRESHOLDS.get(output_type, 0.7)
        return confidence >= threshold
    
    @classmethod
    def needs_review(cls, output_type: str, confidence: float) -> bool:
        """Check if output needs human review."""
        accept_threshold = cls.DEFAULT_THRESHOLDS.get(output_type, 0.7)
        review_threshold = cls.REVIEW_THRESHOLDS.get(output_type, 0.5)
        
        return review_threshold <= confidence < accept_threshold
    
    @classmethod
    def should_reject(cls, output_type: str, confidence: float) -> bool:
        """Check if output should be rejected."""
        review_threshold = cls.REVIEW_THRESHOLDS.get(output_type, 0.5)
        return confidence < review_threshold
    
    @classmethod
    def get_action(cls, output_type: str, confidence: float) -> str:
        """Get recommended action for given confidence level."""
        if cls.should_accept(output_type, confidence):
            return "accept"
        elif cls.needs_review(output_type, confidence):
            return "review"
        else:
            return "reject"


# ============================================================================
# Comprehensive Validation Result
# ============================================================================

@dataclass
class HallucinationGuardResult:
    """Comprehensive result from hallucination guard validation."""
    
    # Overall assessment
    is_valid: bool
    overall_confidence: float
    recommended_action: str  # "accept", "review", "reject"
    
    # Component results
    mitre_validation: Optional[Dict[str, Any]] = None
    grounding_validation: Optional[GroundingValidationResult] = None
    hallucination_analysis: Optional[HallucinationAnalysis] = None
    
    # Issues found
    critical_issues: List[str] = field(default_factory=list)
    warnings: List[str] = field(default_factory=list)
    
    # Corrections made
    corrections: Dict[str, Any] = field(default_factory=dict)
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "is_valid": self.is_valid,
            "overall_confidence": self.overall_confidence,
            "recommended_action": self.recommended_action,
            "mitre_validation": self.mitre_validation,
            "grounding_validation": self.grounding_validation.to_dict() if self.grounding_validation else None,
            "hallucination_analysis": self.hallucination_analysis.to_dict() if self.hallucination_analysis else None,
            "critical_issues": self.critical_issues,
            "warnings": self.warnings,
            "corrections": self.corrections
        }


# ============================================================================
# Main Hallucination Guard Class
# ============================================================================

class HallucinationGuard:
    """
    Main class that orchestrates all hallucination detection and prevention.
    
    Usage:
        guard = HallucinationGuard()
        result = guard.validate_faa_item(faa_data, source_context)
        
        if not result.is_valid:
            # Handle invalid output
            logger.warning(f"Hallucination detected: {result.critical_issues}")
    """
    
    def __init__(
        self,
        strict_mitre_validation: bool = True,
        grounding_threshold: float = 0.7,
        enable_auto_correction: bool = True
    ):
        """
        Initialize the hallucination guard.
        
        Args:
            strict_mitre_validation: If True, reject invalid MITRE techniques
            grounding_threshold: Minimum grounding score to accept
            enable_auto_correction: If True, attempt to correct minor issues
        """
        self.strict_mitre_validation = strict_mitre_validation
        self.grounding_threshold = grounding_threshold
        self.enable_auto_correction = enable_auto_correction
    
    def validate_faa_item(
        self,
        faa_data: Dict[str, Any],
        source_context: str,
        original_confidence: float = 0.7
    ) -> HallucinationGuardResult:
        """
        Validate a Findings and Actions (FAA) item.
        
        Args:
            faa_data: The FAA item data from LLM
            source_context: Original terminal/screenshot content
            original_confidence: LLM's reported confidence
            
        Returns:
            HallucinationGuardResult with validation details
        """
        critical_issues = []
        warnings = []
        corrections = {}
        
        # 1. Validate MITRE technique
        mitre_validation = None
        mitre_technique = faa_data.get("mitre_technique")
        mitre_tactic = faa_data.get("mitre_tactic")
        
        if mitre_technique:
            is_valid, error = MITREValidator.validate_technique_tactic_pair(
                mitre_technique, mitre_tactic
            )
            
            mitre_validation = {
                "technique": mitre_technique,
                "tactic": mitre_tactic,
                "is_valid": is_valid,
                "error": error if not is_valid else None
            }
            
            if not is_valid:
                if self.strict_mitre_validation:
                    critical_issues.append(f"Invalid MITRE mapping: {error}")
                else:
                    warnings.append(f"Potentially invalid MITRE mapping: {error}")
                
                # Try to suggest correction
                if self.enable_auto_correction:
                    normalized = MITREValidator.normalize_technique_id(mitre_technique)
                    if normalized:
                        suggestion = MITREValidator.suggest_closest_technique(normalized)
                        if suggestion:
                            corrections["suggested_technique"] = suggestion
                            mitre_validation["suggestion"] = suggestion
        
        # 2. Validate grounding
        content = faa_data.get("content", "") + " " + faa_data.get("output", "")
        grounding_result = EvidenceGroundingValidator.validate_grounding(
            content, source_context
        )
        
        if not grounding_result.is_grounded:
            for fab in grounding_result.fabrications:
                if fab.severity == "high":
                    critical_issues.append(fab.message)
                else:
                    warnings.append(fab.message)
        
        for warn in grounding_result.warnings:
            warnings.append(warn.message)
        
        # 3. Analyze for hallucination indicators
        hallucination_analysis = HallucinationDetector.detect_hallucination_indicators(
            content
        )
        
        if hallucination_analysis.hallucination_risk_score > 0.5:
            warnings.append(hallucination_analysis.recommendation)
        
        # 4. Calculate overall confidence
        confidence_factors = [
            original_confidence,
            grounding_result.grounding_score,
            1.0 - hallucination_analysis.hallucination_risk_score,
            1.0 if (mitre_validation is None or mitre_validation["is_valid"]) else 0.5
        ]
        overall_confidence = sum(confidence_factors) / len(confidence_factors)
        
        # 5. Determine recommended action
        action = ConfidenceThresholdManager.get_action("faa_classification", overall_confidence)
        
        # Override if there are critical issues
        if critical_issues:
            action = "reject" if self.strict_mitre_validation else "review"
        
        is_valid = len(critical_issues) == 0 and overall_confidence >= 0.5
        
        return HallucinationGuardResult(
            is_valid=is_valid,
            overall_confidence=overall_confidence,
            recommended_action=action,
            mitre_validation=mitre_validation,
            grounding_validation=grounding_result,
            hallucination_analysis=hallucination_analysis,
            critical_issues=critical_issues,
            warnings=warnings,
            corrections=corrections
        )
    
    def validate_expert_analysis(
        self,
        analysis_data: Dict[str, Any],
        source_context: str,
        session_ids: Set[str]
    ) -> HallucinationGuardResult:
        """
        Validate expert analysis output.
        
        Args:
            analysis_data: The expert analysis data from LLM
            source_context: Combined session data
            session_ids: Set of valid session IDs
            
        Returns:
            HallucinationGuardResult with validation details
        """
        critical_issues = []
        warnings = []
        
        # 1. Validate evidence sessions
        evidence_sessions = analysis_data.get("evidence_sessions", [])
        invalid_sessions = [sid for sid in evidence_sessions if sid not in session_ids]
        
        if invalid_sessions:
            warnings.append(f"Referenced {len(invalid_sessions)} non-existent session(s)")
        
        # 2. Validate grounding of text content
        text_content = " ".join([
            analysis_data.get("progress_summary", ""),
            analysis_data.get("risk_assessment", ""),
            " ".join(analysis_data.get("recommendations", [])),
            " ".join(analysis_data.get("gaps_identified", []))
        ])
        
        grounding_result = EvidenceGroundingValidator.validate_grounding(
            text_content, source_context
        )
        
        if grounding_result.grounding_score < self.grounding_threshold:
            warnings.append(
                f"Analysis may contain ungrounded claims (grounding score: {grounding_result.grounding_score:.2f})"
            )
        
        # 3. Analyze for hallucination
        hallucination_analysis = HallucinationDetector.detect_hallucination_indicators(
            text_content
        )
        
        # 4. Calculate confidence
        overall_confidence = (
            grounding_result.grounding_score * 0.4 +
            (1.0 - hallucination_analysis.hallucination_risk_score) * 0.3 +
            (1.0 - len(invalid_sessions) / max(len(evidence_sessions), 1)) * 0.3
        )
        
        action = ConfidenceThresholdManager.get_action("expert_analysis", overall_confidence)
        
        return HallucinationGuardResult(
            is_valid=len(critical_issues) == 0,
            overall_confidence=overall_confidence,
            recommended_action=action,
            grounding_validation=grounding_result,
            hallucination_analysis=hallucination_analysis,
            critical_issues=critical_issues,
            warnings=warnings
        )
    
    def validate_query_response(
        self,
        response: str,
        source_context: str,
        question: str
    ) -> HallucinationGuardResult:
        """
        Validate a Q&A query response.
        
        Args:
            response: LLM's response to the query
            source_context: The context provided to the LLM
            question: The original question
            
        Returns:
            HallucinationGuardResult with validation details
        """
        warnings = []
        
        # 1. Validate grounding
        grounding_result = EvidenceGroundingValidator.validate_grounding(
            response, source_context
        )
        
        if not grounding_result.is_grounded:
            for fab in grounding_result.fabrications:
                warnings.append(fab.message)
        
        # 2. Analyze for hallucination
        hallucination_analysis = HallucinationDetector.detect_hallucination_indicators(
            response
        )
        
        # 3. Check if response admits lack of information (this is good!)
        if hallucination_analysis.admits_lack_of_info:
            # Boost confidence when LLM appropriately says it doesn't know
            confidence_boost = 0.1
        else:
            confidence_boost = 0.0
        
        overall_confidence = (
            grounding_result.grounding_score * 0.5 +
            (1.0 - hallucination_analysis.hallucination_risk_score) * 0.5 +
            confidence_boost
        )
        overall_confidence = min(1.0, overall_confidence)
        
        action = "accept" if overall_confidence >= 0.6 else "review"
        
        return HallucinationGuardResult(
            is_valid=overall_confidence >= 0.5,
            overall_confidence=overall_confidence,
            recommended_action=action,
            grounding_validation=grounding_result,
            hallucination_analysis=hallucination_analysis,
            warnings=warnings
        )


# ============================================================================
# Convenience Functions
# ============================================================================

def validate_mitre_technique(technique: str) -> Tuple[bool, Optional[str], Optional[str]]:
    """
    Quick validation of a MITRE technique.
    
    Returns:
        Tuple of (is_valid, normalized_id, error_message)
    """
    normalized = MITREValidator.normalize_technique_id(technique)
    if not normalized:
        return False, None, f"Invalid technique format: {technique}"
    
    if MITREValidator.is_valid_technique(normalized):
        return True, normalized, None
    
    suggestion = MITREValidator.suggest_closest_technique(normalized)
    error = f"Unknown technique: {normalized}"
    if suggestion:
        error += f" (did you mean {suggestion}?)"
    
    return False, normalized, error


def check_grounding(response: str, context: str) -> float:
    """
    Quick check of response grounding.
    
    Returns:
        Grounding score from 0.0 to 1.0
    """
    result = EvidenceGroundingValidator.validate_grounding(response, context)
    return result.grounding_score


def get_hallucination_risk(text: str) -> float:
    """
    Quick assessment of hallucination risk.
    
    Returns:
        Risk score from 0.0 to 1.0
    """
    analysis = HallucinationDetector.detect_hallucination_indicators(text)
    return analysis.hallucination_risk_score


