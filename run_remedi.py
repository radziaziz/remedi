# Copyright 2026 Google LLC
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#     https://www.apache.org/licenses/LICENSE-2.0

import asyncio
from app.agent import app
from google.adk.runners import InMemoryRunner
from google.genai import types

async def run_cli():
    print("=" * 60)
    print(" REMEDI - Disaster Pharmacy Intelligence CLI Client")
    print("=" * 60)
    
    runner = InMemoryRunner(app=app)
    user_id = "manager_1"
    session = await runner.session_service.create_session(
        app_name=app.name,
        user_id=user_id
    )
    
    print(f"Session started: {session.id}")
    print("\nPlease enter a disaster alert to begin forecasting.")
    print("Example: 'Severe flooding reported in Kuala Makar district. Rapid river level rise upstream.'")
    print("-" * 60)
    
    alert = input("Disaster Alert > ").strip()
    if not alert:
        print("Alert cannot be empty. Exiting.")
        return
        
    # Start the workflow run
    new_message = types.Content(
        role="user",
        parts=[types.Part.from_text(text=alert)]
    )
    
    current_message = new_message
    
    while True:
        hitl_interrupt = None
        
        # Run the workflow turn
        async for event in runner.run_async(
            user_id=user_id,
            session_id=session.id,
            new_message=current_message
        ):
            # Print content events (e.g. status updates or model steps)
            if event.content and event.content.parts:
                for part in event.content.parts:
                    # If it's a function call to adk_request_input, it means we are at the HITL step
                    if part.function_call and part.function_call.name == "adk_request_input":
                        hitl_interrupt = part.function_call
                    elif part.text:
                        print(part.text)
                        
            # If we received the final output of the workflow
            if event.output is not None and not hitl_interrupt:
                print("\n" + "=" * 60)
                print(" FINAL COMPLETED DISASTER SITUATIONAL BRIEF")
                print("=" * 60)
                print(event.output)
                print("=" * 60)
                return
                
        # If we have reached a HITL state, prompt the user for input
        if hitl_interrupt:
            interrupt_id = hitl_interrupt.id
            brief_draft = hitl_interrupt.args.get("message", "")
            
            print("\n" + "=" * 60)
            print(" SITUATIONAL BRIEF DRAFT FOR DISASTER PHARMACY MANAGER REVIEW")
            print("=" * 60)
            print(brief_draft)
            print("=" * 60)
            
            # Loop until a valid command is entered to avoid typos causing infinite restarts
            while True:
                print("\nManager Actions:")
                print("  Type: /approve                  (to sign off and complete)")
                print("  Type: /modify [instructions]    (to request adjustments)")
                command = input("\nAction > ").strip()
                
                # Check for empty input
                if not command:
                    continue
                
                # Validate commands and handle common typos
                cmd_lower = command.lower()
                
                if cmd_lower == "/approve" or cmd_lower == "/approved":
                    if cmd_lower == "/approved":
                        print("ℹ️ Treating '/approved' as '/approve'.")
                    valid_command = "/approve"
                    break
                elif cmd_lower.startswith("/modify ") or cmd_lower.startswith("/modify"):
                    # Check if they forgot the space or text
                    parts = command.split(" ", 1)
                    if len(parts) < 2 or not parts[1].strip():
                        print("⚠️ Please specify what to modify. Example: '/modify increase forecasting horizon to 10 days'")
                        continue
                    valid_command = command
                    break
                elif cmd_lower.startswith("/") and not (cmd_lower.startswith("/approve") or cmd_lower.startswith("/modify")):
                    # Check for potential typos of approve
                    if "appr" in cmd_lower or "prov" in cmd_lower:
                        print("⚠️ Unknown command. Did you mean '/approve'?")
                    elif "modif" in cmd_lower or "change" in cmd_lower:
                        print("⚠️ Unknown command. Did you mean '/modify [instructions]'?")
                    else:
                        print("⚠️ Unknown command. Valid commands: /approve, /modify [instructions]")
                    continue
                else:
                    # If they didn't start with a slash, treat it as modification feedback
                    print(f"ℹ️ Treating your response as: '/modify {command}'")
                    valid_command = f"/modify {command}"
                    break
            
            # Send the manager command to resume the workflow
            current_message = types.Content(
                role="user",
                parts=[
                    types.Part(
                        function_response=types.FunctionResponse(
                            id=interrupt_id,
                            name="adk_request_input",
                            response={"result": valid_command}
                        )
                    )
                ]
            )
        else:
            # If execution finished without HITL and without explicit final output (edge case)
            break

if __name__ == "__main__":
    asyncio.run(run_cli())
