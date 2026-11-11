// Fictional, offline records for documentation screenshots, never live user data.
const titles = ['晴空列车', '潮汐来信', '星际邮差', '夏日放映室', '云端旅人'];
export const marketLibrary = titles.map((title, i) => ({
  subject_id: 900001 + i, title, original_title: ['Skybound Train', 'Letters from the Tide', 'Star Courier', 'Summer Cinema', 'Cloud Traveller'][i],
  collection_type: [3, 3, 2, 1, 4][i], watched_count: [4, 2, 12, 0, 3][i], episode_count: 12,
  rating: [9, 8, 9, null, 7][i], comment: i === 0 ? '喜欢旅途中的日常和人物关系。' : '',
  tags: [['旅行', '日常'], ['青春'], ['科幻'], ['日常'], ['冒险']][i], type: i === 3 ? 'Movie' : 'TV',
  date: i < 2 ? '2026-10-03' : '2024-04-06',
  collection_date: `2026-11-0${8 - i}T10:00:00Z`, updated_at: '2026-11-10T10:00:00Z',
}));
export const marketShows = marketLibrary.slice(0, 3).map((r, i) => ({
  id: `market-${i}`, bangumiSubjectId: r.subject_id, title: r.title, season: 'S01',
  handled: [5, 3, 12][i], latest: [5, 3, 12][i], target: [6, 4, null][i], total: 12,
  phase: i === 2 ? 'completed' : 'airing', waiting: false, pending: 0,
}));
export const marketPlans = marketShows.map((r, i) => ({
  id: `market-plan-${i}`, revision: 1, trackId: r.id, bangumiSubjectId: r.bangumiSubjectId,
  title: r.title, season: r.season, mode: i === 2 ? 'season_batch' : 'latest_regular',
  tier: i === 2 ? 'premium' : 'browse', requireZh: true, enqueue: true,
  syncedEpisode: [4, 2, 12][i], collectionType: i === 2 ? 2 : 3, collectionSync: 'synced',
  schedule: i === 2 ? {kind:'manual'} : {kind:'weekly', weekdays:[5], time:'22:00', timeZone:'Asia/Shanghai'},
  scheduleId: i === 2 ? null : `market-task-${i}`, scheduleActive: i !== 2, nextCheck: '2026-11-13T14:00:00Z',
  evidence: i === 2 ? {
    foundPackage:true, completedPackage:true, completedDownloads:1,
    latestPackage:{scope:'season', title:'[DEMO] Star Courier S01 Complete 1080p Blu-ray Remux', size:'84 GiB',infoHash:'c'.repeat(40),canDownload:true},
    download:{status:'completed',progress:1},
  } : {
    latestFound:{episode:[5,3][i],title:`[DEMO] ${['Skybound Train - 05','Letters from the Tide - 03'][i]} 1080p WEB-DL [CHT]`,size:'1.5 GiB',infoHash:String(i+1).repeat(40),canDownload:true,checkedAt:'2026-11-10T14:00:00Z'},
    download:{status:i===0?'completed':'downloading',progress:i===0?1:0.64},
    completedDownloads:i===0?5:2,completedEpisodes:i===0?[1,2,3,4,5]:[1,2],
  },
}));
