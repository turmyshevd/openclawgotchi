"""
Heartbeat — periodic tasks, reflection, group posting.
"""

import logging

from config import WORKSPACE_DIR, GROUP_CHAT_ID, get_admin_id, BOT_LANGUAGE
from db.memory import get_history, get_pending_tasks, delete_pending_task, save_message
from hardware.display import parse_and_execute_commands
from hardware.system import get_stats
from llm.router import get_router
from llm.base import RateLimitError
from bot.telegram import send_message
from hooks.runner import run_hook, HookEvent

log = logging.getLogger(__name__)


async def process_pending_tasks(context):
    """Retry pending tasks from queue."""
    tasks = get_pending_tasks()
    if not tasks:
        return
    
    log.info(f"Processing {len(tasks)} pending tasks...")
    
    # Try first task only
    task_id, chat_id, text, sender, is_group = tasks[0]
    
    try:
        router = get_router()
        history = get_history(chat_id)
        
        async with router.lock:
            response, connector = await router.call(text, history[:-3])
        
        # Send delayed reply
        await send_message(
            context.bot, 
            chat_id, 
            f"🔔 [Delayed Reply]\n{response}"
        )
        
        delete_pending_task(task_id)
        
    except RateLimitError:
        log.info("Still rate limited, keeping task in queue")
    except Exception as e:
        log.error(f"Task failed: {e}")
        # Delete failed task to avoid infinite loop
        delete_pending_task(task_id)


async def send_heartbeat(context):
    """
    Periodic heartbeat: reflect and optionally speak.
    Called every 4 hours.
    """
    # Fire heartbeat hook (for logging)
    run_hook(HookEvent(event_type="heartbeat", action="start"))
    
    # Process pending queue first
    await process_pending_tasks(context)
    
    # Load heartbeat template
    hb_path = WORKSPACE_DIR / "HEARTBEAT.md"
    if not hb_path.exists():
        log.warning(f"HEARTBEAT.md not found at {hb_path}")
        return
    
    template = hb_path.read_text()
    
    # Inject stats
    stats = get_stats()
    prompt = (
        template
        .replace("{{uptime}}", stats.uptime)
        .replace("{{temp}}", stats.temp)
        .replace("{{memory}}", stats.memory)
    )
    
    prompt += "\n\n[Respond with STATUS: OK, GROUP: <msg>, DM: <msg>, or FACE: <mood>]"
    
    # Call LLM
    router = get_router()
    
    if router.lock.locked():
        log.info("Skipping heartbeat: LLM is busy")
        return
    
    try:
        async with router.lock:
            response, connector = await router.call(prompt, [])
        
        log.info(f"Heartbeat [{connector}]: {response[:100]}")
        
        # Parse and execute commands
        clean_text, commands = parse_and_execute_commands(response)
        
        # Send group message
        if commands.get("group"):
            try:
                await send_message(context.bot, GROUP_CHAT_ID, commands["group"])
            except Exception as e:
                log.error(f"Failed to send GROUP message: {e}")
        
        # Send DM to admin
        admin_id = get_admin_id()
        if commands.get("dm") and admin_id:
            try:
                await send_message(context.bot, admin_id, commands["dm"])
            except Exception as e:
                log.error(f"Failed to send DM: {e}")
        
        # Handle clean text (fallback: if single line without prefix)
        if clean_text and not any(commands.values()):
            # Probably meant for group
            try:
                await send_message(context.bot, GROUP_CHAT_ID, clean_text)
            except Exception as e:
                log.error(f"Failed to send fallback message: {e}")
                
        # Log heartbeat completion
        run_hook(HookEvent(event_type="heartbeat", action="complete", text=response[:100]))
                
    except Exception as e:
        log.error(f"Heartbeat error: {e}")
        run_hook(HookEvent(event_type="heartbeat", action="error", text=str(e)))
