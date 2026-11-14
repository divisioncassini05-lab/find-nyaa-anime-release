import test from 'node:test';
import assert from 'node:assert/strict';
import {observePanelActivity} from '../client/panel-activity.mjs';
import {WhaleCheckStatus} from '../client/whale-check-status.mjs';

test('idle panel notices an external run and refreshes on returning to the window', () => {
  const doc = new EventTarget(), win = new EventTarget();
  let tick, interval, cleared = false, reads = 0, status = 'idle', signal;
  Object.assign(win, {setInterval(fn, ms) {tick = fn; interval = ms; return 17;},
    clearInterval(id) {assert.equal(id, 17); cleared = true;}});
  const observer = new WhaleCheckStatus();
  const stop = observePanelActivity(() => {
    reads++; signal = observer.update([{id:'one', checkStatus:status}]);
  }, false, doc, win);
  assert.equal(interval, 30000);
  tick(); assert.equal(signal.checking, false);
  status = 'running'; tick(); assert.equal(signal.checking, true);
  doc.hidden = true; tick(); assert.equal(reads, 2);
  doc.hidden = false; doc.dispatchEvent(new Event('visibilitychange'));
  win.dispatchEvent(new Event('focus')); assert.equal(reads, 4);
  stop(); assert.equal(cleared, true);
  win.dispatchEvent(new Event('focus')); assert.equal(reads, 4);
});
