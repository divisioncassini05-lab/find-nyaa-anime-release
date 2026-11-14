// Keep observing idle plans: another view/session may start the next check.
// This reads local status only; it never schedules work or calls a model.
export function observePanelActivity(refresh, running, doc = document, win = window) {
  const poll = () => { if (!doc.hidden) refresh(); };
  const timer = win.setInterval(poll, running ? 15000 : 30000);
  doc.addEventListener('visibilitychange', poll);
  win.addEventListener('focus', poll);
  return () => {
    win.clearInterval(timer);
    doc.removeEventListener('visibilitychange', poll);
    win.removeEventListener('focus', poll);
  };
}
