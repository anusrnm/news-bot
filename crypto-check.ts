// ==========================================
// Configuration
// ==========================================
const CONFIG = {
  // List of CoinGecko IDs to track
  coins: ["beldex","solana"], 
  // Target currency
  currency: "inr", 
  // Cron schedule: "0 9 * * *" means every day at 09:00 AM
  cronSchedule: "0 8 * * *", 
  port: 8000,
};

// Environment Variables
const TELEGRAM_BOT_TOKEN = Deno.env.get("TELEGRAM_BOT_TOKEN");
const TELEGRAM_CHAT_ID = Deno.env.get("TELEGRAM_CHAT_ID");

if (!TELEGRAM_BOT_TOKEN || !TELEGRAM_CHAT_ID) {
  console.error("Error: TELEGRAM_BOT_TOKEN and TELEGRAM_CHAT_ID must be set.");
  Deno.exit(1);
}

// Initialize Deno KV for persistent state storage
const KV = await Deno.openKv();

// ==========================================
// State Persistence
// ==========================================
interface PriceState {
  [coinId: string]: {
    price: number;
    lastUpdated: string;
  };
}

async function loadState(): Promise<PriceState> {
  try {
    const entry = await KV.get<string[]>(["crypto_price_state"]);
    if (entry.value) {
      // Reconstruct object from flattened [key, value, key, value...] array
      const state: PriceState = {};
      for (let i = 0; i < entry.value.length; i += 2) {
        const key = entry.value[i];
        const valueStr = entry.value[i + 1];
        state[key] = JSON.parse(valueStr);
      }
      return state;
    }
  } catch (error) {
    console.error(`[State Load Error] ${error}`);
  }
  return {}; // Return empty state if KV is empty or error occurs
}

async function saveState(state: PriceState) {
  try {
    // Flatten object to array for KV storage
    const entries: string[] = [];
    for (const [key, value] of Object.entries(state)) {
      entries.push(key, JSON.stringify(value));
    }
    await KV.set(["crypto_price_state"], entries);
  } catch (error) {
    console.error(`[State Save Error] ${error}`);
  }
}

// ==========================================
// API & Telegram Functions
// ==========================================
async function fetchPrices(): Promise<Record<string, Record<string, number>> | null> {
  try {
    const ids = CONFIG.coins.join(",");
    const url = `https://api.coingecko.com/api/v3/simple/price?ids=${ids}&vs_currencies=${CONFIG.currency}`;
    const response = await fetch(url);
    
    if (!response.ok) throw new Error(`HTTP ${response.status}`);
    return await response.json();
  } catch (error) {
    console.error(`[Fetch Error] ${error.message}`);
    return null;
  }
}

async function sendTelegramAlert(message: string): Promise<void> {
  const url = `https://api.telegram.org/bot${TELEGRAM_BOT_TOKEN}/sendMessage`;
  try {
    const response = await fetch(url, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        chat_id: TELEGRAM_CHAT_ID,
        text: message,
        parse_mode: "Markdown",
      }),
    });
    if (!response.ok) console.error(`[Telegram Error] ${await response.text()}`);
    else console.log("[Telegram] Alert sent.");
  } catch (error) {
    console.error(`[Telegram Network Error] ${error.message}`);
  }
}

// ==========================================
// Daily Cron Job Logic
// ==========================================
let lastRunStatus = "Pending first run";

async function runDailyCheck() {
  console.log(`[Cron] Running daily price check at ${new Date().toISOString()}`);
  lastRunStatus = "Running...";
  
  const prices = await fetchPrices();
  if (!prices) {
    lastRunStatus = "Failed: API Error";
    return;
  }

  const previousState = await loadState();
  const newState: PriceState = {};
  const changes: string[] = [];

  for (const coin of CONFIG.coins) {
    const currentPrice = prices[coin]?.[CONFIG.currency];
    if (currentPrice === undefined) continue;

    const prev = previousState[coin]?.price;
    newState[coin] = { price: currentPrice, lastUpdated: new Date().toISOString() };

    // Check if price changed or if it's the first time tracking
    if (prev !== undefined && prev !== currentPrice) {
      const diff = currentPrice - prev;
      const percent = ((diff / prev) * 100).toFixed(2);
      const emoji = diff > 0 ? "📈" : "📉";
      changes.push(`${emoji} *${coin.toUpperCase()}*: ${CONFIG.currency.toUpperCase()} ${currentPrice} (${diff > 0 ? '+' : ''}${percent}%)`);
    } else if (prev === undefined) {
      changes.push(`🆕 *${coin.toUpperCase()}*: ${CONFIG.currency.toUpperCase()} ${currentPrice} (Initial tracking)`);
    }
  }

  if (changes.length > 0) {
    const msg = changes.join("\n") + `\n\n📊 *Daily Crypto Update*`;
    await sendTelegramAlert(msg);
  } else {
    console.log("[Cron] No price changes detected. Skipping Telegram alert.");
  }

  await saveState(newState);
  lastRunStatus = "Success";
  console.log("[Cron] Daily check completed and state saved.");
}

// ==========================================
// Server & Cron Initialization
// ==========================================

// Setup Built-in Deno Cron Job
Deno.cron("daily-crypto-check", CONFIG.cronSchedule, async () => {
  await runDailyCheck();
});

console.log(`[Cron] Scheduled daily crypto check using Deno.cron. Schedule: ${CONFIG.cronSchedule}`);

// Optional: Run immediately on startup for testing (comment out in production)
// runDailyCheck(); 

// HTTP Server for status monitoring
Deno.serve({ port: CONFIG.port }, async (_req) => {
  const state = await loadState();
  
  const status = {
    config: {
      coins: CONFIG.coins,
      currency: CONFIG.currency,
      schedule: CONFIG.cronSchedule,
    },
    tracker: {
      lastRunStatus,
    },
    currentState: state,
  };

  return new Response(JSON.stringify(status, null, 2), {
    headers: { "Content-Type": "application/json" },
  });
});

console.log(`[Server] Status endpoint running at http://localhost:${CONFIG.port}`);
