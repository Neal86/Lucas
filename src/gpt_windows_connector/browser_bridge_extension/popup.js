let renderSequence = 0;
async function render() {
  const sequence = ++renderSequence;
  const [s, tabs] = await Promise.all([
    chrome.storage.local.get(["connected", "lastSeen", "paired", "nodeId", "bridgeProfile", "lucasTabStates"]),
    chrome.tabs.query({active:true, currentWindow:true})
  ]);
  if (sequence !== renderSequence) return;
  const connected = s.connected === true && s.paired === true && Date.now() - Number(s.lastSeen || 0) < 45000;
  document.getElementById("status").textContent = connected ? "Connected" : "Disconnected";
  const profile = s.bridgeProfile || {};
  document.getElementById("profile").textContent = [s.nodeId || "—", profile.profile_name || profile.profile_id || "—"].join(" / ");
  const state = s.lucasTabStates?.[tabs[0]?.id];
  document.getElementById("tabState").textContent = !tabs.length ? "—" : !state ? "Human" : state.paused ? (state.control === "human" ? "Human Control" : "AI Paused") : "AI Running";
}
chrome.storage.onChanged.addListener(render);
chrome.tabs.onActivated.addListener(render);
chrome.tabs.onUpdated.addListener(render);
render();
setInterval(render, 1000);
