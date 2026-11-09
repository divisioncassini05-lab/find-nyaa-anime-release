import React from 'react';
import { ChevronDown, Check, RefreshCw, Pause, CircleX } from 'lucide-react';
import { primaryAction } from './library.mjs';

export function PlanStatusActions({ record, busy, onMove, onProgress }) {
  const primary = primaryAction(record);
  return <div className="anime-record-actions">
    <div className="anime-split-action">
      <button disabled={busy || primary.disabled} title={primary.reason} onClick={() => primary.kind === 'watched' ? onMove(2) : onProgress()}>{primary.kind === 'watched' ? <Check size={14} aria-hidden="true"/> : <RefreshCw size={14} aria-hidden="true"/>}{primary.label}</button>
      <details onKeyDown={(e) => { if (e.key === 'Escape') { e.currentTarget.open = false; e.currentTarget.querySelector('summary').focus(); } }}>
        <summary title="其他番单操作" aria-disabled={busy} onClick={(e) => { if (busy) e.preventDefault(); }} aria-label={`${record.title}的其他番单操作`}><ChevronDown size={15}/></summary>
        <div className="anime-status-menu">{[[4, '搁置', Pause], [5, '抛弃', CircleX]].map(([value, label, Icon]) => <button key={value} data-action={value} disabled={busy} onClick={(e) => { e.currentTarget.closest('details').open = false; onMove(value); }}><Icon size={15} aria-hidden="true"/>{label}</button>)}</div>
      </details>
    </div>
  </div>;
}
