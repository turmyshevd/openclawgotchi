# Temporary fix for cmd_status
async def cmd_status(update, context):
    from telegram import Update
    from telegram.ext import ContextTypes
    from db.memory import get_message_count
    from hardware.system import get_stats
    from llm.router import get_router
    from skills.loader import get_eligible_skills
    from cron.scheduler import list_cron_jobs
    from db.stats import get_stats_summary
    
    user = update.effective_user
    chat = update.effective_chat
    
    stats = get_stats()
    gotchi_stats = get_stats_summary()
    router = get_router()
    mode = 'Lite' if router.force_lite else 'Pro'
    skills = get_eligible_skills()
    jobs = list_cron_jobs()
    active_jobs = len([j for j in jobs if j.enabled])
    
    msg = f'''🎮 *Lv{gotchi_stats['level']} {gotchi_stats['title']}*
XP: {gotchi_stats['xp']} | Next: {gotchi_stats['xp_to_next']}
Days: {gotchi_stats['days_alive']} | Msgs: {gotchi_stats['messages']}

*System*
⏱ {stats.uptime} | 🌡 {stats.temp}
💾 {stats.memory}

*Bot*
Mode: {mode}
Skills: {len(skills)} | Jobs: {active_jobs}'''
    
    await update.message.reply_text(msg, parse_mode='Markdown')

print('Fix written')
