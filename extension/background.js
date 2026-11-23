// Requests go from here, not from the content script: ffmenu.cz is HTTPS and the service usually plain
// HTTP on the local network, which the page itself is not allowed to call.
const DEFAULTS = { serviceUrl: "http://127.0.0.1:8077", token: "" };

async function call(path, body) {
  const { serviceUrl, token } = { ...DEFAULTS, ...(await chrome.storage.local.get(["serviceUrl", "token"])) };
  try {
    const response = await fetch(serviceUrl.replace(/\/+$/, "") + path, {
      method: body ? "POST" : "GET",
      headers: { "Content-Type": "application/json", "X-Token": token },
      body: body ? JSON.stringify(body) : undefined,
    });
    return { status: response.status, data: await response.json().catch(() => ({})) };
  } catch (error) {
    return { status: 0, data: { error: `Služba na ${serviceUrl} neodpovídá (běží python -m ffkt serve?)` } };
  }
}

chrome.runtime.onMessage.addListener((message, sender, sendResponse) => {
  const query = (params) => new URLSearchParams(params).toString();
  const routes = {
    add: () => call("/api/add", { key: message.key, date: message.date }),
    addDay: () => call("/api/add-day", { date: message.date, program: message.program }),
    menu: () => call(`/api/menu?${query({ date: message.date, program: message.program || "" })}`),
  };
  if (!routes[message.type]) return false;
  routes[message.type]().then(sendResponse);
  return true;
});

chrome.action.onClicked.addListener(() => chrome.runtime.openOptionsPage());
