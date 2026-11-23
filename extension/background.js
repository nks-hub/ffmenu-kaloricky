// Kalorické tabulky client, same protocol as ffkt/kt.py (legacy XML API of KT Android 3.14.71).
if (typeof md5 === "undefined") importScripts("md5.js");

const KT_URL = "https://www.dine4fit.com/";
// app version code and client id that the Android app appends to every legacy request
const APP_PARAMS = { v: "621", pid: "aNdV2wl7" };
const KJ_PER_KCAL = 4.1871;
// 450 = logged out, 451 = token belongs to another user; both are fixed by logging in again
const SESSION_LOST = new Set([450, 451]);
// waits between attempts after "503 No server is available" from KT's load balancer (see RETRY_DELAYS in ffkt/kt.py)
const RETRY_DELAYS_MS = [2000, 5000];
// diary time written for each KT slot (ID_Cas 1-6)
const SLOT_TIMES = { 1: "07:00", 2: "10:00", 3: "12:00", 4: "15:00", 5: "18:00", 6: "20:00" };

class KTError extends Error {
  constructor(code, message) {
    super(`${code}: ${message}`);
    this.code = code;
  }
}

function field(xml, name) {
  const match = xml.match(new RegExp(`<${name}>([^<]*)</${name}>`));
  if (!match) return null;
  return match[1].replace(/&lt;/g, "<").replace(/&gt;/g, ">").replace(/&quot;/g, '"').replace(/&amp;/g, "&");
}

async function ktRequest(path, params, body) {
  const url = new URL(path, KT_URL);
  for (const [name, value] of Object.entries({ ...params, ...APP_PARAMS })) url.searchParams.set(name, value);
  let response;
  for (const delay of [...RETRY_DELAYS_MS, null]) {
    response = await fetch(url, body && {
      method: "POST",
      headers: { "Content-Type": "application/json; charset=UTF-8" },
      body: JSON.stringify(body),
    });
    if (response.status !== 503 || delay === null) break;
    await new Promise((resolve) => setTimeout(resolve, delay));
  }
  const xml = await response.text();
  if (!response.ok) throw new KTError(response.status, response.statusText);
  if (/^\s*(<\?xml[^>]*\?>\s*)?<result[\s>]/.test(xml)) {
    const code = Number(field(xml, "code"));
    if (!(code >= 200 && code < 300)) throw new KTError(code, field(xml, "msg") || "");
  }
  return xml;
}

async function session(fresh) {
  const stored = await chrome.storage.local.get(["email", "passwordMd5", "hash", "unit"]);
  if (!stored.email || !stored.passwordMd5) {
    throw new KTError(0, "v nastavení doplňku chybí přihlášení do Kalorických tabulek");
  }
  if (stored.hash && !fresh) return stored;
  const hash = field(await ktRequest("login.api.php", { Email: stored.email, Pass: stored.passwordMd5 }), "hash");
  if (!hash) throw new KTError(0, "přihlášení nevrátilo hash uživatele");
  // the app assumes kcal when the account has no preferred unit
  const unit = (field(await ktRequest("getInfo.php", { HASH_Uzivatel: hash }), "preferUnit") || "kcal").toLowerCase();
  await chrome.storage.local.set({ hash, unit });
  return { ...stored, hash, unit };
}

async function withSession(call) {
  try {
    return await call(await session(false));
  } catch (error) {
    if (!SESSION_LOST.has(error.code)) throw error;
    return call(await session(true));
  }
}

function validMeal(meal, date) {
  const numbers = ["kj", "protein", "carbs", "fat", "fiber", "cholesterol"];
  return meal && /^\d+:\d{4}-\d\d-\d\d:\d+$/.test(meal.key) && /^\d{4}-\d\d-\d\d$/.test(date)
    && typeof meal.name === "string" && meal.name.trim() && meal.dayTime in SLOT_TIMES
    && numbers.every((n) => Number.isFinite(meal[n]) && meal[n] >= 0);
}

async function addMeal(meal, date) {
  if (!validMeal(meal, date)) throw new KTError(0, "jídlo na stránce se nepodařilo přečíst");
  const storageKey = `added:${date}`;
  const added = (await chrome.storage.local.get(storageKey))[storageKey] || [];
  if (added.includes(meal.key)) return "already";
  await withSession((s) => ktRequest("addPrijem.php", { HASH_Uzivatel: s.hash }, {
    Datum: date,
    Cas: SLOT_TIMES[meal.dayTime],
    ID_Cas: meal.dayTime,
    Polozky: [{
      Typ: "vlozenaHodnota",
      Nazev: `FF Menu: ${meal.name}`,
      Energie: s.unit === "kj" ? meal.kj : Math.round((meal.kj / KJ_PER_KCAL) * 10) / 10,
      Bilkoviny: meal.protein,
      Sacharidy: meal.carbs,
      Tuky: meal.fat,
      Vlaknina: meal.fiber,
      Cholesterol: meal.cholesterol,
    }],
  }));
  added.push(meal.key);
  await chrome.storage.local.set({ [storageKey]: added });
  return "added";
}

async function addedOn(dates) {
  const stored = await chrome.storage.local.get(dates.map((d) => `added:${d}`));
  return Object.fromEntries(dates.map((d) => [d, stored[`added:${d}`] || []]));
}

async function credentialsSet() {
  const { email, passwordMd5 } = await chrome.storage.local.get(["email", "passwordMd5"]);
  return Boolean(email && passwordMd5);
}

const handlers = {
  add: (m) => addMeal(m.meal, m.date),
  added: (m) => addedOn(m.dates),
  status: () => credentialsSet(),
  login: async () => (await session(true)).unit,
  openOptions: () => chrome.runtime.openOptionsPage(),
};

chrome.runtime.onMessage.addListener((message, sender, sendResponse) => {
  const handler = handlers[message.type];
  if (!handler) return false;
  Promise.resolve(handler(message))
    .then((result) => sendResponse({ ok: true, result }))
    .catch((error) => sendResponse({ ok: false, error: error.message }));
  return true;
});

chrome.action.onClicked.addListener(() => chrome.runtime.openOptionsPage());
