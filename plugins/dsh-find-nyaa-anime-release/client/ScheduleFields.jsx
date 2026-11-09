import React from 'react';

export default function ScheduleFields({ value, onChange, catchup = false, immediate = false }) {
  const zone = Intl.DateTimeFormat().resolvedOptions().timeZone || 'UTC';
  const field = (name, next) => onChange({ ...value, [name]: next });
  const changeKind = (kind) => onChange(kind === 'manual' ? { kind } : kind === 'interval' ? { kind, hours: 4 } : {
    kind, time: value.time || '22:00', timeZone: value.timeZone || zone,
    ...(kind === 'weekly' ? { weekdays: value.weekdays || [1] } : {}),
    ...(kind === 'once' ? { date: value.date || '' } : {}),
  });
  return <div className="anime-schedule-fields">
    <label>执行方式<select value={value.kind} onChange={(e) => changeKind(e.target.value)}>
      <option value="manual">{immediate ? '提交后执行一次' : '仅手动检查'}</option>
      {!catchup && <><option value="weekly">每周</option><option value="daily">每天</option></>}
      <option value="once">预约一次</option>
      {!catchup && <option value="interval">按小时间隔</option>}
    </select></label>
    {value.kind === 'weekly' && <fieldset className="anime-weekdays"><legend>星期</legend>{[1, 2, 3, 4, 5, 6, 7].map((day) => <label key={day}><input type="checkbox" checked={value.weekdays.includes(day)} onChange={(e) => field('weekdays', e.target.checked ? [...value.weekdays, day].sort() : value.weekdays.filter((n) => n !== day))}/>{`周${'一二三四五六日'[day - 1]}`}</label>)}</fieldset>}
    {value.kind === 'once' && <label>执行日期<input required type="date" value={value.date} onChange={(e) => field('date', e.target.value)}/></label>}
    {['weekly', 'daily', 'once'].includes(value.kind) && <div className="anime-schedule-clock">
      <label>执行时间<input required type="time" value={value.time} onChange={(e) => field('time', e.target.value)}/></label>
      <label>时区<input required list="anime-time-zones" value={value.timeZone} onChange={(e) => field('timeZone', e.target.value)}/></label>
      <datalist id="anime-time-zones">{[...new Set([zone, 'Asia/Shanghai', 'Asia/Tokyo', 'UTC', 'America/New_York', 'Europe/London'])].map((v) => <option value={v} key={v}/>)}</datalist>
    </div>}
    {value.kind === 'interval' && <label>间隔小时数<input required type="number" min="1" max="168" value={value.hours} onChange={(e) => field('hours', Number(e.target.value))}/></label>}
  </div>;
}
