// Co 5 s wysyła do lokalnego agenta (127.0.0.1) dane aktywnej karty w aktywnym oknie.
// Token i port ustaw raz w konsoli service workera:
//   chrome.storage.local.set({token: "to-samo-co-local_token", port: 47800})
const PERIOD_MIN = 5 / 60;
chrome.alarms.create("tick", { periodInMinutes: Math.max(PERIOD_MIN, 1 / 60) });
async function tick() {
  const { token = "zmien-mnie", port = 47800 } = await chrome.storage.local.get(["token", "port"]);
  const [tab] = await chrome.tabs.query({ active: true, lastFocusedWindow: true });
  if (!tab || tab.incognito) return;
  try {
    await fetch(`http://127.0.0.1:${port}/tab`, {
      method: "POST",
      headers: { "X-TT-Token": token, "Content-Type": "application/json" },
      body: JSON.stringify({ url: tab.url || "", title: tab.title || "", audible: !!tab.audible, incognito: false }),
    });
  } catch (e) { /* agent nie działa: pomijamy */ }
}
chrome.alarms.onAlarm.addListener(tick);
setInterval(tick, 5000);
