import test from 'node:test';
import assert from 'node:assert/strict';
import { scheduleFor, validateSchedule, scheduleTiming, scheduleLabel } from '../host/schedule.js';
import { nextCheckLabel } from '../client/presentation.mjs';

test('weekly uses ISO weekdays and a wall clock in the chosen zone', () => {
  const schedule = validateSchedule({kind:'weekly',weekdays:[7,5,5],time:'22:30',timeZone:'Asia/Shanghai'});
  assert.deepEqual(scheduleTiming({schedule}), {kind:'weekly',weekly:{time:'22:30:00',time_zone:'Asia/Shanghai',weekdays:[5,7]}});
  assert.equal(scheduleLabel({schedule}), '每周五、日 22:30 · Asia/Shanghai');
});
test('one-time local date is delegated to DSH without workstation timezone conversion', () => {
  const schedule = {kind:'once',date:'2099-12-01',time:'09:05',timeZone:'America/New_York'};
  assert.deepEqual(scheduleTiming({schedule}), {kind:'at',at:{date:'2099-12-01',time:'09:05:00',time_zone:'America/New_York'}});
  assert.equal(nextCheckLabel({schedule,scheduleId:'s',scheduleActive:false,scheduleStatus:'ended'}),'预约已执行');
});
test('legacy intervals remain intervals, not reinterpreted calendar dates', () => {
  assert.deepEqual(scheduleFor({intervalHours:168}),{kind:'interval',hours:168});
  assert.deepEqual(scheduleTiming({intervalHours:24}),{kind:'every',every_seconds:86400});
  assert.equal(scheduleTiming({intervalHours:0}),null);
});
test('daily wall clock is not an elapsed 24 hour timer', () => {
  assert.deepEqual(scheduleTiming({schedule:{kind:'daily',time:'21:00',timeZone:'Europe/London'}}),{kind:'daily',daily:{time:'21:00:00',time_zone:'Europe/London'}});
});
test('invalid and empty date/weekday/zone/time fields are rejected', () => {
  for(const schedule of [
    {kind:'weekly',weekdays:[],time:'20:00',timeZone:'UTC'},
    {kind:'weekly',weekdays:[0],time:'20:00',timeZone:'UTC'},
    {kind:'daily',time:'24:01',timeZone:'UTC'},
    {kind:'daily',time:'20:00',timeZone:'Not/A_Zone'},
    {kind:'once',time:'20:00',timeZone:'UTC',date:'2099-02-30'},
    {kind:'once',time:'20:00',timeZone:'UTC',date:''},
    {kind:'interval',hours:0},
    {kind:'manual',unexpected:true},
  ]) assert.throws(()=>validateSchedule(schedule));
});
