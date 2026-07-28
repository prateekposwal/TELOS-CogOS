#!/usr/bin/env python3
"""
Project Research Bootstrap — initializes the universal research context for any project.

Usage:
  python3 telos/tools/bootstrap_project.py /path/to/project "Project Name"

This creates:
  - PROJECT/AGENTS.md          — persistent context (read at session start)
  - PROJECT/tools/research_monitor.py  — daily data fetcher (optional)
  - PROJECT/.github/workflows/daily-research.yml  — CI/CD for monitoring (optional)
"""
import os, sys, datetime

TEMPLATE = """# {name} — Research Context

## Project Identity
- **Name:** {name}
- **Domain:** 
- **Repo:** {repo}
- **Deployed URL:** 
- **Key People/Orgs:** 

## Current State (update each session)
- **Tests passing:** 
- **Last active:** {date}
- **Session count:** 0
- **Current focus:** 

## Domain Sources
### Primary Sources (URLs to fetch before answering)
- API:
- Docs:
- Core maintainers:

### Community
- Forum:
- Reddit:
- Mailing list:

### Competitors
- Project 1:
- Project 2:

### Data Feeds
- Live metrics:
- Dashboard:

## Open Questions
- Q1:
- Q2:
- Q3:

## Research Checklist (do before every answer)
- [ ] Fetch latest from sources
- [ ] Check if open questions have new answers
- [ ] Cross-reference 2+ independent sources
- [ ] Update hypothesis if data contradicts current state
- [ ] Commit changes

## Session Handoff (fill at end of session)
- State:
- Decisions:
- Open issues:
- Next steps:
"""

def bootstrap(path, name):
    repo_path = os.path.abspath(path)
    
    # Read existing AGENTS.md if present
    agents_path = os.path.join(repo_path, 'AGENTS.md')
    if os.path.exists(agents_path):
        print(f"AGENTS.md already exists at {agents_path}")
        print("Appending template sections if missing...")
        with open(agents_path, 'a') as f:
            f.write(f"\n## Domain Sources\n- (add URLs here)\n")
            f.write(f"\n## Research Checklist\n- [ ] Fetch before answering\n")
        print("Done.")
        return
    
    # Create new AGENTS.md
    os.makedirs(repo_path, exist_ok=True)
    content = TEMPLATE.format(
        name=name,
        repo=repo_path,
        date=datetime.datetime.utcnow().strftime('%Y-%m-%d')
    )
    with open(agents_path, 'w') as f:
        f.write(content)
    
    # Create tools directory
    tools_dir = os.path.join(repo_path, 'tools')
    os.makedirs(tools_dir, exist_ok=True)
    
    print(f"✅ Initialized research context for {name}")
    print(f"   AGENTS.md: {agents_path}")
    print(f"   tools/:    {tools_dir}")
    print()
    print("Next steps:")
    print("  1. Edit AGENTS.md — fill in domain sources (APIs, forums, docs)")
    print("  2. Tell me the domain — I'll research and fill in the template")
    print("  3. Every session starts with: 'check {name} status'")

if __name__ == "__main__":
    if len(sys.argv) < 3:
        print("Usage: python3 bootstrap_project.py /path/to/project 'Project Name'")
        sys.exit(1)
    bootstrap(sys.argv[1], sys.argv[2])
