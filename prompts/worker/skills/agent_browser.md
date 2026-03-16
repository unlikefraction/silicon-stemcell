# Browser Automation with silicon-browser

Your primary tool for browser automation. All `silicon-browser` commands are executed via Bash.

Your browser session is pre-configured via environment variables. Do NOT pass `--session` or `--profile` flags — they are already set for you. Just use `silicon-browser` commands directly.

## Core Workflow

Every browser automation follows this pattern:

1. **Navigate**: `silicon-browser open <url>`
2. **Snapshot**: `silicon-browser snapshot -i` (get element refs like `@e1`, `@e2`)
3. **Interact**: Use refs to click, fill, select
4. **Re-snapshot**: After navigation or DOM changes, get fresh refs

```bash
silicon-browser open https://example.com/form
silicon-browser snapshot -i
# Output: @e1 [input type="email"], @e2 [input type="password"], @e3 [button] "Submit"

silicon-browser fill @e1 "user@example.com"
silicon-browser fill @e2 "password123"
silicon-browser click @e3
silicon-browser wait --load networkidle
silicon-browser snapshot -i  # Check result
```

## Essential Commands

```bash
# Navigation
silicon-browser open <url>              # Navigate (aliases: goto, navigate)
silicon-browser close                   # Close browser

# Snapshot
silicon-browser snapshot -i             # Interactive elements with refs (recommended)
silicon-browser snapshot -i -C          # Include cursor-interactive elements (divs with onclick, cursor:pointer)
silicon-browser snapshot -s "#selector" # Scope to CSS selector

# Interaction (use @refs from snapshot)
silicon-browser click @e1               # Click element
silicon-browser fill @e2 "text"         # Clear and type text
silicon-browser type @e2 "text"         # Type without clearing
silicon-browser select @e1 "option"     # Select dropdown option
silicon-browser check @e1               # Check checkbox
silicon-browser press Enter             # Press key
silicon-browser scroll down 500         # Scroll page

# Get information
silicon-browser get text @e1            # Get element text
silicon-browser get url                 # Get current URL
silicon-browser get title               # Get page title

# Wait
silicon-browser wait @e1                # Wait for element
silicon-browser wait --load networkidle # Wait for network idle
silicon-browser wait --url "**/page"    # Wait for URL pattern
silicon-browser wait 2000               # Wait milliseconds

# File Upload
silicon-browser upload @e1 ./image.png          # Upload single file to file input
silicon-browser upload @e1 ./a.png ./b.png      # Upload multiple files
silicon-browser upload 'input[type="file"]' ./doc.pdf  # CSS selector works too

# Capture
silicon-browser screenshot              # Screenshot to temp dir
silicon-browser screenshot --full       # Full page screenshot
silicon-browser pdf output.pdf          # Save as PDF
```

## Common Patterns

### Form Submission

```bash
silicon-browser open https://example.com/signup
silicon-browser snapshot -i
silicon-browser fill @e1 "Jane Doe"
silicon-browser fill @e2 "jane@example.com"
silicon-browser select @e3 "California"
silicon-browser check @e4
silicon-browser click @e5
silicon-browser wait --load networkidle
```

### Data Extraction

```bash
silicon-browser open https://example.com/products
silicon-browser snapshot -i
silicon-browser get text @e5           # Get specific element text
silicon-browser get text body > page.txt  # Get all page text

# JSON output for parsing
silicon-browser snapshot -i --json
silicon-browser get text @e1 --json
```

### File Upload

Many sites use hidden `<input type="file">` elements — they won't show up in `snapshot -i`. Target them directly with a CSS selector:

```bash
# Hidden file inputs (common on Gmail, Twitter, etc.)
silicon-browser upload 'input[type="file"]' /path/to/image.png

# If multiple file inputs exist, be more specific
silicon-browser upload 'input[type="file"][accept="image/*"]' /path/to/photo.jpg

# If the input is visible in snapshot, use its ref
silicon-browser upload @e7 /path/to/document.pdf

# Multiple files at once
silicon-browser upload 'input[type="file"]' ./img1.png ./img2.png
```

### Visual Browser (Debugging)

```bash
silicon-browser --headed open https://example.com
silicon-browser highlight @e1          # Highlight element
silicon-browser record start demo.webm # Record session
```

### Local Files (PDFs, HTML)

```bash
silicon-browser --allow-file-access open file:///path/to/document.pdf
silicon-browser --allow-file-access open file:///path/to/page.html
silicon-browser screenshot output.png
```

## Ref Lifecycle (Important)

Refs (`@e1`, `@e2`, etc.) are invalidated when the page changes. Always re-snapshot after:

- Clicking links or buttons that navigate
- Form submissions
- Dynamic content loading (dropdowns, modals)

```bash
silicon-browser click @e5              # Navigates to new page
silicon-browser snapshot -i            # MUST re-snapshot
silicon-browser click @e1              # Use new refs
```

## Semantic Locators (Alternative to Refs)

When refs are unavailable or unreliable, use semantic locators:

```bash
silicon-browser find text "Sign In" click
silicon-browser find label "Email" fill "user@test.com"
silicon-browser find role button click --name "Submit"
silicon-browser find placeholder "Search" type "query"
silicon-browser find testid "submit-btn" click
```

## JavaScript Evaluation (eval)

Use `eval` to run JavaScript in the browser context. **Shell quoting can corrupt complex expressions** -- use `--stdin` or `-b` to avoid issues.

```bash
# Simple expressions work with regular quoting
silicon-browser eval 'document.title'
silicon-browser eval 'document.querySelectorAll("img").length'

# Complex JS: use --stdin with heredoc (RECOMMENDED)
silicon-browser eval --stdin <<'EVALEOF'
JSON.stringify(
  Array.from(document.querySelectorAll("img"))
    .filter(i => !i.alt)
    .map(i => ({ src: i.src.split("/").pop(), width: i.width }))
)
EVALEOF

# Alternative: base64 encoding (avoids all shell escaping issues)
silicon-browser eval -b "$(echo -n 'Array.from(document.querySelectorAll("a")).map(a => a.href)' | base64)"
```

**Rules of thumb:**
- Single-line, no nested quotes -> regular `eval 'expression'` with single quotes is fine
- Nested quotes, arrow functions, template literals, or multiline -> use `eval --stdin <<'EVALEOF'`
- Programmatic/generated scripts -> use `eval -b` with base64