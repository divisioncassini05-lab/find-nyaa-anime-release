import React, { useState } from 'react';
import { Film } from 'lucide-react';

export function Cover({ url }) {
  const [failed, setFailed] = useState(null);
  return <span className="anime-tile" aria-hidden="true">
    {url && failed !== url ? <img src={url} alt="" width="46" height="60" loading="lazy" decoding="async" referrerPolicy="no-referrer" onError={() => setFailed(url)}/> : <Film size={22}/>}
  </span>;
}
