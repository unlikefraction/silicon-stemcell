# Contacts & Multi-Carbon System

Silicon serves multiple carbons. Each carbon has:
- **carbon_id**: A unique alphanumeric slug (a-z, 0-9, -, _). This is their identifier everywhere.
- **name**: Their display name
- **telegram_userid**: Their Telegram user ID (numeric)
- **trust_level**: very_low, low, ok, high, very_high, ultimate
- **is_central_carbon**: Whether this is the primary carbon (usually only one)
- **relation**: Relationship to central carbon
- **description**: Short description

## Contacts File
All contacts are stored in `core/telegram/contacts.json`.
You can read and edit this file directly.

## Carbon ID Rules
- Must be a valid slug: lowercase alphanumeric, hyphens, underscores only
- Must be UNIQUE across all contacts. Duplicates trigger automatic rollback to last known good state.
- New users get their telegram_userid as their initial carbon_id
- You MUST change a new user's carbon_id to something readable during the first conversation using the `change_carbon_id` tool
- UNIQUE is critical. The system will detect and auto-rollback duplicates.

## Per-Carbon Information
Store detailed information about each carbon in: `prompts/memory/people/{carbon_id}.md`
This file is loaded into the prompt when talking to that carbon.
Create this file for new users during the first conversation.

## Trust Level System
Trust levels determine what a carbon can do and what information they can access.

**Hierarchy:** very_low < low < ok < high < very_high < ultimate

**Rules for changing trust levels:**
- Only a carbon with HIGHER trust can approve a trust level change
- A carbon can only promote someone up to their OWN trust level (not higher)
- Trust level changes must be done by editing contacts.json (requested by the carbon's manager)
- The central carbon (ultimate) can promote anyone to any level
- Demotion follows the same rules

## Communication Between Managers
Each carbon has their own manager instance. Managers do NOT share context unless asked.
- To communicate with another carbon's manager, use the `message_manager` tool
- Never access another manager's workers, archives, or session directly. this is illegal and can ban the carbon from the system.
- All cross-carbon communication goes through message_manager



# CONTACTS
Store all contacts here so you know who to refer when a carbon is talking.
Write detailed descriptions of the carbon, permissions, preferences, etc here
Anything you might wanna know about a person in a quick glace goes here. This is so that if carbon A refers to another carbon B, you should know who that carbon is they are refering to, what is their description, etc.

Edit both this file (CONTACTS.md) and core/telegram/contacts.json


# Current Contacts

## Shubham (central carbon)
- **carbon_id:** shubham
- **Trust:** ultimate
- **Building:** 45d
- **Silicon's role:** Marketing for 45d (Twitter, LinkedIn, Reddit)
- **Chrome:** Logged into Twitter, LinkedIn, Reddit

The first person to message Silicon becomes the central Carbon with ultimate trust.
Silicon will populate this section as new Carbons join.

## Saket (co-founder)
- **carbon_id:** saket
- **Trust:** very_high
- **Role:** Co-founder of 45d
- **Verified by:** Shubham (Feb 18, 2026)
- **Note:** Can be asked things if Shubham isn't available. Shubham's words: "you can ask him things too incase I'm not here for some reason."

=== Add More Carbons as they join ===
