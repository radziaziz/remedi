# Copyright 2026 Google LLC
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#     https://www.apache.org/licenses/LICENSE-2.0

from dotenv import load_dotenv
load_dotenv()

import os
import logging
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel
from typing import Optional, Any

import google.auth
from google.cloud import logging as google_cloud_logging

from google.adk.runners import InMemoryRunner
from google.adk.apps import App
from google.genai import types

# Setup local or cloud logging
use_vertex = os.environ.get("GOOGLE_GENAI_USE_VERTEXAI", "False").lower() in ("true", "1")
logger_name = "remedi_fastapi"

if use_vertex:
    try:
        _, project_id = google.auth.default()
        logging_client = google_cloud_logging.Client()
        cloud_logger = logging_client.logger(logger_name)
        class CloudLoggerWrapper:
            def log_struct(self, data, severity="INFO"):
                cloud_logger.log_struct(data, severity=severity)
            def info(self, msg):
                cloud_logger.log_text(msg, severity="INFO")
            def warning(self, msg):
                cloud_logger.log_text(msg, severity="WARNING")
        logger = CloudLoggerWrapper()
    except Exception as e:
        logging.basicConfig(level=logging.INFO)
        logger = logging.getLogger(logger_name)
else:
    logging.basicConfig(level=logging.INFO)
    logger = logging.getLogger(logger_name)

# Import ADK App and Runner from app.agent
from app.agent import app as adk_app
runner = InMemoryRunner(app=adk_app)

# Initialize FastAPI App
app = FastAPI(
    title="REMEDI API",
    description="Backend API for Resilient Medication Management for Disasters (REMEDI)"
)

# Configure CORS Middleware
allow_origins = (
    os.getenv("ALLOW_ORIGINS", "").split(",") if os.getenv("ALLOW_ORIGINS") else ["*"]
)
app.add_middleware(
    CORSMiddleware,
    allow_origins=allow_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ==========================================
# Pydantic Request/Response Models
# ==========================================

class StartRequest(BaseModel):
    alert: str

class HitlRequest(BaseModel):
    session_id: str
    command: str

# ==========================================
# API Endpoints
# ==========================================

@app.post("/api/start")
async def api_start(req: StartRequest):
    """Starts a new REMEDI disaster pharmacy intelligence session."""
    user_id = "clinician_web"
    try:
        session = await runner.session_service.create_session(
            app_name=adk_app.name,
            user_id=user_id
        )
        
        new_message = types.Content(
            role="user",
            parts=[types.Part.from_text(text=req.alert)]
        )
        
        hitl_interrupt = None
        final_output = None
        
        async for event in runner.run_async(
            user_id=user_id,
            session_id=session.id,
            new_message=new_message
        ):
            if event.content and event.content.parts:
                for part in event.content.parts:
                    if part.function_call and part.function_call.name == "adk_request_input":
                        hitl_interrupt = part.function_call
            if event.output is not None and not hitl_interrupt:
                final_output = event.output
                
        session_obj = await runner.session_service.get_session(
            app_name=adk_app.name,
            user_id=user_id,
            session_id=session.id
        )
        state = session_obj.state if session_obj else {}
        
        return {
            "session_id": session.id,
            "status": "waiting_hitl" if hitl_interrupt else "completed",
            "interrupt_id": hitl_interrupt.id if hitl_interrupt else None,
            "brief_draft": hitl_interrupt.args.get("message", "") if hitl_interrupt else None,
            "final_brief": final_output,
            "state": state
        }
    except Exception as e:
        logging.error(f"Error in api_start: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/api/hitl")
async def api_hitl(req: HitlRequest):
    """Resumes a paused REMEDI session with a clinician command."""
    user_id = "clinician_web"
    try:
        resume_message = types.Content(
            role="user",
            parts=[
                types.Part(
                    function_response=types.FunctionResponse(
                        id="hitl_command",
                        name="adk_request_input",
                        response={"result": req.command}
                    )
                )
            ]
        )
        
        hitl_interrupt = None
        final_output = None
        
        async for event in runner.run_async(
            user_id=user_id,
            session_id=req.session_id,
            new_message=resume_message
        ):
            if event.content and event.content.parts:
                for part in event.content.parts:
                    if part.function_call and part.function_call.name == "adk_request_input":
                        hitl_interrupt = part.function_call
            if event.output is not None and not hitl_interrupt:
                final_output = event.output
                
        session_obj = await runner.session_service.get_session(
            app_name=adk_app.name,
            user_id=user_id,
            session_id=req.session_id
        )
        state = session_obj.state if session_obj else {}
        
        return {
            "session_id": req.session_id,
            "status": "waiting_hitl" if hitl_interrupt else "completed",
            "interrupt_id": hitl_interrupt.id if hitl_interrupt else None,
            "brief_draft": hitl_interrupt.args.get("message", "") if hitl_interrupt else None,
            "final_brief": final_output,
            "state": state
        }
    except Exception as e:
        logging.error(f"Error in api_hitl: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/api/session/{session_id}")
async def api_get_session(session_id: str):
    """Retrieves state of a specific session."""
    user_id = "clinician_web"
    session_obj = await runner.session_service.get_session(
        app_name=adk_app.name,
        user_id=user_id,
        session_id=session_id
    )
    if not session_obj:
        raise HTTPException(status_code=404, detail="Session not found")
    return {
        "session_id": session_id,
        "state": session_obj.state
    }

# ==========================================
# Mount Frontend Static Files
# ==========================================

# Determine parent folder of app/fast_api_app.py
project_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
frontend_dir = os.path.join(project_dir, "frontend")

# Ensure the frontend folder exists before mounting
os.makedirs(frontend_dir, exist_ok=True)

# Mount the static directory
app.mount("/", StaticFiles(directory=frontend_dir, html=True), name="frontend")

if __name__ == "__main__":
    import uvicorn
    uvicorn.run("fast_api_app:app", host="0.0.0.0", port=8000, reload=True)
