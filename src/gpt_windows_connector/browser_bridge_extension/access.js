// Local website controls are separate from browser Profile selection.
(() => {
  const cleanHost = url => {
    const parsed = new URL(String(url));
    if (!['http:', 'https:', 'file:'].includes(parsed.protocol)) throw new Error('Browser-internal pages cannot be automated.');
    return parsed.protocol === 'file:' ? 'file://' : parsed.hostname.toLowerCase();
  };
  const matches = (host, rules) => (rules || []).some(rule => {
    rule = String(rule).trim().toLowerCase();
    return rule.startsWith('*.') ? host === rule.slice(2) || host.endsWith('.' + rule.slice(2)) : host === rule;
  });
  const handoff = (type, message, extra = {}) => ({status:'requires_user_action', requires_user_action:true,
    action_type:type, message, chat_message:message, ...extra});
  async function check(url) {
    const s = await chrome.storage.local.get(['paused','siteMode','allowedHosts','blockedHosts']);
    if (s.paused) return handoff('browser_paused', 'Lucas browser control is paused. Resume it in the extension.');
    const host = cleanHost(url);
    if (matches(host, s.blockedHosts)) return handoff('website_blocked', 'Website blocked in Lucas: ' + host, {host});
    if (s.siteMode !== 'ask' || matches(host, s.allowedHosts)) return null;
    const {temporaryHosts = {}} = await chrome.storage.session.get('temporaryHosts');
    if ((temporaryHosts[host] || 0) > Date.now()) return null;
    await chrome.storage.local.set({pendingSite:host});
    return handoff('website_permission', 'Allow ' + host + ' in the Lucas extension, then retry.', {host});
  }
  async function historyConsent() {
    if (!(await chrome.permissions.contains({permissions:['history']})))
      return handoff('history_permission', 'Enable one history lookup in Lucas extension settings, then retry.');
    const {historyConsentUntil = 0} = await chrome.storage.session.get('historyConsentUntil');
    if (historyConsentUntil < Date.now()) return handoff('history_permission', 'Approve one history lookup in Lucas extension settings, then retry.');
    await chrome.storage.session.remove('historyConsentUntil');
    return null;
  }
  globalThis.LucasAccess = {check, cleanHost, matches, handoff, historyConsent};
})();
