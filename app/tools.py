# Copyright 2026 Google LLC
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#     https://www.apache.org/licenses/LICENSE-2.0

import os
import re
from datetime import datetime, timedelta
from google.adk.tools import ToolContext

# Local simulated database for Selangor-based Hospital Kuala Makar (HKM)
FACILITIES = {
    "HKM": {
        "facility_name": "Hospital Kuala Makar",
        "district_name": "Kuala Makar",
        "base_population": 220000,
        "flood_vulnerability": 0.85,
        "medications": {
            "Amlodipine": {
                "base_daily_dose": 3500,
                "current_stock": 110000,
                "excess_capacity": 5000
            },
            "Perindopril": {
                "base_daily_dose": 2500,
                "current_stock": 73000,
                "excess_capacity": 0
            },
            "Simvastatin": {
                "base_daily_dose": 4000,
                "current_stock": 130000,
                "excess_capacity": 10000
            }
        }
    },
    "HKP": {
        "facility_name": "Hospital Kampung Pisang",
        "district_name": "Kuala Makar",
        "base_population": 180000,
        "flood_vulnerability": 0.65,
        "medications": {
            "Amlodipine": {
                "base_daily_dose": 3000,
                "current_stock": 115000,
                "excess_capacity": 25000
            },
            "Perindopril": {
                "base_daily_dose": 2000,
                "current_stock": 85000,
                "excess_capacity": 25000
            },
            "Simvastatin": {
                "base_daily_dose": 3500,
                "current_stock": 95000,
                "excess_capacity": 0
            }
        }
    }
}

def get_regional_baseline_metrics(district_name: str) -> dict:
    """Looks up geographic and meteorological baseline metrics for a district.

    Args:
        district_name: The name of the district to look up (e.g., 'Kuala Makar').

    Returns:
        A dictionary containing:
        - district_id: The identifier for the district (e.g., 'HKM').
        - base_population: Fictional baseline population.
        - flood_vulnerability: The historical vulnerability index (0.0 to 1.0).
    """
    clean_name = district_name.strip().lower()
    
    # Handle fictional Kuala Makar (masked HKM facility)
    if "makar" in clean_name or "kuala makar" in clean_name or "hkm" in clean_name:
        facility_info = FACILITIES["HKM"]
        return {
            "district_id": "HKM",
            "base_population": facility_info["base_population"],
            "flood_vulnerability": facility_info["flood_vulnerability"]
        }
    
    # Fallback to realistic default if district is not matched
    return {
        "district_id": "HKM",
        "base_population": 220000,
        "flood_vulnerability": 0.85
    }

def calculate_medication_demand_surge(
    district_id: str,
    flood_severity: float,
    forecast_horizon_days: int
) -> dict:
    """Calculates forecasted utilization spikes using an emulated TFT model.
    Provides p10 (conservative), p50 (expected), and p90 (extreme) demand quantiles.

    Args:
        district_id: The ID of the target district / facility (e.g., 'HKM').
        flood_severity: The dynamic severity score of the flood (range 0.0 to 1.0).
        forecast_horizon_days: The forecasting horizon in days.

    Returns:
        A dictionary containing estimated demand surges and quantile distributions for Amlodipine, Perindopril, and Simvastatin.
    """
    facility_id = district_id.strip().upper()
    if facility_id not in FACILITIES:
        facility_id = "HKM"
        
    facility_info = FACILITIES[facility_id]
    vulnerability = facility_info["flood_vulnerability"]
    
    # TFT emulated Quantile Surge Factors
    # p10 (conservative): 1.0 + (severity * vulnerability * 0.2)
    # p50 (expected): 1.0 + (severity * vulnerability * 0.5)
    # p90 (extreme): 1.0 + (severity * vulnerability * 0.8)
    surge_p10 = 1.0 + (flood_severity * vulnerability * 0.2)
    surge_p50 = 1.0 + (flood_severity * vulnerability * 0.5)
    surge_p90 = 1.0 + (flood_severity * vulnerability * 0.8)
    
    surge_results = {}
    for med_name, med_info in facility_info["medications"].items():
        base_daily = med_info["base_daily_dose"]
        
        daily_p10 = int(base_daily * surge_p10)
        daily_p50 = int(base_daily * surge_p50)
        daily_p90 = int(base_daily * surge_p90)
        
        surge_results[med_name] = {
            # Legacy parameters for backward compatibility
            "surge_factor": round(surge_p50, 4),
            "estimated_daily_doses_needed": daily_p50,
            "total_estimated_doses_needed": daily_p50 * forecast_horizon_days,
            
            # Multi-quantile TFT specifications
            "surge_factor_p10": round(surge_p10, 4),
            "estimated_daily_doses_needed_p10": daily_p10,
            "total_estimated_doses_needed_p10": daily_p10 * forecast_horizon_days,
            
            "surge_factor_p50": round(surge_p50, 4),
            "estimated_daily_doses_needed_p50": daily_p50,
            "total_estimated_doses_needed_p50": daily_p50 * forecast_horizon_days,
            
            "surge_factor_p90": round(surge_p90, 4),
            "estimated_daily_doses_needed_p90": daily_p90,
            "total_estimated_doses_needed_p90": daily_p90 * forecast_horizon_days,
        }
        
    return surge_results

def evaluate_stock_allocation(surge_data: dict, forecast_horizon_days: int) -> dict:
    """Evaluates inventory, relocations between facilities, and procurement triggers.
    Integrates the 1-month buffer stock rule (Required Target = Expected Demand + 30-day Buffer Stock).
    Supports both nested district-level data and legacy flat facility-level data.

    Args:
        surge_data: Output of calculate_medication_demand_surge (or dict of facility outputs).
        forecast_horizon_days: Number of forecast days.

    Returns:
        A dictionary containing stock evaluation parameters for each drug.
    """
    # 1. District-level nested mode
    if "HKM" in surge_data and "HKP" in surge_data:
        hkm_meds = FACILITIES["HKM"]["medications"]
        hkp_meds = FACILITIES["HKP"]["medications"]
        
        allocation_results = {
            "HKM": {},
            "HKP": {}
        }
        
        for med_name in ["Amlodipine", "Perindopril", "Simvastatin"]:
            hkm_stock = hkm_meds[med_name]["current_stock"]
            hkp_stock = hkp_meds[med_name]["current_stock"]
            
            hkm_expected_demand = surge_data["HKM"][med_name]["total_estimated_doses_needed_p50"]
            hkp_expected_demand = surge_data["HKP"][med_name]["total_estimated_doses_needed_p50"]
            
            # 1-month (30-day) buffer stock requirement
            hkm_buffer = hkm_meds[med_name]["base_daily_dose"] * 30
            hkp_buffer = hkp_meds[med_name]["base_daily_dose"] * 30
            
            # Required Target = Expected Demand + 30-day Buffer
            hkm_needed = hkm_expected_demand + hkm_buffer
            hkp_needed = hkp_expected_demand + hkp_buffer
            
            hkm_surge_factor = surge_data["HKM"][med_name]["surge_factor_p50"]
            hkp_surge_factor = surge_data["HKP"][med_name]["surge_factor_p50"]
            
            # Balances
            hkm_balance = hkm_stock - hkm_needed
            hkp_balance = hkp_stock - hkp_needed
            
            # Default allocations
            hkm_relocate = 0.0
            hkp_relocate = 0.0
            hkm_procure = 0.0
            hkp_procure = 0.0
            hkm_lend = 0.0
            hkp_lend = 0.0
            
            hkm_status = "Safe (Stock Sufficient)"
            hkp_status = "Safe (Stock Sufficient)"
            hkm_msg = f"Hospital Kuala Makar has sufficient local stock of {med_name} (Stock covers expected demand + 30-day buffer)."
            hkp_msg = f"Hospital Kampung Pisang has sufficient local stock of {med_name} (Stock covers expected demand + 30-day buffer)."
            
            # Relocation and Procurement rules
            if hkm_balance < 0 and hkp_balance >= 0:
                hkm_deficit = -hkm_balance
                # Relocate up to the partner's surplus (excess above required target)
                hkm_relocate = round(min(hkm_deficit, hkp_balance), 1)
                hkm_procure = round(max(0.0, hkm_deficit - hkm_relocate), 1)
                hkp_lend = hkm_relocate
                
                if hkm_relocate > 0 and hkm_procure == 0:
                    hkm_status = "Relocating"
                    hkm_msg = f"Deficit of {hkm_deficit:.1f} units (includes 30-day buffer) will be fully covered by stock relocation from Hospital Kampung Pisang."
                elif hkm_relocate > 0 and hkm_procure > 0:
                    hkm_status = "Relocation & Procurement"
                    hkm_msg = f"Deficit of {hkm_deficit:.1f} units. Relocating {hkm_relocate:.1f} from Hospital Kampung Pisang and procuring {hkm_procure:.1f} from Makar District Health Office."
                else:
                    hkm_status = "Procuring"
                    hkm_msg = f"Deficit of {hkm_deficit:.1f} units will be fully covered by emergency procurement from Makar District Health Office."
                
                if hkp_lend > 0:
                    hkp_status = "Lending to HKM"
                    hkp_msg = f"Hospital Kampung Pisang has excess stock and will lend {hkp_lend:.1f} units of {med_name} to Hospital Kuala Makar."
                    
            elif hkp_balance < 0 and hkm_balance >= 0:
                hkp_deficit = -hkp_balance
                hkp_relocate = round(min(hkp_deficit, hkm_balance), 1)
                hkp_procure = round(max(0.0, hkp_deficit - hkp_relocate), 1)
                hkm_lend = hkp_relocate
                
                if hkp_relocate > 0 and hkp_procure == 0:
                    hkp_status = "Relocating"
                    hkp_msg = f"Deficit of {hkp_deficit:.1f} units (includes 30-day buffer) will be fully covered by stock relocation from Hospital Kuala Makar."
                elif hkp_relocate > 0 and hkp_procure > 0:
                    hkp_status = "Relocation & Procurement"
                    hkp_msg = f"Deficit of {hkp_deficit:.1f} units. Relocating {hkp_relocate:.1f} from Hospital Kuala Makar and procuring {hkp_procure:.1f} from Makar District Health Office."
                else:
                    hkp_status = "Procuring"
                    hkp_msg = f"Deficit of {hkp_deficit:.1f} units will be fully covered by emergency procurement from Makar District Health Office."
                    
                if hkm_lend > 0:
                    hkm_status = "Lending to HKP"
                    hkm_msg = f"Hospital Kuala Makar has excess stock and will lend {hkm_lend:.1f} units of {med_name} to Hospital Kampung Pisang."
                    
            elif hkm_balance < 0 and hkp_balance < 0:
                hkm_deficit = -hkm_balance
                hkp_deficit = -hkp_balance
                hkm_procure = round(hkm_deficit, 1)
                hkp_procure = round(hkp_deficit, 1)
                
                hkm_status = "Procuring"
                hkm_msg = f"Deficit of {hkm_deficit:.1f} units will be fully covered by emergency procurement from Makar District Health Office."
                hkp_status = "Procuring"
                hkp_msg = f"Deficit of {hkp_deficit:.1f} units will be fully covered by emergency procurement from Makar District Health Office."
            
            allocation_results["HKM"][med_name] = {
                "current_stock": hkm_stock,
                "total_needed": hkm_needed,
                "deficit": round(max(0.0, -hkm_balance), 1),
                "relocation_qty": hkm_relocate,
                "procurement_qty": hkm_procure,
                "lend_qty": hkm_lend,
                "status": hkm_status,
                "message": hkm_msg
            }
            
            allocation_results["HKP"][med_name] = {
                "current_stock": hkp_stock,
                "total_needed": hkp_needed,
                "deficit": round(max(0.0, -hkp_balance), 1),
                "relocation_qty": hkp_relocate,
                "procurement_qty": hkp_procure,
                "lend_qty": hkp_lend,
                "status": hkp_status,
                "message": hkp_msg
            }
            
        return allocation_results

    # 2. Legacy flat single-facility mode (e.g. for existing tests)
    hkm_meds = FACILITIES["HKM"]["medications"]
    hkp_meds = FACILITIES["HKP"]["medications"]
    
    allocation_results = {}
    
    for med_name, surge_info in surge_data.items():
        hkm_stock = hkm_meds[med_name]["current_stock"]
        hkp_stock = hkp_meds[med_name]["current_stock"]
        
        expected_demand = surge_info["total_estimated_doses_needed_p50"]
        buffer_stock = hkm_meds[med_name]["base_daily_dose"] * 30
        
        # Required Target = Forecast Demand + 30-day Buffer
        total_needed = expected_demand + buffer_stock
        surge_factor = surge_info["surge_factor_p50"]
        is_baseline = (surge_factor == 1.0)
        
        if is_baseline:
            deficit = 0
            relocate_qty = 0
            procure_qty = 0
            lend_qty = 0
            status = "Safe (Stock Sufficient)"
            message = f"Hospital Kuala Makar baseline operations continue. No disaster impact detected. No emergency stock relocation required."
        else:
            deficit = round(max(0, total_needed - hkm_stock), 1)
            lend_qty = 0
            
            # Relocate from HKP surplus
            hkp_target = (hkp_meds[med_name]["base_daily_dose"] * surge_factor * forecast_horizon_days) + (hkp_meds[med_name]["base_daily_dose"] * 30)
            hkp_surplus = max(0, hkp_stock - hkp_target)
            
            if deficit > 0:
                relocate_qty = round(min(deficit, hkp_surplus), 1)
                procure_qty = round(max(0, deficit - relocate_qty), 1)
                if relocate_qty > 0 and procure_qty == 0:
                    status = "Relocating"
                    message = f"Deficit of {deficit} units will be fully covered by stock relocation from Hospital Kampung Pisang."
                elif relocate_qty > 0 and procure_qty > 0:
                    status = "Relocation & Procurement"
                    message = f"Deficit of {deficit} units. Relocating {relocate_qty} from Hospital Kampung Pisang and placing emergency order of {procure_qty} from Makar District Health Office."
                else:
                    status = "Procuring"
                    message = f"Deficit of {deficit} units will be fully covered by emergency procurement from Makar District Health Office."
            else:
                relocate_qty = 0
                procure_qty = 0
                
                # Check if HKM has excess stock to lend to HKP
                hkm_excess = round(max(0, hkm_stock - total_needed), 1)
                
                # Calculate HKP's demand and deficit
                hkp_needed = hkp_target
                hkp_deficit = round(max(0, hkp_needed - hkp_stock), 1)
                
                if hkm_excess > 0 and hkp_deficit > 0:
                    lend_qty = round(min(hkm_excess, hkp_deficit), 1)
                    status = "Lending to HKP"
                    message = f"Hospital Kuala Makar has excess stock and will lend {lend_qty} units of {med_name} to Hospital Kampung Pisang."
                else:
                    status = "Safe (Stock Sufficient)"
                    message = f"Hospital Kuala Makar has sufficient local stock of {med_name}."
            
        allocation_results[med_name] = {
            "current_stock": hkm_stock,
            "total_needed": total_needed,
            "deficit": deficit,
            "relocation_qty": relocate_qty,
            "procurement_qty": procure_qty,
            "lend_qty": lend_qty,
            "status": status,
            "message": message
        }
        
    return allocation_results

def validate_custom_allocation_plan(original_allocation: dict, overrides: dict) -> dict:
    """Validates if manager overrides satisfy logical safety rules.

    Checks:
    1. Overrides must be positive or zero numbers.
    2. Overrides cannot exceed the available stock of the donor facility.
    """
    for facility_id, meds in overrides.items():
        if facility_id not in ["HKM", "HKP"]:
            continue
            
        # The donor facility is the opposite facility
        donor_facility = "HKP" if facility_id == "HKM" else "HKM"
        donor_meds = FACILITIES[donor_facility]["medications"]
        
        for med_name, actions in meds.items():
            relocate_qty = actions.get("relocation_qty", 0.0)
            procure_qty = actions.get("procurement_qty", 0.0)
            
            try:
                relocate_qty = float(relocate_qty)
                procure_qty = float(procure_qty)
            except (ValueError, TypeError):
                return {
                    "passed": False,
                    "reason": f"Value error: {med_name} allocations must be valid numbers."
                }
                
            if relocate_qty < 0 or procure_qty < 0:
                return {
                    "passed": False,
                    "reason": f"Negative value error: {med_name} in {facility_id} cannot have negative quantities."
                }
                
            # Verify relocate amount is within donor surplus stock (to prevent creating donor deficits)
            donor_alloc = original_allocation.get(donor_facility, {}).get(med_name, {})
            current_donor_stock = donor_alloc.get("current_stock", 0.0)
            donor_needed = donor_alloc.get("total_needed", 0.0)
            donor_surplus = max(0.0, current_donor_stock - donor_needed)
            
            if relocate_qty > donor_surplus:
                return {
                    "passed": False,
                    "reason": f"Relocation error: Requested relocation of {relocate_qty:.1f} units of {med_name} exceeds the available surplus of donor facility {donor_facility} (Available surplus to lend: {donor_surplus:.1f})."
                }
                
    return {
        "passed": True,
        "reason": "All manual overrides comply with facility inventory limits."
    }

def generate_daily_demand_curves(facility_id: str, severity: float) -> dict:
    """Generates 14 days of actual history and 30 days of p10/p50/p90 daily forecasting bounds.

    Returns:
        A dictionary for each medication containing:
        - dates: list of 44 formatted date strings
        - history: list of 14 actual daily values, then 30 None values
        - p10: list of 14 None values, then 30 forecast values
        - p50: list of 14 None values, then 30 forecast values
        - p90: list of 14 None values, then 30 forecast values
    """
    facility_info = FACILITIES.get(facility_id, FACILITIES["HKM"])
    vulnerability = facility_info["flood_vulnerability"]
    
    # Anchor current date at 29 Jun 2026
    current_day = datetime(2026, 6, 29)
    
    # Generate 44 days timeline (14 days past, 30 days future)
    dates = []
    for i in range(14):
        date_obj = current_day - timedelta(days=14 - i)
        dates.append(date_obj.strftime("%d %b %Y"))
    for i in range(30):
        date_obj = current_day + timedelta(days=i)
        dates.append(date_obj.strftime("%d %b %Y"))
        
    curves = {}
    for med_name, med_info in facility_info["medications"].items():
        base_daily = med_info["base_daily_dose"]
        
        # 1. 14 Days History
        history = []
        for d in range(14):
            # Deterministic variation
            noise = (d * 17) % 200 - 100
            history.append(int(base_daily + noise))
        # Fill rest with None
        history += [None] * 30
        
        # 2. 30 Days Forecast Curves
        p10 = [None] * 14
        p50 = [None] * 14
        p90 = [None] * 14
        
        for t in range(1, 31):
            # Surge multiplier peaks around day 7, then recedes by day 30
            if t <= 7:
                factor = (t / 7.0) * 0.5
            else:
                factor = max(0.0, 0.5 * (1.0 - (t - 7.0) / 23.0))
                
            # Base surge
            surge_p50 = 1.0 + (severity * vulnerability * factor)
            surge_p10 = 1.0 + (severity * vulnerability * factor * 0.4)
            surge_p90 = 1.0 + (severity * vulnerability * factor * 1.6)
            
            p10.append(int(base_daily * surge_p10))
            p50.append(int(base_daily * surge_p50))
            p90.append(int(base_daily * surge_p90))
            
        curves[med_name] = {
            "dates": dates,
            "history": history,
            "p10": p10,
            "p50": p50,
            "p90": p90
        }
        
    return curves

def search_disaster_guidelines(query: str) -> str:
    """Searches local RAG directory (supporting md, txt, and pdf) for SOP guidelines.

    Args:
        query: The user prompt or agent question to find guidelines context for.

    Returns:
        Relevant paragraphs from the guidelines.
    """
    import pypdf
    rag_dir = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "rag_docs")
    if not os.path.exists(rag_dir):
        return "Makar District Health Office (MDHO) Disaster Guidelines: directory not found."
        
    snippets = []
    
    try:
        for filename in sorted(os.listdir(rag_dir)):
            filepath = os.path.join(rag_dir, filename)
            if not os.path.isfile(filepath):
                continue
                
            file_text = ""
            ext = os.path.splitext(filename)[1].lower()
            
            if ext in [".md", ".txt"]:
                with open(filepath, "r", encoding="utf-8") as f:
                    file_text = f.read()
            elif ext == ".pdf":
                cache_path = filepath + ".txt"
                if os.path.exists(cache_path):
                    with open(cache_path, "r", encoding="utf-8") as f:
                        file_text = f.read()
                else:
                    reader = pypdf.PdfReader(filepath)
                    text_list = []
                    for page in reader.pages:
                        text_list.append(page.extract_text() or "")
                    file_text = "\n".join(text_list)
                    try:
                        with open(cache_path, "w", encoding="utf-8") as f:
                            f.write(file_text)
                    except Exception:
                        pass
                
            if not file_text.strip():
                continue
                
            # Split sections by header markers or double newlines
            sections = file_text.split("##") if ext == ".md" else file_text.split("\n\n")
            query_words = set(re.findall(r"\w+", query.lower()))
            if not query_words:
                continue
                
            for sec in sections:
                if not sec.strip():
                    continue
                sec_words = set(re.findall(r"\w+", sec.lower()))
                intersection = query_words.intersection(sec_words)
                if intersection:
                    snippets.append((len(intersection), sec.strip()))
                    
        # Sort by match count descending
        snippets.sort(key=lambda x: x[0], reverse=True)
        
        if snippets:
            return "\n\n---\n\n".join([item[1] for item in snippets[:2]])
        return "No direct matching sections found in Makar District Health Office (MDHO) Guidelines. Refer to standard MDHO SOPs."
    except Exception as e:
        return f"Error reading guidelines: {str(e)}"
