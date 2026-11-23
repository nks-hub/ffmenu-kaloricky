// Meal keys equal Meal.key in ffkt/ffmenu.py: "<product_variant_id>:<YYYY-MM-DD>:<card index in the day>".
const MONTHS = ["ledna", "února", "března", "dubna", "května", "června", "července", "srpna", "září",
  "října", "listopadu", "prosince"];
// KT diary slots: 1 breakfast, 2 morning snack, 3 lunch, 4 afternoon snack, 5 dinner, 6 second dinner
const DAY_TIMES = { "Snídaně": 1, "Oběd": 3, "Večeře": 5 };
const LABELS = { idle: "Do KT", busy: "Zapisuji…", done: "V KT ✓", error: "Chyba, znovu" };

const send = (message) => chrome.runtime.sendMessage(message);

function currentVariant() {
  const fromUrl = new URL(location.href).searchParams.get("product_variant_id");
  if (fromUrl) return fromUrl;
  const active = document.querySelector("a.btn-outline-secondary.active[href*='product_variant_id']");
  return active ? new URL(active.href).searchParams.get("product_variant_id") : null;
}

function isoDay(text) {
  const match = text.replace(/\s+/g, " ").match(/(\d{1,2})\.\s*(\S+)\s+(\d{4})/);
  const month = match ? MONTHS.indexOf(match[2]) + 1 : 0;
  return month ? `${match[3]}-${String(month).padStart(2, "0")}-${match[1].padStart(2, "0")}` : null;
}

function number(text) {
  const match = (text || "").replace(/\s/g, "").replace(",", ".").match(/\d+(\.\d+)?/);
  return match ? Number(match[0]) : null;
}

function readMeal(card, key, dayTime) {
  const values = {};
  for (const block of card.querySelectorAll(".headings-line-height")) {
    const label = block.querySelector("small")?.textContent.trim();
    if (label) values[label] = number(block.textContent.replace(label, ""));
  }
  return {
    key,
    dayTime,
    name: card.querySelector(".mb-1.font-weight-bold")?.textContent.trim(),
    kj: number(card.querySelector(".text-large")?.textContent),
    protein: values["Bílkoviny"],
    carbs: values["Sacharidy"],
    fat: values["Tuky"],
    fiber: values["Vláknina"] ?? 0,
    cholesterol: values["Cholesterol"] ?? 0,
  };
}

function menuDays(variant) {
  return [...document.querySelectorAll(".section-h3")].map((header) => {
    const date = isoDay(header.textContent);
    const cards = [...(header.nextElementSibling?.querySelectorAll(".position-relative.product-select-container") ?? [])];
    let seenLunch = false;
    const meals = cards.map((card, slot) => {
      const kind = card.querySelector(".news-slider-tag")?.textContent.trim();
      const dayTime = DAY_TIMES[kind] ?? (kind === "Svačina" ? (seenLunch ? 4 : 2) : 6);
      seenLunch = seenLunch || kind === "Oběd";
      return { card, meal: readMeal(card, `${variant}:${date}:${slot}`, dayTime) };
    });
    return { header, date, meals };
  }).filter((day) => day.date && day.meals.length);
}

function setState(button, state, title = "") {
  button.textContent = state === "idle" && button.dataset.day ? "Celý den do KT" : LABELS[state];
  button.disabled = state === "busy" || state === "done";
  button.dataset.state = state;
  button.title = title;
}

function showBanner(text, withSettings) {
  let banner = document.querySelector(".ffkt-banner");
  if (!banner) {
    banner = Object.assign(document.createElement("div"), { className: "ffkt-banner" });
    document.querySelector("h1")?.after(banner);
  }
  banner.textContent = `FF Menu do KT: ${text} `;
  if (withSettings) {
    const open = Object.assign(document.createElement("button"), { type: "button", textContent: "Otevřít nastavení" });
    open.addEventListener("click", () => send({ type: "openOptions" }));
    banner.append(open);
  }
}

async function addMeal(button, meal, date) {
  setState(button, "busy");
  const response = await send({ type: "add", meal, date });
  setState(button, response.ok ? "done" : "error", response.ok ? "" : response.error);
  return response.ok;
}

async function init() {
  const variant = currentVariant();
  const days = variant ? menuDays(variant) : [];
  if (!days.length) return;

  for (const day of days) {
    day.buttons = day.meals.map(({ card, meal }) => {
      const button = Object.assign(document.createElement("button"), { type: "button", className: "ffkt-btn" });
      button.dataset.key = meal.key;
      setState(button, "idle");
      button.addEventListener("click", () => addMeal(button, meal, day.date));
      card.append(button);
      return button;
    });
    day.dayButton = Object.assign(document.createElement("button"), { type: "button", className: "ffkt-btn ffkt-day" });
    day.dayButton.dataset.day = day.date;
    setState(day.dayButton, "idle");
    day.dayButton.addEventListener("click", async () => {
      setState(day.dayButton, "busy");
      let allDone = true;
      for (const [i, { meal }] of day.meals.entries()) {
        if (day.buttons[i].dataset.state !== "done") allDone = (await addMeal(day.buttons[i], meal, day.date)) && allDone;
      }
      setState(day.dayButton, allDone ? "done" : "error", allDone ? "" : "některá jídla se nezapsala");
    });
    day.header.append(day.dayButton);
  }

  const added = await send({ type: "added", dates: days.map((d) => d.date) });
  for (const day of days) {
    const keys = new Set(added.result[day.date]);
    day.buttons.forEach((button) => keys.has(button.dataset.key) && setState(button, "done"));
    if (day.buttons.every((button) => button.dataset.state === "done")) setState(day.dayButton, "done");
  }
  if (!(await send({ type: "status" })).result) {
    showBanner("nejdřív zadej přihlášení do Kalorických tabulek.", true);
  }
}

init();
