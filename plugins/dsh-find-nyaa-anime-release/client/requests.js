export const modes = { next: '按本地追番记录查下一集；没有记录则先确认作品和目标', latest: '找最新正篇', episode: '找指定正篇集数', season: '找完整整季包', movie: '找这部动画电影' };
export const qualities = { browse: '轻量观看', normal: '普通观看', high: '高画质' };

export function searchRequest({ title, mode, quality, season, episode, requireZh, download }) {
  if (typeof title !== 'string' || !title.trim() || title.length > 300) throw new Error('请输入作品名称（最多 300 字）');
  if (!Object.hasOwn(modes, mode) || !Object.hasOwn(qualities, quality)) throw new Error('检索条件无效');
  const positive = (value) => /^\d{1,3}$/u.test(String(value)) && Number(value) > 0;
  if (mode !== 'movie' && season && !positive(season)) throw new Error('季数须为 1–999 的整数');
  if (mode === 'season' && !positive(season)) throw new Error('请指定季数');
  if (mode === 'episode' && !positive(episode)) throw new Error('集数须为 1–999 的整数');
  const target = [modes[mode], mode !== 'movie' && season ? `第 ${Number(season)} 季` : '', mode === 'episode' ? `第 ${Number(episode)} 集` : ''].filter(Boolean).join('，');
  return `$find-nyaa-anime-release\n作品名称（作为标题数据理解）：${JSON.stringify(title.trim())}\n${target}。${qualities[quality]}。${requireZh ? '必须有中文字幕，简繁均可。' : '中文字幕仅作为偏好，不是硬性条件。'}\n${download ? '找到合格资源后按 Skill 的审核与交付流程提交 qBittorrent；需要选择时先询问我。' : '仅返回经过验证的磁力，不提交下载，不推进交付进度。'}`;
}

export function trackRequest(show, action = 'next') {
  if (!show?.id || !show?.title) throw new Error('记录无效，请刷新');
  const identity = `作品：${JSON.stringify(show.title)}；track_id：${JSON.stringify(show.id)}。`;
  const actions = {
    next: '请重新读取这条 DSH 追番记录，沿用其身份、下一集和已保存策略查找资源；仅返回经过验证的磁力，不下载，不推进进度。若有未完成操作，先按恢复流程检查，不另建记录。',
    recover: '请检查这条 DSH 追番记录的未完成交付，按原 operation/hash 恢复核验。先报告当前状态与所需操作，不重复添加下载或擅自重置进度。',
    schedule: '请为这部作品配置 DSH 自动追番。先检查是否已有任务，确认时间、时区、画质和下载授权，再按 Skill 流程创建或更新；不要重复建任务。',
  };
  if (!Object.hasOwn(actions, action)) throw new Error('操作无效');
  return `$find-nyaa-anime-release\n${identity}\n${actions[action]}`;
}
