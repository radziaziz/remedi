import asyncio
from app.agent import app
from google.adk.runners import InMemoryRunner
from google.genai import types

async def main():
    runner = InMemoryRunner(app=app)
    user_id = "test"
    session = await runner.session_service.create_session(app_name=app.name, user_id=user_id)
    
    print("Initial session state:", session.state)
    
    new_message = types.Content(
        role="user",
        parts=[types.Part.from_text(text="Severe flooding reported in Kuala Makar district.")]
    )
    
    try:
        async for event in runner.run_async(user_id=user_id, session_id=session.id, new_message=new_message):
            print("Event:", event)
    except Exception as e:
        import traceback
        traceback.print_exc()
        
    # Reload session
    session_obj = await runner.session_service.get_session(app_name=app.name, user_id=user_id, session_id=session.id)
    print("Post-run session state:", session_obj.state if session_obj else None)

if __name__ == "__main__":
    asyncio.run(main())
