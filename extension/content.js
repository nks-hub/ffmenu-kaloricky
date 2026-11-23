// Meal keys must equal Meal.key in ffkt/ffmenu.py: "<product_variant_id>:<YYYY-MM-DD>:<card index in the day>".
const MONTHS = ["ledna", "února", "března", "dubna", "května", "června", "července", "srpna", "září",
  "října", "listopadu", "prosince"];
const LABELS = { idle: "Do KT", busy: "Zapisuji…", done: "V KT ✓", error: "Chyba, znovu" };

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

function menuDays() {
  return [...document.querySelectorAll(".section-h3")].map((header) => ({
    header,
    date: isoDay(header.textContent),
    cards: [...(header.nextElementSibling?.querySelectorAll(".position-relative.product-select-container") ?? [])],
  })).filter((day) => day.date && day.cards.length);
}

function setState(button, state, title = "") {
  button.textContent = state === "idle" && button.dataset.day ? "Celý den do KT" : LABELS[state];
  button.disabled = state === "busy" || state === "done";
  button.dataset.state = state;
  button.title = title;
}

function showProblem(text) {
  let banner = document.querySelector(".ffkt-banner");
  if (!banner) {
    banner = Object.assign(document.createElement("div"), { className: "ffkt-banner" });
    document.querySelector("h1")?.after(banner);
  }
  banner.textContent = `FF Menu do KT: ${text}`;
}

async function refreshDay(day, variant) {
  const { status, data } = await chrome.runtime.sendMessage({ type: "menu", date: day.date, program: variant });
  if (status !== 200) return showProblem(data.error || `chyba ${status}`);
  const added = new Set(data.meals.filter((m) => m.added).map((m) => m.key));
  day.buttons.forEach((button) => added.has(button.dataset.key) && setState(button, "done"));
  if (day.buttons.every((button) => button.dataset.state === "done")) setState(day.dayButton, "done");
}

function addButtons() {
  const variant = currentVariant();
  if (!variant) return;
  for (const day of menuDays()) {
    day.buttons = day.cards.map((card, slot) => {
      const button = Object.assign(document.createElement("button"), { type: "button", className: "ffkt-btn" });
      button.dataset.key = `${variant}:${day.date}:${slot}`;
      setState(button, "idle");
      button.addEventListener("click", async () => {
        setState(button, "busy");
        const { status, data } = await chrome.runtime.sendMessage({ type: "add", key: button.dataset.key, date: day.date });
        if (status === 200 || status === 409) setState(button, "done");
        else setState(button, "error", data.error || `chyba ${status}`);
      });
      card.append(button);
      return button;
    });

    day.dayButton = Object.assign(document.createElement("button"), { type: "button", className: "ffkt-btn ffkt-day" });
    day.dayButton.dataset.day = day.date;
    setState(day.dayButton, "idle");
    day.dayButton.addEventListener("click", async () => {
      setState(day.dayButton, "busy");
      const { status, data } = await chrome.runtime.sendMessage({ type: "addDay", date: day.date, program: variant });
      if (status !== 200) return setState(day.dayButton, "error", data.error || `chyba ${status}`);
      setState(day.dayButton, "done");
      refreshDay(day, variant);
    });
    day.header.append(day.dayButton);
    refreshDay(day, variant);
  }
}

addButtons();
