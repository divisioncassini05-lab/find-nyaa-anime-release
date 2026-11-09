// Shared plan timing contract. DSH owns clock evaluation and DST handling.
const fail = (code = 'invalid_schedule') => Object.assign(new Error(code), { code });
export const scheduleFor = (plan) => plan?.schedule || (plan?.intervalHours > 0 ? { kind: 'interval', hours: plan.intervalHours } : { kind: 'manual' });
export const hasSchedule = (plan) => scheduleFor(plan).kind !== 'manual';
export function validateSchedule(input) {
  if (!input || typeof input !== 'object' || Array.isArray(input)) throw fail();
  const fields = { manual: [], interval: ['hours'], daily: ['time', 'timeZone'], weekly: ['time', 'timeZone', 'weekdays'], once: ['date', 'time', 'timeZone'] }[input.kind];
  if (!fields || Object.keys(input).some((k) => k !== 'kind' && !fields.includes(k))) throw fail();
  if (input.kind === 'manual') return { kind: 'manual' };
  if (input.kind === 'interval') {
    if (!Number.isInteger(input.hours) || input.hours < 1 || input.hours > 168) throw fail();
    return { kind: 'interval', hours: input.hours };
  }
  if (!/^([01]\d|2[0-3]):[0-5]\d$/u.test(input.time || '')) throw fail();
  if (typeof input.timeZone !== 'string' || input.timeZone.length > 100) throw fail('invalid_time_zone');
  try { new Intl.DateTimeFormat('en', { timeZone: input.timeZone }).format(); } catch { throw fail('invalid_time_zone'); }
  const result = { kind: input.kind, time: input.time, timeZone: input.timeZone };
  if (input.kind === 'weekly') {
    if (!Array.isArray(input.weekdays) || !input.weekdays.length || input.weekdays.some((n) => !Number.isInteger(n) || n < 1 || n > 7)) throw fail();
    result.weekdays = [...new Set(input.weekdays)].sort((a, b) => a - b);
  }
  if (input.kind === 'once') {
    const date = /^\d{4}-\d{2}-\d{2}$/u.test(input.date || '') && new Date(`${input.date}T00:00:00Z`);
    if (!date || !Number.isFinite(date.getTime()) || date.toISOString().slice(0, 10) !== input.date) throw fail();
    result.date = input.date;
  }
  return result;
}
export function scheduleTiming(plan) {
  const rule = validateSchedule(scheduleFor(plan));
  if (rule.kind === 'manual') return null;
  if (rule.kind === 'interval') return { kind: 'every', every_seconds: rule.hours * 3600 };
  const clock = { time: `${rule.time}:00`, time_zone: rule.timeZone };
  if (rule.kind === 'once') return { kind: 'at', at: { ...clock, date: rule.date } };
  return { kind: rule.kind, [rule.kind]: { ...clock, ...(rule.kind === 'weekly' ? { weekdays: rule.weekdays } : {}) } };
}
export function scheduleLabel(plan) {
  const rule = scheduleFor(plan);
  if (rule.kind === 'manual') return '仅手动检查';
  if (rule.kind === 'interval') return `每 ${rule.hours} 小时`;
  const period = rule.kind === 'weekly' ? `每周${rule.weekdays.map((n) => '一二三四五六日'[n - 1]).join('、')}` : rule.kind === 'daily' ? '每天' : `${rule.date}（仅一次）`;
  return `${period} ${rule.time} · ${rule.timeZone}`;
}
