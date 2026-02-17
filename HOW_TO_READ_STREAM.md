```js
import { useState, useMemo, useCallback } from "react";

const C = {
  bg: "#0a0a0a",
  surface: "#111113",
  surfaceHover: "#19191b",
  border: "#252528",
  text: "#e2e2e5",
  textMuted: "#8b8b8f",
  textDim: "#56565a",
  accent: "#f97316",
  green: "#34d399",
  greenDim: "#065f46",
  blue: "#60a5fa",
  blueDim: "#1e3a5f",
  purple: "#c084fc",
  purpleDim: "#581c87",
  red: "#f87171",
  redDim: "#7f1d1d",
  yellow: "#fbbf24",
  cyan: "#22d3ee",
  orange: "#fb923c",
};

function extractTextFromContent(content) {
  if (!content) return "";
  if (typeof content === "string") return content;
  if (Array.isArray(content)) {
    return content
      .map((c) => {
        if (typeof c === "string") return c;
        if (c.type === "text") return c.text || "";
        if (c.type === "tool_result") return extractTextFromContent(c.content);
        return JSON.stringify(c);
      })
      .filter(Boolean)
      .join("\n");
  }
  if (typeof content === "object") {
    if (content.type === "text") return content.text || "";
    return JSON.stringify(content, null, 2);
  }
  return String(content);
}

function shortToolName(name) {
  if (!name) return "unknown";
  if (name.startsWith("mcp__")) {
    const parts = name.replace("mcp__", "").split("__");
    const server = parts[0] || "";
    const tool = parts.slice(1).join("__") || "";
    const shortServer = server.replace("claude-in-chrome", "chrome").replace("claude-in-", "");
    return `${shortServer}:${tool}`;
  }
  return name;
}

function toolPreview(name, input) {
  if (!input) return "";
  if (input.command) return input.command;
  if (input.url) return input.url;
  if (input.query) return typeof input.query === "string" ? input.query : JSON.stringify(input.query);
  if (input.action) {
    let s = input.action;
    if (input.text) s += `: ${input.text}`;
    if (input.coordinate) s += ` @ [${input.coordinate}]`;
    if (input.ref) s += ` ref=${input.ref}`;
    return s;
  }
  if (input.description) return input.description;
  if (input.path) return input.path;
  if (input.filter) return `filter=${input.filter}`;
  if (input.createIfEmpty != null) return `createIfEmpty: ${input.createIfEmpty}`;
  const keys = Object.keys(input);
  if (keys.length === 0) return "{}";
  if (keys.length <= 2) return keys.map((k) => `${k}: ${JSON.stringify(input[k]).slice(0, 40)}`).join(", ");
  return `{${keys.join(", ")}}`;
}

function parseSession(raw) {
  const lines = raw.trim().split("\n").filter(Boolean);
  const events = [];
  let badLineCount = 0;

  for (const line of lines) {
    try {
      events.push(JSON.parse(line));
    } catch {
      badLineCount++;
    }
  }

  if (events.length === 0) {
    return { error: "No valid JSON lines found", events: [] };
  }

  const init = events.find((e) => e.type === "system" && e.subtype === "init");
  const result = events.find((e) => e.type === "result");

  // Accumulate token usage from stream events
  const tokenAccum = {};
  for (const evt of events) {
    if (evt.type === "stream_event" && evt.event?.type === "message_delta" && evt.event?.usage) {
      const u = evt.event.usage;
      const key = "stream_total";
      if (!tokenAccum[key]) tokenAccum[key] = { input: 0, output: 0, cacheRead: 0, cacheCreate: 0 };
      tokenAccum[key].input += u.input_tokens || 0;
      tokenAccum[key].output += u.output_tokens || 0;
      tokenAccum[key].cacheRead += u.cache_read_input_tokens || 0;
      tokenAccum[key].cacheCreate += u.cache_creation_input_tokens || 0;
    }
  }

  // Build conversation turns
  const turns = [];
  const seenTexts = new Set();

  for (const evt of events) {
    if (evt.type === "assistant" && evt.message?.content) {
      for (const block of evt.message.content) {
        if (block.type === "tool_use") {
          turns.push({ role: "tool_call", name: block.name, input: block.input, id: block.id });
        } else if (block.type === "text" && block.text?.trim()) {
          const txt = block.text.trim();
          if (!seenTexts.has(txt)) {
            seenTexts.add(txt);
            turns.push({ role: "assistant", text: txt });
          }
        }
      }
    }

    if (evt.type === "user") {
      const content = evt.message?.content;
      if (Array.isArray(content)) {
        for (const block of content) {
          if (block.type === "tool_result") {
            let text = extractTextFromContent(block.content);
            // Also check tool_use_result on parent event
            if (!text && evt.tool_use_result) {
              text = extractTextFromContent(evt.tool_use_result);
            }
            turns.push({
              role: "tool_result",
              toolId: block.tool_use_id,
              content: text,
              isError: block.is_error || false,
            });
          } else if (block.type === "text") {
            const txt = (block.text || "").trim();
            // Skip tab context duplicates that are just annotation
            if (txt && !seenTexts.has(txt)) {
              seenTexts.add(txt);
              turns.push({ role: "user", text: txt });
            }
          }
        }
      }
    }
  }

  return {
    init,
    result,
    turns,
    tokenAccum,
    totalParsed: events.length,
    badLines: badLineCount,
    isPartial: !result,
  };
}

function Badge({ children, color = C.accent, bg }) {
  return (
    <span
      style={{
        display: "inline-block",
        padding: "2px 7px",
        borderRadius: "4px",
        fontSize: "10.5px",
        fontWeight: 600,
        letterSpacing: "0.02em",
        color,
        background: bg || `${color}18`,
        fontFamily: "'SF Mono', 'Fira Code', 'Cascadia Code', monospace",
        whiteSpace: "nowrap",
      }}
    >
      {children}
    </span>
  );
}

function ToolCallBlock({ name, input, id }) {
  const [open, setOpen] = useState(false);
  const short = shortToolName(name);
  const preview = toolPreview(name, input);

  return (
    <div style={{ margin: "6px 0" }}>
      <div
        onClick={() => setOpen(!open)}
        style={{
          display: "flex",
          alignItems: "center",
          gap: "8px",
          cursor: "pointer",
          padding: "9px 12px",
          background: C.surface,
          border: `1px solid ${C.border}`,
          borderRadius: open ? "8px 8px 0 0" : "8px",
          transition: "background 0.12s",
        }}
        onMouseEnter={(e) => (e.currentTarget.style.background = C.surfaceHover)}
        onMouseLeave={(e) => (e.currentTarget.style.background = C.surface)}
      >
        <span
          style={{
            color: C.textDim,
            fontSize: "10px",
            transform: open ? "rotate(90deg)" : "none",
            transition: "transform 0.12s",
            flexShrink: 0,
          }}
        >
          ▶
        </span>
        <Badge color={C.purple}>{short}</Badge>
        {preview && (
          <code
            style={{
              color: C.textMuted,
              fontSize: "11.5px",
              fontFamily: "'SF Mono', 'Fira Code', monospace",
              overflow: "hidden",
              textOverflow: "ellipsis",
              whiteSpace: "nowrap",
              flex: 1,
              minWidth: 0,
            }}
          >
            {preview}
          </code>
        )}
      </div>
      {open && (
        <pre
          style={{
            margin: 0,
            padding: "11px 13px",
            background: "#09090b",
            borderLeft: `2px solid ${C.purple}40`,
            borderRight: `1px solid ${C.border}`,
            borderBottom: `1px solid ${C.border}`,
            borderRadius: "0 0 8px 8px",
            fontSize: "11.5px",
            color: C.textMuted,
            overflow: "auto",
            maxHeight: "320px",
            fontFamily: "'SF Mono', 'Fira Code', monospace",
            lineHeight: 1.55,
            whiteSpace: "pre-wrap",
            wordBreak: "break-word",
          }}
        >
          {JSON.stringify(input, null, 2)}
        </pre>
      )}
    </div>
  );
}

function ToolResultBlock({ content, isError }) {
  const [expanded, setExpanded] = useState(false);
  const text = content || "(empty result)";
  const lines = text.split("\n");
  const hasMore = lines.length > 4;
  const preview = lines.slice(0, 4).join("\n");
  const borderColor = isError ? C.red : C.green;
  const textColor = isError ? C.red : `${C.green}cc`;

  return (
    <div style={{ margin: "2px 0 6px 0" }}>
      <pre
        style={{
          margin: 0,
          padding: "9px 13px",
          background: isError ? `${C.red}08` : `${C.green}06`,
          borderLeft: `2px solid ${borderColor}50`,
          borderRadius: "6px",
          fontSize: "11.5px",
          color: textColor,
          overflow: "auto",
          maxHeight: expanded ? "500px" : "100px",
          fontFamily: "'SF Mono', 'Fira Code', monospace",
          lineHeight: 1.5,
          cursor: hasMore ? "pointer" : "default",
          whiteSpace: "pre-wrap",
          wordBreak: "break-word",
        }}
        onClick={() => hasMore && setExpanded(!expanded)}
      >
        {expanded ? text : preview}
        {!expanded && hasMore && (
          <span style={{ color: C.textDim }}>
            {"\n"}… {lines.length - 4} more lines (click to expand)
          </span>
        )}
      </pre>
    </div>
  );
}

function AssistantBlock({ text }) {
  return (
    <div
      style={{
        margin: "6px 0",
        padding: "10px 14px",
        color: C.text,
        fontSize: "13.5px",
        lineHeight: 1.6,
        whiteSpace: "pre-wrap",
        wordBreak: "break-word",
      }}
    >
      {text}
    </div>
  );
}

function UserBlock({ text }) {
  return (
    <div
      style={{
        margin: "10px 0",
        padding: "10px 14px",
        background: `${C.blue}0c`,
        borderLeft: `2px solid ${C.blue}50`,
        borderRadius: "6px",
        fontSize: "13.5px",
        color: C.text,
        lineHeight: 1.6,
        whiteSpace: "pre-wrap",
        wordBreak: "break-word",
      }}
    >
      <span style={{ fontSize: "10px", color: C.blue, fontWeight: 600, letterSpacing: "0.04em", display: "block", marginBottom: "4px" }}>
        USER
      </span>
      {text}
    </div>
  );
}

function MetaPanel({ init, result, isPartial, totalParsed }) {
  const items = [];

  if (init?.model) items.push({ label: "Model", value: <Badge color={C.blue}>{init.model}</Badge> });
  if (init?.cwd) items.push({ label: "Directory", value: <code style={{ fontSize: "11.5px", color: C.textMuted, fontFamily: "monospace" }}>{init.cwd}</code> });
  if (init?.claude_code_version) items.push({ label: "CC Version", value: <span style={{ fontSize: "12.5px", color: C.text }}>{init.claude_code_version}</span> });
  if (init?.permissionMode) items.push({ label: "Permissions", value: <Badge color={init.permissionMode === "bypassPermissions" ? C.orange : C.green}>{init.permissionMode}</Badge> });
  if (result?.duration_ms != null) {
    items.push({
      label: "Duration",
      value: (
        <span style={{ fontSize: "12.5px", color: C.text }}>
          {(result.duration_ms / 1000).toFixed(1)}s
          {result.duration_api_ms != null && <span style={{ color: C.textDim, marginLeft: "6px", fontSize: "11px" }}>(API: {(result.duration_api_ms / 1000).toFixed(1)}s)</span>}
        </span>
      ),
    });
  }
  if (result?.num_turns != null) items.push({ label: "Turns", value: <span style={{ fontSize: "12.5px", color: C.text }}>{result.num_turns}</span> });
  if (result?.total_cost_usd != null) items.push({ label: "Cost", value: <span style={{ fontSize: "12.5px", color: C.yellow }}>${result.total_cost_usd.toFixed(4)}</span> });
  if (result?.subtype) items.push({ label: "Status", value: <Badge color={result.subtype === "success" ? C.green : C.red}>{result.subtype}</Badge> });

  items.push({ label: "Events Parsed", value: <span style={{ fontSize: "12.5px", color: C.text }}>{totalParsed}</span> });

  if (isPartial) {
    items.push({
      label: "State",
      value: <Badge color={C.orange} bg={`${C.orange}20`}>● IN PROGRESS / PARTIAL</Badge>,
    });
  }

  if (init?.mcp_servers?.length > 0) {
    items.push({
      label: "MCP Servers",
      value: (
        <span style={{ display: "flex", gap: "4px", flexWrap: "wrap" }}>
          {init.mcp_servers.map((s, i) => (
            <Badge key={i} color={s.status === "connected" ? C.green : C.red}>
              {s.name} ({s.status})
            </Badge>
          ))}
        </span>
      ),
    });
  }

  if (items.length === 0) return null;

  return (
    <div
      style={{
        display: "grid",
        gridTemplateColumns: "repeat(auto-fill, minmax(180px, 1fr))",
        gap: "10px",
        padding: "14px 16px",
        background: C.surface,
        border: `1px solid ${C.border}`,
        borderRadius: "10px",
        marginBottom: "16px",
      }}
    >
      {items.map((item, i) => (
        <div key={i}>
          <div style={{ fontSize: "9.5px", color: C.textDim, textTransform: "uppercase", letterSpacing: "0.08em", marginBottom: "4px" }}>{item.label}</div>
          {item.value}
        </div>
      ))}
    </div>
  );
}

function TokenPanel({ result, tokenAccum }) {
  if (!result?.modelUsage && Object.keys(tokenAccum).length === 0) return null;

  const rows = result?.modelUsage ? Object.entries(result.modelUsage) : [];

  return (
    <div
      style={{
        padding: "12px 16px",
        background: C.surface,
        border: `1px solid ${C.border}`,
        borderRadius: "10px",
        marginBottom: "16px",
      }}
    >
      <div style={{ fontSize: "9.5px", color: C.textDim, textTransform: "uppercase", letterSpacing: "0.08em", marginBottom: "8px" }}>Token Usage</div>
      {rows.map(([model, usage]) => (
        <div key={model} style={{ display: "flex", alignItems: "center", gap: "10px", padding: "5px 0", borderBottom: `1px solid ${C.border}30`, flexWrap: "wrap" }}>
          <Badge color={C.blue}>{model}</Badge>
          <span style={{ fontSize: "11px", color: C.textMuted, fontFamily: "monospace" }}>
            in: {(usage.inputTokens || 0).toLocaleString()}
            {usage.cacheReadInputTokens > 0 && <span style={{ color: C.green }}> (cache-read: {usage.cacheReadInputTokens.toLocaleString()})</span>}
            {usage.cacheCreationInputTokens > 0 && <span style={{ color: C.cyan }}> (cache-write: {usage.cacheCreationInputTokens.toLocaleString()})</span>}
            {" · "}out: {(usage.outputTokens || 0).toLocaleString()}
            {" · "}
            <span style={{ color: C.yellow }}>${(usage.costUSD || 0).toFixed(4)}</span>
          </span>
        </div>
      ))}
      {rows.length === 0 && Object.keys(tokenAccum).length > 0 && (
        <div style={{ fontSize: "11px", color: C.textMuted, fontFamily: "monospace" }}>
          {Object.entries(tokenAccum).map(([k, v]) => (
            <span key={k}>Streamed totals — in: {v.input.toLocaleString()}, out: {v.output.toLocaleString()}, cache-read: {v.cacheRead.toLocaleString()}</span>
          ))}
        </div>
      )}
    </div>
  );
}

const PLACEHOLDER = `Paste your Claude Code session log here…

Each line should be a JSON object. Works with complete or partial/in-progress logs.
Supported event types: system, stream_event, assistant, user, result`;

export default function ClaudeCodeLogViewer() {
  const [raw, setRaw] = useState("");
  const [collapsed, setCollapsed] = useState(true);

  const parsed = useMemo(() => (raw.trim() ? parseSession(raw) : null), [raw]);

  const handlePaste = useCallback((e) => {
    const text = e.clipboardData?.getData("text");
    if (text && text.length > 50000) {
      e.preventDefault();
      setRaw(text);
    }
  }, []);

  return (
    <div style={{ background: C.bg, minHeight: "100vh", color: C.text, fontFamily: "-apple-system, BlinkMacSystemFont, 'Segoe UI', system-ui, sans-serif" }}>
      <div style={{ maxWidth: "820px", margin: "0 auto", padding: "28px 20px" }}>
        <div style={{ marginBottom: "20px" }}>
          <h1 style={{ fontSize: "18px", fontWeight: 700, margin: "0 0 3px 0", color: C.text, letterSpacing: "-0.02em" }}>
            Claude Code Log Viewer
          </h1>
          <p style={{ fontSize: "12.5px", color: C.textDim, margin: 0 }}>
            Paste a session log (newline-delimited JSON). Handles complete and partial/in-progress sessions.
          </p>
        </div>

        <div style={{ marginBottom: "16px" }}>
          <textarea
            value={raw}
            onChange={(e) => setRaw(e.target.value)}
            onPaste={handlePaste}
            placeholder={PLACEHOLDER}
            style={{
              width: "100%",
              minHeight: collapsed && raw ? "60px" : "110px",
              maxHeight: collapsed && raw ? "60px" : "300px",
              padding: "12px",
              background: C.surface,
              border: `1px solid ${C.border}`,
              borderRadius: "8px",
              color: C.textMuted,
              fontSize: "11.5px",
              fontFamily: "'SF Mono', 'Fira Code', monospace",
              resize: "vertical",
              outline: "none",
              boxSizing: "border-box",
              lineHeight: 1.5,
            }}
          />
          {raw && (
            <div style={{ display: "flex", gap: "8px", marginTop: "6px" }}>
              <button
                onClick={() => setCollapsed(!collapsed)}
                style={{
                  background: "none",
                  border: `1px solid ${C.border}`,
                  borderRadius: "5px",
                  color: C.textMuted,
                  fontSize: "11px",
                  padding: "3px 10px",
                  cursor: "pointer",
                  fontFamily: "inherit",
                }}
              >
                {collapsed ? "Expand input" : "Collapse input"}
              </button>
              <button
                onClick={() => { setRaw(""); setCollapsed(true); }}
                style={{
                  background: "none",
                  border: `1px solid ${C.border}`,
                  borderRadius: "5px",
                  color: C.textDim,
                  fontSize: "11px",
                  padding: "3px 10px",
                  cursor: "pointer",
                  fontFamily: "inherit",
                }}
              >
                Clear
              </button>
            </div>
          )}
        </div>

        {parsed?.error && (
          <div style={{ padding: "10px 14px", background: `${C.red}10`, border: `1px solid ${C.red}30`, borderRadius: "8px", color: C.red, fontSize: "12.5px", marginBottom: "14px" }}>
            {parsed.error}
          </div>
        )}

        {parsed && !parsed.error && (
          <>
            <MetaPanel init={parsed.init} result={parsed.result} isPartial={parsed.isPartial} totalParsed={parsed.totalParsed} />
            <TokenPanel result={parsed.result} tokenAccum={parsed.tokenAccum} />

            <div style={{ fontSize: "9.5px", color: C.textDim, textTransform: "uppercase", letterSpacing: "0.08em", marginBottom: "10px", display: "flex", alignItems: "center", gap: "8px" }}>
              <span>Conversation ({parsed.turns.length} blocks)</span>
              {parsed.isPartial && <Badge color={C.orange}>LIVE / PARTIAL</Badge>}
            </div>

            {parsed.turns.map((turn, i) => {
              switch (turn.role) {
                case "tool_call":
                  return <ToolCallBlock key={i} name={turn.name} input={turn.input} id={turn.id} />;
                case "tool_result":
                  return <ToolResultBlock key={i} content={turn.content} isError={turn.isError} />;
                case "assistant":
                  return <AssistantBlock key={i} text={turn.text} />;
                case "user":
                  return <UserBlock key={i} text={turn.text} />;
                default:
                  return null;
              }
            })}

            {parsed.result?.result && (
              <div style={{ marginTop: "16px", padding: "14px", background: `${C.green}08`, border: `1px solid ${C.green}20`, borderRadius: "10px" }}>
                <div style={{ fontSize: "9.5px", color: C.greenDim, textTransform: "uppercase", letterSpacing: "0.08em", marginBottom: "6px" }}>Final Result</div>
                <div style={{ fontSize: "13px", color: C.text, whiteSpace: "pre-wrap", lineHeight: 1.6 }}>
                  {parsed.result.result}
                </div>
              </div>
            )}

            {parsed.badLines > 0 && (
              <div style={{ marginTop: "12px", fontSize: "11px", color: C.textDim }}>
                ⚠ {parsed.badLines} line(s) couldn't be parsed (possibly truncated)
              </div>
            )}
          </>
        )}
      </div>
    </div>
  );
}
```