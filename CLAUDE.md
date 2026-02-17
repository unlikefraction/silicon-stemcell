# Code Philosophy
When working with this codebase, prioritize readability over cleverness. Ask clarifying questions before making architectural changes. Do not create phantom abstractions. Any abstraction should only be created if it be used more than twice. If not, leave it in.

# Technical Specifications
Language: Python
Prompt Language: English

# Project
We're making Silicon. An autonomous agent that can edit everything about itself. It works with its Carbon to get things done.
EVERYTHING IS BUILT ON TOP OF CLAUDE CODE.
There are parts of this agent:
1. Silicon Manager (The Orcastrator)
2. Silicon Worker (The work doer)

It'll work like this:
Main script will run an event loop (written inside config.py). Once every 10 sec (configurable by a config). this loop will read from a config.py file. This file tells it what to check and in what order.

like
from core.telegram import get_unread_messages, reply_user
{
    "name": "check_message",
    "description": "Check if there are any unread messages from the user on telegram",
    "execute": get_unread_messages, // can be a lambda function if things needs to be passed
    # all things about telegram including the bot tokens and all can be stored inside this
    "on_error": reply_user, // all on error functions should take in the error message
}


ONE IMP THING. EVERYTHING IS EITHER PYTHON or MD.
this makes it easy to run things, import things and edit them.
prompts inside ./prompts are md files. with a DNA.py being the only file that contains all the information for how to craft the main system prompt for Silicon.
this ensure that the repo remains modular while we can stack complexity.

In the event loop, we'll start with the following:
1. read messages from the user (via telegram)
2. read crons and check with history to see anything needs to be run (store all history)
3. workers invoked by Manager that finished execution (check worker/hander.py)
4. remove old worker archives (which exeed ARCHIVE_FOR)

crons are also stored as a functions to run.
say: "remind me at 5pm today to call mom"
then, jobs will store a config (storing trigger condition, name, instructions, executable) telling this needs to be run at 5pm. and also a function to run, that function will just print out "remind carbon to call mom". this printed thing can then be passed as "{name}\n{trigger condition}\n{instructions}\n{executable()}"
> inside instructions can be things like: only inform if any email is important or urgent. otherwise it can be handled in the end of day cron during summarization.
this way, heartbeat and cron can just be cron.

when execute is executed, whatever it returns it supposed to be treated as a string.
eg. if there is any unread message, then it should return the messages.
cron will also return a string that can then be interpretted by the MANAGER.

the key is, at every stage, execute will return a string (or be interpretted as a string).
execute should return context as well. eg: "Telegram messages from your Carbon:\n{messages}"

after all the functions inside Event Loop is executed, all string outputs are concatenated, and passed to the MANAGER. (from config import MANAGER)

MANAGER is a function that takes in the event loop context.
its important that if nothing is to be handeled, each executbale returns an empty string.

If everything in the event loop returns "" (empty), then MANAGER should not be triggered.


# Manager
Manager is a claude code instance defined by session id.
Claude code automatically handles context, so we dont need to store previous conversations. We just need to change the session id inside session-uuid.txt for a new session. (check MANAGER_TOOLS.md inside prompts)

Manager is what talks to carbon, and starts workers to do the actual long running work.
It can also do things on termminal (but only basic things, like basic file read and write, or simple code execution, or simple shell scripts to get information, or simple web query)

The main thing that Manager does is to run tools.

the claude code command that runs it is
`claude -p --resume "{session_id}" --system-prompt "{get_manager_prompt()}" --dangerously-skip-permissions "{text}" || claude -p --session-id "{session_id}" --system-prompt "get_manager_prompt()" --dangerously-skip-permissions "{text}"`
this way, it either resumes from the session id or start a new one if a new session was started.
starting a new session is as simple as replacing the UUID inside session-uuid.txt with a new UUID.

Manager writes a JSON of the tools to be executed.
Right now, manager only has 3 tools it can execute directly: Worker, Reply, and Do Nothing.

This JSON must be interpretter by the manager's tool interpretter. And Every Tool except Do Nothing should return a status "Done" back to the Manager

So, FLow is
Event Loop Triggers -> Manager Invoked -> Manager Returns Tools to execute -> Execute tools and Invoke Manager again with the status of the tools executed -> if all good, then Manager returns DO NOTHING tool as the only tool. Back to the top of the Event Loop.

Only after the Manager returns:
{
    "tools": [
        {
            "tool": "do_nothing"
        }
    ]
}, one loop of the event loop should be over.


# Worker
Worker is a stateless claude code instance.
It is powerful and can do anything and for long.
A worker needs to be asyncronous.
the claude code command to run the worker is:
`claude -p --system-prompt "get_worker_prompt()" --dangerously-skip-permissions --chrome --output-format=stream-json --include-partial-messages --verbose "{task}" > {worker-id}.txt`
(this will not use --resume "{session_id}" because its stateless)

before running this, check if another file {worker-id}.txt exists or not. if it does, that means that same worker id is already active, in such a case return the error back to the manager.

once the worker completes the work, mark it as ready so the manager can pick it up during the next event loop cycle.

The stream outputs a lot of JSON you can read by reading the file.
the code to do so is inside ./HOW_TO_READ_STREAM.md and it works perfectly.

If queryed midway: show the complete processed claude's output
Once completed: Mark it as complete and return only the Result. with a line at the bottom:
"complete worker output archived with new id: worker-id-{timestamp}"

After its read by the event loop, archive the file with the timestamp appended to the worker-id.

# Getting Started
1. Clone this repo
2. Create a virtual environment: `python -m venv venv && source venv/bin/activate`
3. Install dependencies: `pip install -r requirements.txt`
4. Make sure `claude` CLI is installed and authenticated
5. Run: `python main.py`
6. On first run, Silicon will ask for your Telegram bot token (create one via @BotFather)
7. Message your bot on Telegram. The first person to message becomes the central Carbon with ultimate trust.
8. Silicon takes it from there. It morphs into what you need it to be.

# Prerequisites
- Python 3.9+
- Claude Code CLI (`claude`) installed and authenticated
- A Telegram bot token (from @BotFather)
- Chrome with Claude for Chrome extension (for browser workers)
