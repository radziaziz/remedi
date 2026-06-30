# Copyright 2026 Google LLC
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#     https://www.apache.org/licenses/LICENSE-2.0

import pytest
import httpx
import time

def test_backend_flow():
    # Wait for server to be ready
    url = "http://localhost:8000"
    
    # 1. Start session
    payload = {
        "alert": "Severe flooding reported upstream in Gombak/Kuala Makar district. Hospital Makar needs immediate forecasting."
    }
    response = httpx.post(f"{url}/api/start", json=payload, timeout=30.0)
    assert response.status_code == 200
    res_data = response.json()
    
    assert "session_id" in res_data
    session_id = res_data["session_id"]
    assert res_data["status"] == "waiting_hitl"
    assert "Hospital Kuala Makar" in res_data["brief_draft"]
    
    # Check state data
    state = res_data["state"]
    assert state["district_id"] == "HKM"
    assert state["base_population"] == 220000
    assert state["flood_vulnerability"] == 0.85
    assert "Amlodipine" in state["medication_surge"]
    
    # 2. Modify request
    modify_payload = {
        "session_id": session_id,
        "command": "/modify Adjust severity to 0.9 and increase horizon to 10 days"
    }
    modify_response = httpx.post(f"{url}/api/hitl", json=modify_payload, timeout=30.0)
    assert modify_response.status_code == 200
    modify_res = modify_response.json()
    
    assert modify_res["status"] == "waiting_hitl"
    # Verify updated state
    updated_state = modify_res["state"]
    assert updated_state["severity"] == 0.9
    assert updated_state["forecast_days"] == 10
    
    # Check that Amlodipine daily doses reflect the new surge
    # vulnerability = 0.85, severity = 0.9
    # surge_factor = 1.0 + (0.9 * 0.85 * 0.5) = 1.3825
    # base = 3500, daily = 3500 * 1.3825 = 4838, total = 4838 * 10 = 48380
    assert updated_state["medication_surge"]["Amlodipine"]["surge_factor"] == 1.3825
    assert updated_state["medication_surge"]["Amlodipine"]["estimated_daily_doses_needed"] == 4838
    assert updated_state["medication_surge"]["Amlodipine"]["total_estimated_doses_needed"] == 48380

    # 3. Approve plan
    approve_payload = {
        "session_id": session_id,
        "command": "/approve"
    }
    approve_response = httpx.post(f"{url}/api/hitl", json=approve_payload, timeout=30.0)
    assert approve_response.status_code == 200
    approve_res = approve_response.json()
    
    assert approve_res["status"] == "completed"
    assert "Disaster Pharmacy Manager Digital Sign-off: APPROVED" in approve_res["final_brief"]
    assert approve_res["state"]["approved"] is True
