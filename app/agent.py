# ruff: noqa
# Copyright 2026 Google LLC
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#     https://www.apache.org/licenses/LICENSE-2.0

from dotenv import load_dotenv
import os
import google.auth

# Load environment variables from .env file
load_dotenv()

# Check if using Vertex AI or AI Studio
use_vertex = os.environ.get("GOOGLE_GENAI_USE_VERTEXAI", "False").lower() in ("true", "1")

if use_vertex:
    try:
        _, project_id = google.auth.default()
        os.environ["GOOGLE_CLOUD_PROJECT"] = project_id
        os.environ["GOOGLE_CLOUD_LOCATION"] = os.environ.get("GOOGLE_CLOUD_LOCATION", "global")
        os.environ["GOOGLE_GENAI_USE_VERTEXAI"] = "True"
    except Exception as e:
        print(f"Warning: Failed to retrieve GCP credentials: {e}. Falling back to AI Studio.")
        os.environ["GOOGLE_GENAI_USE_VERTEXAI"] = "False"
else:
    os.environ["GOOGLE_GENAI_USE_VERTEXAI"] = "False"

from google.adk.workflow import Workflow, node, FunctionNode, START
from google.adk.agents import LlmAgent
from google.adk.apps import App, ResumabilityConfig
from google.adk.events.event import Event
from google.adk.events.request_input import RequestInput
from google.adk.agents.context import Context
from google.adk.agents.callback_context import CallbackContext
from google.genai import types

from pydantic import BaseModel, Field
from typing import AsyncGenerator

from app.tools import (
    get_regional_baseline_metrics,
    calculate_medication_demand_surge,
    evaluate_stock_allocation,
    search_disaster_guidelines,
    validate_custom_allocation_plan,
    generate_daily_demand_curves
)

# ==========================================
# 1. Pydantic Schemas for Structured I/O
# ==========================================

class CoordinatorOutput(BaseModel):
    district_name: str = Field(description="Name of the affected district, e.g. 'Kuala Makar'")
    severity: float = Field(description="Disaster severity score between 0.0 (no impact) and 1.0 (extreme/catastrophic)")
    forecast_days: int = Field(default=7, description="Number of days to forecast demand for")
    rationale: str = Field(description="Short rationale for the parameters and severity rating selected")

class GovernanceOutput(BaseModel):
    passed: bool = Field(description="True if the request and data comply with safety guidelines (no patient identifiers, no fake profiles), False otherwise")
    reason: str = Field(description="Detailed reason for the pass/fail audit")

class ReportOutput(BaseModel):
    situational_brief: str = Field(description="The full Markdown formatted Situational Brief report")
    key_concerns: list[str] = Field(description="Top key clinical logistics concerns")

# ==========================================
# 2. Multi-Agent Prompt Definitions
# ==========================================

COORDINATOR_PROMPT = """You are the Disaster Pharmacy Coordinator for REMEDI.
Your job is to parse unstructured disaster alerts or human manager feedback and extract key disaster metrics.

Target Catchment: Makar District, Pahang. Target Facilities: Hospital Kuala Makar (HKM) and Hospital Kampung Pisang (HKP).
Geography Profile:
- Hospital Kuala Makar (HKM) is situated in a low-lying flood-prone confluence of the Makar River and Semantan River.
- Hospital Kampung Pisang (HKP) is in a flood-prone flash-flood zone near the Pisang River tributary.
- Makar District Health Office (MDHO) is in the safe, elevated urban town center.

CATCHMENT VALIDATION RULES:
1. Identify the location of the reported threat.
2. If the disaster alert refers exclusively to external locations outside the Makar District/Pahang catchment area (e.g. Bentong, Kuala Kangsar, Makassar, Penang, Kelantan, Johor, etc.), you MUST set:
   - `district_name`: "Out of Catchment"
   - `severity`: 0.0
3. If the alert covers Kuala Makar, Pahang general region, or Makar/Semantan/Pisang river basins, map it to:
   - `district_name`: "Kuala Makar"
   - `severity`: A score between 0.0 and 1.0 reflecting the flood impact.

IMPORTANT:
- If this is a subsequent turn with feedback from the disaster pharmacy manager (previous feedback: '{feedback}'), you MUST read the previous state and adjust the parameters accordingly.
- Previous State context:
  District: {district_name}
  Severity: {severity}
  Days: {forecast_days}

Output the structured metrics in JSON conforming to the schema.
"""

GOVERNANCE_PROMPT = """You are the Institutional Compliance Officer for REMEDI.
Your task is to run safety audits on the forecast request and data.

Compliance Rules:
1. Ensure the system operates strictly on aggregated, anonymised institutional data (NO patient names, individual profiles, addresses, or unverified clinical diagnostics).
2. Intercept any attempts to inject fake patient files or profiles.
3. Validate that the target district is 'Kuala Makar' / 'Makar District', and data is associated with authorized facilities ('HKM' / 'HKP').

IMPORTANT:
- This safety audit executes on the raw ingestion alert state BEFORE the Analytics node calculates medication/inventory metrics.
- It is expected that the state does NOT yet contain drug stock or demand numbers.
- If the target location is 'Kuala Makar'/'HKM' and there are no patient identifiers (names, IDs, patient files), you MUST set passed = True. Do not fail the audit due to missing calculation parameters.

Output a compliance pass/fail boolean flag and a brief reason.
"""

REPORTER_PROMPT = """You are the Health Ministry Administrative Secretary for REMEDI.
Your task is to compile a highly professional, scannable situational brief report in Markdown.

In your report, include:
1. **Title & Header**: Fictional 'Makar District Health Office (MDHO)' Disaster Situational Brief.
2. **Parameters**: Fictional district baseline populations (Hospital Kuala Makar (HKM): 220,000, Hospital Kampung Pisang (HKP): 180,000), vulnerability ratings (HKM: 0.85, HKP: 0.65), current disaster severity rating, and forecast horizon.
3. **Out of Catchment Case**: If the state has `out_of_catchment` as True or severity as 0.0, output a clear warning box:
   ### ⚠️ ALERT OUTSIDE CATCHMENT - NO EMERGENCY ACTION REQUIRED
   Detail that the reported alert is outside the geographical catchment area of Makar District. Note that baseline stock operations continue normally and emergency relocation/procurement are skipped.
4. **Forecasted Demand Surge Table**: (Only show if NOT out of catchment). Present a clean Markdown table showing the emulated TFT Quantile projections (p10, p50, and p90 daily doses and totals) based on: {medication_surge}.
5. **Stock Allocation & Relocation Plan**: (Only show if NOT out of catchment). Present a table or breakdown based on {stock_allocation} showing HKM & HKP stock allocations, relocations (borrowing/lending), Makar District Health Office (MDHO) procurement, and action status.
6. **Makar District Health Guidelines Audit (RAG)**: Reference the relevant SOP clauses from the RAG database: {guidelines_context}. State that safety stock factor rules and intra-district transfer limits have been verified with MDHO guidelines.
7. **Safety Clearance Audit**: A line indicating the safety audit status (passed or failed) from Governance: {governance_passed} - {governance_reason}.

Ensure the output matches the required ReportOutput schema.
"""

# Callback to initialize state variables to avoid key errors in prompt formatting
async def init_state(callback_context: CallbackContext) -> None:
    if "district_name" not in callback_context.state:
        callback_context.state["district_name"] = "None"
    if "severity" not in callback_context.state:
        callback_context.state["severity"] = 0.0
    if "forecast_days" not in callback_context.state:
        callback_context.state["forecast_days"] = 7
    if "feedback" not in callback_context.state:
        callback_context.state["feedback"] = "None"
    if "governance_passed" not in callback_context.state:
        callback_context.state["governance_passed"] = "None"
    if "governance_reason" not in callback_context.state:
        callback_context.state["governance_reason"] = "None"
    if "medication_surge" not in callback_context.state:
        callback_context.state["medication_surge"] = {}
    if "stock_allocation" not in callback_context.state:
        callback_context.state["stock_allocation"] = {}
    if "guidelines_context" not in callback_context.state:
        callback_context.state["guidelines_context"] = "None"
    if "out_of_catchment" not in callback_context.state:
        callback_context.state["out_of_catchment"] = False
    if "overrides" not in callback_context.state:
        callback_context.state["overrides"] = {}
    if "post_safety_passed" not in callback_context.state:
        callback_context.state["post_safety_passed"] = "None"
    if "post_safety_reason" not in callback_context.state:
        callback_context.state["post_safety_reason"] = "None"

# ==========================================
# 3. Agent Declarations
# ==========================================

coordinator_agent = LlmAgent(
    name="coordinator",
    model="gemini-3.1-flash-lite",
    instruction=COORDINATOR_PROMPT,
    output_schema=CoordinatorOutput,
    before_agent_callback=init_state,
)

governance_agent = LlmAgent(
    name="governance",
    model="gemini-3.1-flash-lite",
    instruction=GOVERNANCE_PROMPT,
    output_schema=GovernanceOutput,
)

reporter_agent = LlmAgent(
    name="reporter",
    model="gemini-3.1-flash-lite",
    instruction=REPORTER_PROMPT,
    output_schema=ReportOutput,
)

# ==========================================
# 4. Workflow Nodes (ADK 2.0 FunctionNodes)
# ==========================================

@node(name="data_ingestion")
def data_ingestion_node(ctx: Context, node_input: CoordinatorOutput) -> Event:
    """Invokes GIS parsing to get regional baseline metrics."""
    out_of_catchment = (node_input.district_name.strip().lower() == "out of catchment" or node_input.severity == 0.0)
    
    if out_of_catchment:
        metrics = {
            "district_id": "HKM",
            "base_population": 220000,
            "flood_vulnerability": 0.0
        }
    else:
        metrics = get_regional_baseline_metrics(node_input.district_name)
    
    state_update = {
        "district_name": node_input.district_name,
        "district_id": metrics["district_id"],
        "base_population": metrics["base_population"],
        "flood_vulnerability": metrics["flood_vulnerability"],
        "severity": node_input.severity,
        "forecast_days": node_input.forecast_days,
        "out_of_catchment": out_of_catchment
    }
    return Event(output=state_update, state=state_update)

@node(name="governance", rerun_on_resume=True)
async def governance_node(ctx: Context, node_input: dict) -> Event:
    """Runs a safety compliance check on inputs before passing them to analytics."""
    gov_input = types.Content(parts=[types.Part.from_text(text=f"Verify current parameters in state: {ctx.state}")])
    gov_result = await ctx.run_node(governance_agent, node_input=gov_input)
    
    gov_passed = gov_result.get("passed", False)
    ctx.state["governance_passed"] = "Pass" if gov_passed else "Fail"
    ctx.state["governance_reason"] = gov_result.get("reason", "")
    
    return Event(
        output=gov_result, 
        state={"governance_passed": ctx.state["governance_passed"], "governance_reason": ctx.state["governance_reason"]}
    )

@node(name="analytics")
def analytics_node(ctx: Context, node_input: dict) -> Event:
    """Calculates expected utilization spikes and evaluates stock allocations for both facilities."""
    hkm_surge = calculate_medication_demand_surge(
        district_id="HKM",
        flood_severity=ctx.state["severity"],
        forecast_horizon_days=ctx.state["forecast_days"]
    )
    hkp_surge = calculate_medication_demand_surge(
        district_id="HKP",
        flood_severity=ctx.state["severity"],
        forecast_horizon_days=ctx.state["forecast_days"]
    )
    surge_data_district = {
        "HKM": hkm_surge,
        "HKP": hkp_surge
    }
    
    stock_allocation_district = evaluate_stock_allocation(
        surge_data=surge_data_district,
        forecast_horizon_days=ctx.state["forecast_days"]
    )
    
    daily_demand_curves_district = {
        "HKM": generate_daily_demand_curves("HKM", ctx.state["severity"]),
        "HKP": generate_daily_demand_curves("HKP", ctx.state["severity"])
    }
    
    # Backward compatibility with single-facility format:
    legacy_stock_allocation = evaluate_stock_allocation(hkm_surge, ctx.state["forecast_days"])

    return Event(
        output={"surge_data": hkm_surge, "stock_allocation": legacy_stock_allocation},
        state={
            "medication_surge": hkm_surge, 
            "medication_surge_district": surge_data_district,
            "stock_allocation": legacy_stock_allocation,
            "stock_allocation_district": stock_allocation_district,
            "daily_demand_curves_district": daily_demand_curves_district
        }
    )

@node(name="reporting", rerun_on_resume=True)
async def reporting_node(ctx: Context, node_input: dict) -> Event:
    """Fetches RAG guidelines context and drafts the situational brief."""
    guidelines_context = search_disaster_guidelines(
        f"Stock buffer and relocation rules for HKM facility."
    )
    ctx.state["guidelines_context"] = guidelines_context
    
    rep_input = types.Content(parts=[types.Part.from_text(text=f"Generate the report based on current state: {ctx.state}")])
    rep_result = await ctx.run_node(reporter_agent, node_input=rep_input)
    
    rep_brief = rep_result.get("situational_brief", "")
    if "Hospital Kuala Makar" not in rep_brief:
        rep_brief = rep_brief.replace("HKM", "Hospital Kuala Makar (HKM)")
    if "Hospital Kampung Pisang" not in rep_brief:
        rep_brief = rep_brief.replace("HKP", "Hospital Kampung Pisang (HKP)")
        
    rep_concerns = rep_result.get("key_concerns", [])
    ctx.state["situational_brief"] = rep_brief
    ctx.state["key_concerns"] = rep_concerns
    
    return Event(output=rep_result, state={
        "situational_brief": rep_brief,
        "key_concerns": rep_concerns
    })

@node(name="hitl_gatekeeper", rerun_on_resume=True)
async def hitl_gatekeeper_node(ctx: Context, node_input: ReportOutput) -> AsyncGenerator[Event, None]:
    """Waits for Disaster Pharmacy Manager validation or modification instructions."""
    brief = ctx.state.get("situational_brief", "")
    
    post_safety_passed = ctx.state.get("post_safety_passed", "None")
    post_safety_reason = ctx.state.get("post_safety_reason", "")
    
    if post_safety_passed == "Fail":
        brief = brief + f"\n\n⚠️ **POST-DECISION SAFETY AUDIT FAILED:**\n{post_safety_reason}\n*Please adjust parameters via `/modify` or edit values in the grid before re-submitting.*"
        ctx.state["post_safety_passed"] = "None"

    # Pause and wait for HITL command if not provided
    if not ctx.resume_inputs or "hitl_command" not in ctx.resume_inputs:
        yield RequestInput(interrupt_id="hitl_command", message=brief)
        return

    command = ctx.resume_inputs["hitl_command"].strip()
    
    # Case-insensitive validation of Manager commands
    if command.lower().startswith("/approve"):
        # Check for overrides payload
        payload_str = command[8:].strip()
        overrides = None
        if payload_str:
            try:
                import json
                overrides = json.loads(payload_str)
            except Exception:
                pass
        
        ctx.state["overrides"] = overrides
        yield Event(output=brief, route="approve", state={"overrides": overrides})
    elif command.lower().startswith("/modify"):
        feedback = command[7:].strip()
        yield Event(output=feedback, route="modify", state={"feedback": feedback})
    else:
        # Reprompt on unknown commands / typo errors
        warning_msg = brief + f"\n\n⚠️ **Error: Unknown command '{command}'. Please enter `/approve` or `/modify [adjustments]`.**"
        yield RequestInput(interrupt_id="hitl_command", message=warning_msg)

@node(name="post_decision_safety", rerun_on_resume=True)
def post_decision_safety_node(ctx: Context, node_input: str) -> Event:
    """Verifies that custom quantity overrides comply with physical inventory stocks."""
    overrides = ctx.state.get("overrides")
    current_alloc = ctx.state.get("stock_allocation_district")
    
    if overrides:
        # Check overrides via tools
        validation_result = validate_custom_allocation_plan(current_alloc, overrides)
        
        if not validation_result["passed"]:
            ctx.state["post_safety_passed"] = "Fail"
            ctx.state["post_safety_reason"] = validation_result["reason"]
            return Event(
                output=validation_result,
                route="fail",
                state={"post_safety_passed": "Fail", "post_safety_reason": validation_result["reason"]}
            )
        else:
            # Overrides are valid, update the stock allocation state with the overrides
            import copy
            updated_alloc = copy.deepcopy(current_alloc)
            for fac_id, meds in overrides.items():
                for med_name, actions in meds.items():
                    if fac_id in updated_alloc and med_name in updated_alloc[fac_id]:
                        orig = updated_alloc[fac_id][med_name]
                        orig["relocation_qty"] = float(actions.get("relocation_qty", orig["relocation_qty"]))
                        orig["procurement_qty"] = float(actions.get("procurement_qty", orig["procurement_qty"]))
                        orig["message"] = f"Manual override: Relocate {orig['relocation_qty']:.1f} units and Procure {orig['procurement_qty']:.1f} units."
                        orig["status"] = "Override Approved"
                        
                        # Sync the lend_qty of the donor facility
                        donor_id = "HKP" if fac_id == "HKM" else "HKM"
                        if donor_id in updated_alloc and med_name in updated_alloc[donor_id]:
                            updated_alloc[donor_id][med_name]["lend_qty"] = orig["relocation_qty"]
                            
            ctx.state["stock_allocation_district"] = updated_alloc
            ctx.state["post_safety_passed"] = "Pass"
            ctx.state["post_safety_reason"] = "Manual overrides verified and passed compliance rules."
    else:
        ctx.state["post_safety_passed"] = "Pass"
        ctx.state["post_safety_reason"] = "Recommended plan approved without overrides. Baseline validation passed."
        
    return Event(
        output={"passed": True},
        route="pass",
        state={"post_safety_passed": ctx.state["post_safety_passed"], "post_safety_reason": ctx.state["post_safety_reason"]}
    )

@node(name="dispatch")
def dispatch_node(ctx: Context, node_input: dict) -> Event:
    """Formats two separate messages for HKM and HKP and outputs final approval signature."""
    alloc = ctx.state["stock_allocation_district"]
    severity = ctx.state["severity"]
    days = ctx.state["forecast_days"]
    
    # Generate HKM message
    hkm_lines = []
    hkm_lines.append(f"### 📍 DISPATCH PLAN FOR HOSPITAL KUALA MAKAR (HKM)")
    hkm_lines.append(f"**Date:** 29 Jun 2026")
    hkm_lines.append(f"**Disaster Severity Rating:** {severity:.2f} ({days}-day forecast horizon)")
    hkm_lines.append(f"\n**Required Operational Actions:**")
    
    for med, info in alloc["HKM"].items():
        hkm_lines.append(f"- **{med}**: Current Stock: {int(info['current_stock']):,} | Forecast Demand: {int(info['total_needed']):,}")
        if info['relocation_qty'] > 0:
            hkm_lines.append(f"  * ACTION: Receive **{int(info['relocation_qty']):,} units** relocated from Hospital Kampung Pisang (HKP).")
        if info['lend_qty'] > 0:
            hkm_lines.append(f"  * ACTION: Transfer/Lend **{int(info['lend_qty']):,} units** to Hospital Kampung Pisang (HKP).")
        if info['procurement_qty'] > 0:
            hkm_lines.append(f"  * ACTION: Order **{int(info['procurement_qty']):,} units** from Makar District Health Office (MDHO) central depot.")
        if info['relocation_qty'] == 0 and info['lend_qty'] == 0 and info['procurement_qty'] == 0:
            hkm_lines.append(f"  * ACTION: Maintain status quo. Local stock is sufficient.")
            
    hkm_msg = "\n".join(hkm_lines)
    
    # Generate HKP message
    hkp_lines = []
    hkp_lines.append(f"### 📍 DISPATCH PLAN FOR HOSPITAL KAMPUNG PISANG (HKP)")
    hkp_lines.append(f"**Date:** 29 Jun 2026")
    hkp_lines.append(f"**Disaster Severity Rating:** {severity:.2f} ({days}-day forecast horizon)")
    hkp_lines.append(f"\n**Required Operational Actions:**")
    
    for med, info in alloc["HKP"].items():
        hkp_lines.append(f"- **{med}**: Current Stock: {int(info['current_stock']):,} | Forecast Demand: {int(info['total_needed']):,}")
        if info['relocation_qty'] > 0:
            hkp_lines.append(f"  * ACTION: Receive **{int(info['relocation_qty']):,} units** relocated from Hospital Kuala Makar (HKM).")
        if info['lend_qty'] > 0:
            hkp_lines.append(f"  * ACTION: Transfer/Lend **{int(info['lend_qty']):,} units** to Hospital Kuala Makar (HKM).")
        if info['procurement_qty'] > 0:
            hkp_lines.append(f"  * ACTION: Order **{int(info['procurement_qty']):,} units** from Makar District Health Office (MDHO) central depot.")
        if info['relocation_qty'] == 0 and info['lend_qty'] == 0 and info['procurement_qty'] == 0:
            hkp_lines.append(f"  * ACTION: Maintain status quo. Local stock is sufficient.")
            
    hkp_msg = "\n".join(hkp_lines)
    
    final_brief = f"{hkm_msg}\n\n---\n\n{hkp_msg}\n\n---\n**Disaster Pharmacy Manager Digital Sign-off: APPROVED**\n*Metadata: Verified by Hospital Kuala Makar Disaster Pharmacy Intelligence System*"
    
    state_update = {
        "hkm_message": hkm_msg,
        "hkp_message": hkp_msg,
        "final_brief": final_brief,
        "approved": True
    }
    return Event(output=final_brief, state=state_update)

root_agent = Workflow(
    name="remedi_workflow",
    edges=[
        ('START', coordinator_agent),
        (coordinator_agent, data_ingestion_node),
        (data_ingestion_node, governance_node),
        (governance_node, analytics_node),
        (analytics_node, reporting_node),
        (reporting_node, hitl_gatekeeper_node),
        (hitl_gatekeeper_node, {'modify': coordinator_agent, 'approve': post_decision_safety_node}),
        (post_decision_safety_node, {'pass': dispatch_node, 'fail': hitl_gatekeeper_node}),
    ],
    description="REMEDI disaster pharmacy intelligence multi-agent workflow.",
    before_agent_callback=init_state
)

app = App(
    root_agent=root_agent,
    name="app",
    resumability_config=ResumabilityConfig(is_resumable=True),
)
