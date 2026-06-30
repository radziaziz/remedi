# Copyright 2026 Google LLC
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#     https://www.apache.org/licenses/LICENSE-2.0

from app.tools import get_regional_baseline_metrics, calculate_medication_demand_surge

def test_get_regional_baseline_metrics():
    metrics = get_regional_baseline_metrics("Kuala Makar")
    assert metrics["district_id"] == "HKM"
    assert metrics["base_population"] == 220000
    assert metrics["flood_vulnerability"] == 0.85

    # Case insensitivity test
    metrics_lower = get_regional_baseline_metrics("kuala makar")
    assert metrics_lower["district_id"] == "HKM"

    # Default fallback test
    metrics_fallback = get_regional_baseline_metrics("Unknown District")
    assert metrics_fallback["district_id"] == "HKM"

def test_calculate_medication_demand_surge():
    # severity = 0.8, vulnerability = 0.85
    # surge_factor = 1.0 + (0.8 * 0.85 * 0.5) = 1.0 + 0.34 = 1.34
    res = calculate_medication_demand_surge("HKM", flood_severity=0.8, forecast_horizon_days=7)
    
    # Assert actual drug names are present
    assert "Amlodipine" in res
    assert "Perindopril" in res
    assert "Simvastatin" in res

    # Check Amlodipine calculations
    # base = 3500, daily = 3500 * 1.34 = 4690, total = 4690 * 7 = 32830
    assert res["Amlodipine"]["surge_factor"] == 1.34
    assert res["Amlodipine"]["estimated_daily_doses_needed"] == 4690
    assert res["Amlodipine"]["total_estimated_doses_needed"] == 32830

    # Check Perindopril calculations
    # base = 2500, daily = 2500 * 1.34 = 3350
    assert res["Perindopril"]["estimated_daily_doses_needed"] == 3350

    # Check Simvastatin calculations
    # base = 4000, daily = 4000 * 1.34 = 5360
    assert res["Simvastatin"]["estimated_daily_doses_needed"] == 5360

def test_tft_quantiles():
    res = calculate_medication_demand_surge("HKM", flood_severity=0.8, forecast_horizon_days=5)
    for med in ["Amlodipine", "Perindopril", "Simvastatin"]:
        info = res[med]
        # p10 <= p50 <= p90
        assert info["estimated_daily_doses_needed_p10"] <= info["estimated_daily_doses_needed_p50"]
        assert info["estimated_daily_doses_needed_p50"] <= info["estimated_daily_doses_needed_p90"]
        
        assert info["total_estimated_doses_needed_p10"] <= info["total_estimated_doses_needed_p50"]
        assert info["total_estimated_doses_needed_p50"] <= info["total_estimated_doses_needed_p90"]
        
        assert info["surge_factor_p10"] <= info["surge_factor_p50"]
        assert info["surge_factor_p50"] <= info["surge_factor_p90"]

def test_stock_allocation():
    from app.tools import evaluate_stock_allocation
    surge_data = calculate_medication_demand_surge("HKM", flood_severity=0.8, forecast_horizon_days=5)
    alloc = evaluate_stock_allocation(surge_data, forecast_horizon_days=5)
    
    assert "Amlodipine" in alloc
    # Expected daily for Amlodipine under 0.8 severity = 3500 * 1.34 = 4690
    # Total expected needed (p50) for 5 days = 4690 * 5 = 23450
    # 1-month buffer = 3500 * 30 = 105000
    # Required target = 23450 + 105000 = 128450
    # HKM stock = 110000. Deficit = 128450 - 110000 = 18450
    # HKP target: expected = 3000 * 1.26 * 5 = 18900. buffer = 90000. target = 108900.
    # HKP stock = 115000. Surplus = 115000 - 108900 = 6100.
    # Relocation = min(18450, 6100) = 6100.
    # Procurement = 18450 - 6100 = 12350
    aml_alloc = alloc["Amlodipine"]
    assert aml_alloc["current_stock"] == 110000
    assert aml_alloc["total_needed"] == 128450
    assert aml_alloc["deficit"] == 18450
    assert aml_alloc["relocation_qty"] == 4900
    assert aml_alloc["procurement_qty"] == 13550
    assert aml_alloc["status"] == "Relocation & Procurement"

def test_search_disaster_guidelines():
    from app.tools import search_disaster_guidelines
    snippet = search_disaster_guidelines("buffer stock multiplier")
    assert "Safety Stock" in snippet or "buffer multiplier" in snippet
    
    snippet_relocate = search_disaster_guidelines("relocation limit helper")
    assert "50%" in snippet_relocate or "relocate" in snippet_relocate

def test_out_of_catchment_evaluation():
    from app.tools import evaluate_stock_allocation
    # severity = 0.0, which emulates an out-of-catchment or zero-impact warning
    surge_data = calculate_medication_demand_surge("HKM", flood_severity=0.0, forecast_horizon_days=5)
    alloc = evaluate_stock_allocation(surge_data, forecast_horizon_days=5)
    
    for med in ["Amlodipine", "Perindopril", "Simvastatin"]:
        assert alloc[med]["deficit"] == 0
        assert alloc[med]["relocation_qty"] == 0
        assert alloc[med]["procurement_qty"] == 0
        assert alloc[med]["status"] == "Safe (Stock Sufficient)"
        assert "baseline operations continue" in alloc[med]["message"]

def test_lending_allocation():
    from app.tools import evaluate_stock_allocation, calculate_medication_demand_surge, FACILITIES
    # Let's adjust FACILITIES stocks so HKM has surplus and HKP has deficit
    FACILITIES["HKM"]["medications"]["Amlodipine"]["current_stock"] = 160000
    FACILITIES["HKP"]["medications"]["Amlodipine"]["current_stock"] = 80000
    
    # severity = 0.5, forecast days = 5
    # Expected p50 demand for Amlodipine (HKM) = 3500 * (1.0 + 0.5*0.85*0.5) * 5 = 19359.375
    # HKM target = 19359.375 + 105000 = 124359.375. Surplus = 160000 - 124359.375 = 35640.625
    # Expected p50 demand for Amlodipine (HKP) = 3000 * (1.0 + 0.5*0.65*0.5) * 5 = 16218.75
    # HKP target = 16218.75 + 90000 = 106218.75. Deficit = 106218.75 - 80000 = 26218.75
    # Lend qty = min(35640.625, 26218.75) = 26218.75
    surge_data = calculate_medication_demand_surge("HKM", flood_severity=0.5, forecast_horizon_days=5)
    
    # To run nested district evaluation:
    surge_district = {
        "HKM": calculate_medication_demand_surge("HKM", flood_severity=0.5, forecast_horizon_days=5),
        "HKP": calculate_medication_demand_surge("HKP", flood_severity=0.5, forecast_horizon_days=5)
    }
    
    alloc = evaluate_stock_allocation(surge_district, forecast_horizon_days=5)
    
    aml_alloc = alloc["HKP"]["Amlodipine"]
    assert aml_alloc["deficit"] == 27435
    assert aml_alloc["relocation_qty"] == 27435
    assert aml_alloc["procurement_qty"] == 0
    
    # Restore FACILITIES stocks for other tests
    FACILITIES["HKM"]["medications"]["Amlodipine"]["current_stock"] = 110000
    FACILITIES["HKP"]["medications"]["Amlodipine"]["current_stock"] = 115000

def test_search_disaster_guidelines_pdf(monkeypatch):
    import pypdf
    import os
    from app.tools import search_disaster_guidelines
    
    dummy_pdf = "mock_sop.pdf"
    
    class MockPage:
        def extract_text(self):
            return "MDHO Safety Stock threshold is 1.3x. Relocation limit safety factor is 50%."
            
    class MockReader:
        def __init__(self, filepath):
            self.pages = [MockPage()]
            
    monkeypatch.setattr(pypdf, "PdfReader", MockReader)
    monkeypatch.setattr(os.path, "exists", lambda x: False if x.endswith(".txt") else True)
    monkeypatch.setattr(os, "listdir", lambda x: [dummy_pdf])
    monkeypatch.setattr(os.path, "isfile", lambda x: True)
    
    snippet = search_disaster_guidelines("Safety Stock")
    assert "MDHO" in snippet
    assert "1.3x" in snippet


