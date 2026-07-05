"""
MITRE ATT&CK Data Fetcher.

Fetches real detection strategies and analytics from the official MITRE ATT&CK STIX data.
"""
import json
import logging
import re
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional

import requests

from app.config import settings

logger = logging.getLogger(__name__)

# Official MITRE ATT&CK STIX data URLs
ENTERPRISE_ATTACK_URL = "https://raw.githubusercontent.com/mitre-attack/attack-stix-data/master/enterprise-attack/enterprise-attack.json"


def fetch_mitre_attack_data() -> Dict[str, Any]:
    """
    Fetch the latest MITRE ATT&CK Enterprise data from GitHub.
    
    Returns:
        STIX bundle dictionary
    """
    logger.info(f"Fetching MITRE ATT&CK data from {ENTERPRISE_ATTACK_URL}")
    
    response = requests.get(ENTERPRISE_ATTACK_URL, timeout=60)
    response.raise_for_status()
    
    data = response.json()
    logger.info(f"Fetched {len(data.get('objects', []))} STIX objects")
    
    return data


def extract_detection_strategies(stix_data: Dict[str, Any]) -> List[Dict[str, Any]]:
    """
    Extract detection strategies from STIX data.
    
    Args:
        stix_data: STIX bundle dictionary
        
    Returns:
        List of detection strategy dictionaries
    """
    strategies = []
    analytics_by_id = {}
    technique_names = {}
    relationships = []
    
    objects = stix_data.get("objects", [])
    
    # First pass: collect analytics, techniques, and relationships
    for obj in objects:
        obj_type = obj.get("type")
        
        if obj_type == "x-mitre-analytic":
            analytic_id = obj.get("id")
            analytics_by_id[analytic_id] = obj
            
        elif obj_type == "attack-pattern":
            # This is a technique
            ext_refs = obj.get("external_references", [])
            for ref in ext_refs:
                if ref.get("source_name") == "mitre-attack":
                    technique_id = ref.get("external_id")
                    technique_names[obj.get("id")] = {
                        "id": technique_id,
                        "name": obj.get("name"),
                        "stix_id": obj.get("id")
                    }
                    break
                    
        elif obj_type == "relationship":
            relationships.append(obj)
    
    # Build technique ID lookup by STIX ID
    stix_to_technique = {v["stix_id"]: v["id"] for v in technique_names.values()}
    
    # Second pass: extract detection strategies
    for obj in objects:
        if obj.get("type") != "x-mitre-detection-strategy":
            continue
            
        # Get external ID (DET####)
        external_id = None
        url = None
        ext_refs = obj.get("external_references", [])
        for ref in ext_refs:
            if ref.get("source_name") == "mitre-attack":
                external_id = ref.get("external_id")
                url = ref.get("url")
                break
        
        if not external_id:
            continue
        
        # Find related techniques via relationships
        strategy_stix_id = obj.get("id")
        related_techniques = []
        related_analytics = []
        
        for rel in relationships:
            if rel.get("source_ref") == strategy_stix_id:
                target_ref = rel.get("target_ref")
                rel_type = rel.get("relationship_type")
                
                if rel_type == "detects" and target_ref in stix_to_technique:
                    related_techniques.append(stix_to_technique[target_ref])
                elif "analytic" in str(target_ref).lower():
                    related_analytics.append(target_ref)
                    
            elif rel.get("target_ref") == strategy_stix_id:
                source_ref = rel.get("source_ref")
                rel_type = rel.get("relationship_type")
                
                if source_ref in stix_to_technique:
                    related_techniques.append(stix_to_technique[source_ref])
        
        # Get platforms
        platforms = obj.get("x_mitre_platforms", [])
        
        # Get tactics from kill chain phases
        tactics = []
        for phase in obj.get("kill_chain_phases", []):
            if phase.get("kill_chain_name") == "mitre-attack":
                tactic = phase.get("phase_name", "").replace("-", " ").title()
                tactics.append(tactic)
        
        # Build analytics list
        analytics = []
        analytic_refs = obj.get("x_mitre_analytics", [])
        for analytic_ref in analytic_refs:
            if isinstance(analytic_ref, str) and analytic_ref in analytics_by_id:
                analytic_obj = analytics_by_id[analytic_ref]
                analytics.append({
                    "analytic_id": analytic_obj.get("external_references", [{}])[0].get("external_id"),
                    "platform": ", ".join(analytic_obj.get("x_mitre_platforms", [])),
                    "description": analytic_obj.get("description", ""),
                    "data_components": analytic_obj.get("x_mitre_data_components", [])
                })
        
        strategy = {
            "id": external_id,
            "name": obj.get("name", ""),
            "description": obj.get("description", ""),
            "techniques": list(set(related_techniques)),
            "tactics": tactics,
            "platforms": platforms,
            "analytics": analytics,
            "domain": "Enterprise",
            "url": url or f"https://attack.mitre.org/detectionstrategies/{external_id}"
        }
        
        strategies.append(strategy)
        logger.debug(f"Extracted strategy: {external_id} - {obj.get('name')}")
    
    logger.info(f"Extracted {len(strategies)} detection strategies")
    return strategies


def update_detection_strategies_cache() -> int:
    """
    Fetch real MITRE ATT&CK detection strategies and update the cache file.
    
    Returns:
        Number of strategies fetched
    """
    try:
        # Fetch STIX data
        stix_data = fetch_mitre_attack_data()
        
        # Extract detection strategies
        strategies = extract_detection_strategies(stix_data)
        
        # Save to cache file
        cache_file = Path(settings.data_dir) / "detection_strategies_cache.json"
        cache_data = {
            "strategies": strategies,
            "last_updated": datetime.utcnow().isoformat(),
            "source": ENTERPRISE_ATTACK_URL,
            "_note": "Real MITRE ATT&CK detection strategies fetched from official STIX data"
        }
        
        with open(cache_file, 'w', encoding='utf-8') as f:
            json.dump(cache_data, f, indent=2, ensure_ascii=False)
        
        logger.info(f"Saved {len(strategies)} detection strategies to {cache_file}")
        return len(strategies)
        
    except Exception as e:
        logger.error(f"Failed to update detection strategies cache: {e}")
        raise


def get_technique_to_detection_mapping(stix_data: Dict[str, Any]) -> Dict[str, List[str]]:
    """
    Build a mapping from technique IDs to detection strategy IDs.
    
    Args:
        stix_data: STIX bundle dictionary
        
    Returns:
        Dictionary mapping technique_id -> list of detection strategy IDs
    """
    mapping = {}
    
    objects = stix_data.get("objects", [])
    
    # Build lookups
    stix_to_technique = {}
    stix_to_strategy = {}
    
    for obj in objects:
        obj_type = obj.get("type")
        ext_refs = obj.get("external_references", [])
        
        if obj_type == "attack-pattern":
            for ref in ext_refs:
                if ref.get("source_name") == "mitre-attack":
                    stix_to_technique[obj.get("id")] = ref.get("external_id")
                    break
                    
        elif obj_type == "x-mitre-detection-strategy":
            for ref in ext_refs:
                if ref.get("source_name") == "mitre-attack":
                    stix_to_strategy[obj.get("id")] = ref.get("external_id")
                    break
    
    # Process relationships
    for obj in objects:
        if obj.get("type") != "relationship":
            continue
            
        rel_type = obj.get("relationship_type")
        source_ref = obj.get("source_ref")
        target_ref = obj.get("target_ref")
        
        # Detection strategy detects technique
        if rel_type == "detects":
            if source_ref in stix_to_strategy and target_ref in stix_to_technique:
                technique_id = stix_to_technique[target_ref]
                strategy_id = stix_to_strategy[source_ref]
                
                if technique_id not in mapping:
                    mapping[technique_id] = []
                if strategy_id not in mapping[technique_id]:
                    mapping[technique_id].append(strategy_id)
    
    return mapping


if __name__ == "__main__":
    # Run as script to update cache
    logging.basicConfig(level=logging.INFO)
    count = update_detection_strategies_cache()
    print(f"Updated cache with {count} detection strategies")


