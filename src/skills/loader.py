"""
Skills loader with gating support.
Filters skills based on requirements (bins, env, os).
"""

import os
import shutil
import platform
import logging
import re
import json
from pathlib import Path
from typing import Optional
from dataclasses import dataclass

from config import PROJECT_DIR

log = logging.getLogger(__name__)

SKILLS_DIRS = [
    PROJECT_DIR / "gotchi-skills",
    PROJECT_DIR / "openclaw-skills",
]


@dataclass
class SkillRequirements:
    """Requirements for a skill to be eligible."""
    bins: list[str] = None          # All must exist on PATH
    any_bins: list[str] = None      # At least one must exist
    env: list[str] = None           # Env vars that must be set
    os_list: list[str] = None       # Allowed OS (linux, darwin, win32)
    always: bool = False            # Skip all checks
    
    def __post_init__(self):
        self.bins = self.bins or []
        self.any_bins = self.any_bins or []
        self.env = self.env or []
        self.os_list = self.os_list or []


@dataclass
class Skill:
    """Loaded skill information."""
    name: str
    description: str
    path: Path
    eligible: bool
    reason: str = ""  # Why not eligible
    emoji: str = ""
    requires: Optional[SkillRequirements] = None


def parse_skill_frontmatter(content: str) -> dict:
    """Parse YAML frontmatter from SKILL.md."""
    # Match ---\n...\n---
    match = re.match(r'^---\s*\n(.*?)\n---', content, re.DOTALL)
    if not match:
        return {}
    
    frontmatter = {}
    yaml_text = match.group(1)
    
    # Simple YAML parsing (single-line values)
    for line in yaml_text.split('\n'):
        line = line.strip()
        if ':' in line and not line.startswith('#'):
            key, value = line.split(':', 1)
            key = key.strip()
            value = value.strip()
            
            # Handle JSON metadata
            if key == 'metadata' and value.startswith('{'):
                # Find full JSON (might span multiple lines)
                json_start = yaml_text.find('metadata:')
                if json_start >= 0:
                    json_text = yaml_text[json_start + len('metadata:'):].strip()
                    # Try to parse JSON
                    try:
                        # Handle multi-line JSON
                        brace_count = 0
                        json_end = 0
                        for i, c in enumerate(json_text):
                            if c == '{':
                                brace_count += 1
                            elif c == '}':
                                brace_count -= 1
                                if brace_count == 0:
                                    json_end = i + 1
                                    break
                        if json_end > 0:
                            frontmatter['metadata'] = json.loads(json_text[:json_end])
                    except json.JSONDecodeError:
                        pass
            else:
                # Remove quotes
                if value.startswith('"') and value.endswith('"'):
                    value = value[1:-1]
                elif value.startswith("'") and value.endswith("'"):
                    value = value[1:-1]
                frontmatter[key] = value
    
    return frontmatter


def check_requirements(req: SkillRequirements) -> tuple[bool, str]:
    """
    Check if requirements are met.
    Returns (eligible, reason).
    """
    if req.always:
        return True, ""
    
    # Check OS
    if req.os_list:
        current_os = platform.system().lower()
        os_map = {'linux': 'linux', 'darwin': 'darwin', 'windows': 'win32'}
        current = os_map.get(current_os, current_os)
        if current not in req.os_list:
            return False, f"OS {current} not in {req.os_list}"
    
    # Check binaries (all must exist)
    for bin_name in req.bins:
        if not shutil.which(bin_name):
            return False, f"Binary '{bin_name}' not found"
    
    # Check any_bins (at least one must exist)
    if req.any_bins:
        found = any(shutil.which(b) for b in req.any_bins)
        if not found:
            return False, f"None of {req.any_bins} found"
    
    # Check env vars
    for env_var in req.env:
        if not os.environ.get(env_var):
            return False, f"Env var '{env_var}' not set"
    
    return True, ""


def load_skill(skill_dir: Path) -> Optional[Skill]:
    """Load a single skill from directory."""
    skill_md = skill_dir / "SKILL.md"
    if not skill_md.exists():
        return None
    
    try:
        content = skill_md.read_text(encoding='utf-8')
        frontmatter = parse_skill_frontmatter(content)
        
        name = frontmatter.get('name', skill_dir.name)
        description = frontmatter.get('description', '')
        
        # Parse requirements from metadata.openclaw
        req = SkillRequirements()
        emoji = ""
        
        metadata = frontmatter.get('metadata', {})
        if isinstance(metadata, dict):
            openclaw = metadata.get('openclaw', {})
            if isinstance(openclaw, dict):
                emoji = openclaw.get('emoji', '')
                req.always = openclaw.get('always', False)
                req.os_list = openclaw.get('os', [])
                
                requires = openclaw.get('requires', {})
                if isinstance(requires, dict):
                    req.bins = requires.get('bins', [])
                    req.any_bins = requires.get('anyBins', [])
                    req.env = requires.get('env', [])
        
        # Check eligibility
        eligible, reason = check_requirements(req)
        
        return Skill(
            name=name,
            description=description,
            path=skill_dir,
            eligible=eligible,
            reason=reason,
            emoji=emoji,
            requires=req
        )
        
    except Exception as e:
        log.warning(f"Failed to load skill {skill_dir}: {e}")
        return None


def load_all_skills() -> list[Skill]:
    """
    Load all skills from all skill directories.
    Optimized for Pi Zero: only parses skills in ACTIVE_SKILLS list
    to save RAM and CPU.
    """
    from config import PROJECT_DIR
    import os

    # Skills that are always loaded (essential for bot operation)
    # gotchi-skills take precedence over openclaw-skills with same name
    CORE_SKILLS = ["coding", "display", "weather", "system", "discord"]
    
    # Get additional active skills from env (optional)
    active_env = os.environ.get("ACTIVE_SKILLS", "")
    active_skills = CORE_SKILLS + [s.strip() for s in active_env.split(",") if s.strip()]
    
    skills = []
    seen_names = set()
    
    for skills_dir in SKILLS_DIRS:
        if not skills_dir.exists():
            continue
        
        for item in skills_dir.iterdir():
            if not item.is_dir():
                continue
            
            # Optimization: Skip parsing if not in active list
            if item.name not in active_skills:
                continue
            
            skill = load_skill(item)
            if skill and skill.name not in seen_names:
                skills.append(skill)
                seen_names.add(skill.name)
    
    return skills


def get_eligible_skills() -> list[Skill]:
    """Get only eligible skills."""
    return [s for s in load_all_skills() if s.eligible]


def format_skills_for_prompt(skills: list[Skill] = None) -> str:
    """Format skills list for system prompt."""
    if skills is None:
        skills = get_eligible_skills()
    
    if not skills:
        return ""
    
    lines = ["", "## Available Skills", ""]
    for skill in skills:
        emoji = f"{skill.emoji} " if skill.emoji else ""
        lines.append(f"- **{emoji}{skill.name}**: {skill.description}")
        lines.append(f"  Location: `{skill.path}/SKILL.md`")
    
    lines.append("")
    lines.append("Read SKILL.md before using a skill.")
    
    return "\n".join(lines)


# ============================================================
# SKILL CATALOG (Passive Knowledge)
# ============================================================

def get_skill_catalog() -> str:
    """
    Get the full skill catalog from openclaw-skills/CATALOG.md.
    This is "passive knowledge" — bot doesn't load these, but can search them.
    """
    catalog_path = PROJECT_DIR / "openclaw-skills" / "CATALOG.md"
    if catalog_path.exists():
        return catalog_path.read_text(encoding='utf-8')
    return ""


def search_skill_catalog(query: str) -> str:
    """
    Search the skill catalog for relevant skills.
    Returns matching entries from CATALOG.md.
    
    Args:
        query: Search term (skill name, keyword, or capability)
    
    Returns:
        Matching skill descriptions, or suggestion to check catalog
    """
    catalog = get_skill_catalog()
    if not catalog:
        return "Skill catalog not found (openclaw-skills/CATALOG.md)"
    
    query_lower = query.lower()
    lines = catalog.strip().split('\n')
    
    matches = []
    for line in lines:
        if line.startswith('-') and query_lower in line.lower():
            matches.append(line)
    
    if not matches:
        # Fuzzy search: check individual words
        query_words = query_lower.split()
        for line in lines:
            if line.startswith('-'):
                line_lower = line.lower()
                if any(word in line_lower for word in query_words):
                    matches.append(line)
    
    if matches:
        result = f"Found {len(matches)} skill(s) matching '{query}':\n\n"
        result += "\n".join(matches[:10])  # Max 10 results
        if len(matches) > 10:
            result += f"\n\n... and {len(matches) - 10} more."
        result += "\n\n⚠️ Note: These skills are from openclaw-skills/ and may require macOS or specific tools. Check SKILL.md for requirements."
        return result
    
    return f"No skills found matching '{query}'. Try broader terms or check openclaw-skills/CATALOG.md directly."


def get_skill_content(skill_name: str) -> str:
    """
    Read the full content of a skill's SKILL.md.
    Works for both gotchi-skills and openclaw-skills.
    """
    for skills_dir in SKILLS_DIRS:
        skill_path = skills_dir / skill_name / "SKILL.md"
        if skill_path.exists():
            content = skill_path.read_text(encoding='utf-8')
            
            # Add compatibility warning for openclaw-skills
            if "openclaw-skills" in str(skills_dir):
                warning = (
                    "\n\n---\n"
                    "⚠️ **COMPATIBILITY WARNING**: This skill is from openclaw-skills/ "
                    "and may not work on Raspberry Pi. Check requirements above.\n"
                    "---\n"
                )
                return content + warning
            
            return content
    
    return f"Skill '{skill_name}' not found. Use search_skills() to find available skills."


def list_all_skill_names() -> list[str]:
    """List all available skill names (for autocomplete/discovery)."""
    names = []
    for skills_dir in SKILLS_DIRS:
        if not skills_dir.exists():
            continue
        for item in skills_dir.iterdir():
            if item.is_dir() and (item / "SKILL.md").exists():
                names.append(item.name)
    return sorted(set(names))
