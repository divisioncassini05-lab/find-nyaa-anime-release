// Legacy plans keep their identity and history; only their search behavior changes.
export const scopeMode = (mode) => mode === 'next_tracked' || !mode ? 'latest_regular' : mode;
export const wholeWork = (mode) => ['season_batch', 'movie'].includes(mode);
export const scopeLabel = (mode) => ({ season_batch: '整季合集', movie: '整部剧场版', latest_regular: '最新一集', missing_episodes: '补齐未记录集数' }[scopeMode(mode)] || '查找范围未知');
export const packageFound = (plan) => wholeWork(plan?.mode) && Boolean(plan?.evidence?.foundPackage || plan?.evidence?.latestPackage);
