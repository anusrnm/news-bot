/**
 * Release Checker for Deno Deploy
 * Cron-triggered job that monitors software releases and sends Telegram notifications
 * Requirements:
 * - Deno Deploy environment with cron and KV (Create and attach) support
 * - Telegram Bot API token and target chat ID (set as environment variables)
 * 
 * Resource-aware design:
 * - ~11 API calls per run × 48 runs/day = ~528 requests/day (well under 10k limit)
 * - Small JSON payloads = minimal bandwidth usage
 * - Efficient async/await = low CPU time per execution
 */

// Configuration: Repositories and their check methods
const REPOS: Record<string, { path?: string; method: string }> = {
  "Node.js LTS": { method: "node_lts" },
  "Node.js": { path: "nodejs/node", method: "release" },
  "Monaco": { path: "microsoft/monaco-editor", method: "release" },
  "Spring Framework": { path: "spring-projects/spring-framework", method: "release" },
  "Spring Boot": { path: "spring-projects/spring-boot", method: "release" },
  "Bun": { path: "oven-sh/bun", method: "release" },
  "Deno": { path: "denoland/deno", method: "release" },
  "Rust": { path: "rust-lang/rust", method: "release" },
  "Python": { path: "python/cpython", method: "tag" },
  "Nim": { path: "nim-lang/Nim", method: "tag" },
  "Go": { path: "golang/go", method: "go_api" }
};

// Environment variables (set in Deno Deploy dashboard)
const TOKEN = Deno.env.get("TELEGRAM_BOT_TOKEN");
const CHAT_ID = Deno.env.get("TELEGRAM_CHAT_ID");
const GITHUB_TOKEN = Deno.env.get("GITHUB_TOKEN"); // Optional: increases GitHub rate limits

// Initialize Deno KV for persistent state storage
const KV = await Deno.openKv();

// Logger: console.log is captured by Deno Deploy logs
function log(level: string, message: string): void {
  console.log(`${new Date().toISOString()} - ${level} - ${message}`);
}

// Send notification to Telegram
async function sendTelegram(message: string): Promise<void> {
  if (!TOKEN || !CHAT_ID) {
    log("ERROR", "Telegram credentials not configured");
    return;
  }

  const url = `https://api.telegram.org/bot${TOKEN}/sendMessage`;
  const payload = {
    chat_id: CHAT_ID,
    text: message,
    parse_mode: "Markdown"
  };

  try {
    const response = await fetch(url, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload),
    });

    if (!response.ok) {
      const errorText = await response.text().catch(() => "No response body");
      log("ERROR", `Telegram API Error: ${response.status} - ${errorText}`);
      return;
    }

    log("INFO", "Successfully sent Telegram message");
  } catch (error) {
    log("ERROR", `Telegram connection error: ${error}`);
  }
}

// Load previous versions from Deno KV
async function loadState(): Promise<Record<string, string>> {
  try {
    const entry = await KV.get<string[]>(["release_state"]);
    if (entry.value) {
      // Reconstruct object from flattened [key, value, key, value...] array
      const state: Record<string, string> = {};
      for (let i = 0; i < entry.value.length; i += 2) {
        state[entry.value[i]] = entry.value[i + 1];
      }
      return state;
    }
  } catch (error) {
    log("ERROR", `Failed to load state: ${error}`);
  }
  return {};
}

// Save current versions to Deno KV
async function saveState(state: Record<string, string>): Promise<void> {
  try {
    // Flatten object to array for KV storage
    const entries: string[] = [];
    for (const [key, value] of Object.entries(state)) {
      entries.push(key, value);
    }
    await KV.set(["release_state"], entries);
  } catch (error) {
    log("ERROR", `Failed to save state: ${error}`);
  }
}

// Fetch latest version for a given repository
async function getVersion(
  name: string, 
  config: { path?: string; method: string }
): Promise<[string | null, string | null]> {
  const timeout = AbortSignal.timeout(10000); // 10 second timeout per request

  try {
    // ── Node.js LTS (special endpoint) ──
    if (config.method === "node_lts") {
      const res = await fetch("https://nodejs.org/download/release/index.json", { signal: timeout });
      if (res.ok) {
        const data = await res.json();
        const latestLts = data.find((v: any) => v.lts !== false);
        if (latestLts) {
          const ver = latestLts.version;
          return [ver, `https://github.com/nodejs/node/releases/tag/${ver}`];
        }
      }
    }
    
    // ── Go (official API) ──
    else if (config.method === "go_api") {
      const res = await fetch("https://go.dev/dl/?mode=json", { signal: timeout });
      if (res.ok) {
        const data = await res.json();
        return [data[0].version, `https://go.dev/dl/${data[0].version}`];
      }
    }
    
    // ── GitHub Releases ──
    else if (config.method === "release" && config.path) {
      const headers: Record<string, string> = {};
      if (GITHUB_TOKEN) headers["Authorization"] = `Bearer ${GITHUB_TOKEN}`;
      
      const res = await fetch(
        `https://api.github.com/repos/${config.path}/releases/latest`, 
        { headers, signal: timeout }
      );
      
      if (res.ok) {
        const data = await res.json();
        return [data.tag_name, data.html_url];
      } else if (res.status === 403) {
        log("WARN", `GitHub rate limit hit for ${name}`);
      }
    }
    
    // ── GitHub Tags (fallback for repos without releases) ──
    else if (config.method === "tag" && config.path) {
      const headers: Record<string, string> = {};
      if (GITHUB_TOKEN) headers["Authorization"] = `Bearer ${GITHUB_TOKEN}`;
      
      const res = await fetch(
        `https://api.github.com/repos/${config.path}/tags`, 
        { headers, signal: timeout }
      );
      
      if (res.ok) {
        const data = await res.json();
        if (Array.isArray(data) && data.length > 0) {
          const tagName = data[0].name;
          return [tagName, `https://github.com/${config.path}/releases/tag/${tagName}`];
        }
      } else if (res.status === 403) {
        log("WARN", `GitHub rate limit hit for ${name}`);
      }
    }
  } catch (error) {
    log("ERROR", `Error fetching ${name}: ${error}`);
  }
  
  return [null, null];
}

// Main execution logic
async function main(): Promise<void> {
  log("INFO", "Starting release check cycle");
  const state = await loadState();
  
  for (const [name, config] of Object.entries(REPOS)) {
    const [version, url] = await getVersion(name, config);
    
    if (version && state[name] !== version) {
      // Only notify if this isn't the first time seeing this repo
      if (name in state) {
        const msg = `🚀 *${name} Update!*\nVersion: \`${version}\`\n[View Details](${url})`;
        await sendTelegram(msg);
      }
      
      // Update state
      state[name] = version;
      await saveState(state);
      log("INFO", `Updated ${name}: ${version}`);
    }
    
    // Small delay to avoid hitting rate limits (500ms × 11 repos = ~5.5s total)
    await new Promise(resolve => setTimeout(resolve, 500));
  }
  
  log("INFO", "Release check cycle complete");
}

// ── Cron Handler (runs on schedule) ──
Deno.cron("Check software releases", "0 8 * * *", async () => {
  await main();
});

// ── HTTP Handler (for health checks & manual triggers) ──
Deno.serve(async (req: Request): Promise<Response> => {
  const url = new URL(req.url);
  
  // Health check endpoint
  if (url.pathname === "/health" && req.method === "GET") {
    return new Response("OK", { 
      status: 200,
      headers: { "Content-Type": "text/plain" }
    });
  }

  // ── NEW: Send Telegram message with current state ──
  if (url.pathname === "/notify-state" && req.method === "POST") {
    // Require auth token for safety (sending notifications is intentional)
    // const notifyToken = Deno.env.get("NOTIFY_TOKEN");
    // if (notifyToken) {
    //   const authHeader = req.headers.get("Authorization");
    //   if (authHeader !== `Bearer ${notifyToken}`) {
    //     return new Response("Unauthorized", { status: 401 });
    //   }
    // }
    
    try {
      const state = await loadState();
      
      // Format a clean Telegram message with all versions
      let message = "📋 *Current Tracked Versions*\n\n";
      
      // Sort repos alphabetically for consistent output
      const sortedRepos = Object.keys(REPOS).sort();
      
      for (const name of sortedRepos) {
        const version = state[name] ?? "❓ unknown";
        message += `• *${name}*: \`${version}\`\n`;
      }
      
      message += `\n_Updated: ${new Date().toISOString()}_`;
      
      // Send via Telegram
      await sendTelegram(message);
      
      log("INFO", "State notification sent to Telegram");
      
      return new Response(JSON.stringify({ 
        success: true, 
        sent: Object.keys(state).length,
        timestamp: new Date().toISOString()
      }), {
        status: 200,
        headers: { "Content-Type": "application/json" }
      });
      
    } catch (error) {
      log("ERROR", `Failed to send state notification: ${error}`);
      return new Response(JSON.stringify({ error: "Failed to send notification" }), {
        status: 500,
        headers: { "Content-Type": "application/json" }
      });
    }
  }
  
  // Manual trigger endpoint (optional auth)
  if (url.pathname === "/trigger" && req.method === "POST") {
    const triggerToken = Deno.env.get("TRIGGER_TOKEN");
    if (triggerToken) {
      const authHeader = req.headers.get("Authorization");
      if (authHeader !== `Bearer ${triggerToken}`) {
        return new Response("Unauthorized", { status: 401 });
      }
    }
    
    // Execute in background (don't await to avoid timeout)
    main().catch(error => log("ERROR", `Triggered run failed: ${error}`));
    return new Response("Triggered", { 
      status: 202,
      headers: { "Content-Type": "text/plain" }
    });
  }
  
  return new Response("Not Found", { 
    status: 404,
    headers: { "Content-Type": "text/plain" }
  });
});
