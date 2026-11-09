import React from 'react';

// Original plugin identity; normal action icons continue to use lucide.
export function TelevisionIcon({ size = 24 }) {
  return <svg width={size} height={size} viewBox="0 0 32 32" fill="none" aria-hidden="true" focusable="false">
    <path d="m10 3 6 6 6-6M10 27v2m12-2v2" stroke="currentColor" strokeWidth="2.4" strokeLinecap="round"/>
    <rect x="3" y="8" width="26" height="19" rx="5" fill="currentColor" fillOpacity=".12" stroke="currentColor" strokeWidth="2.2"/>
    <rect x="7" y="12" width="18" height="11" rx="2" fill="currentColor" fillOpacity=".06"/>
    <path d="M11 15v4m10-4v4" stroke="currentColor" strokeWidth="2.6" strokeLinecap="round"/>
  </svg>;
}
