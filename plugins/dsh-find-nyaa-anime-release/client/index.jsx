import React from 'react';
import { Film } from 'lucide-react';
import { Panel } from './Panel.jsx';
import css from './panel.css';

export const name = 'anime-release-panel';
export const inject = ['slots', 'locale', 'connection', 'uiWorkspace'];
const NS = 'anime-release.panel';
const PANEL = 'anime-release';
const Icon = ({ size = 20 }) => <Film size={size}/>;

export function apply(ctx) {
  ctx.effect(() => ctx.locale.register(NS, { zh: { panel: '动漫追番' }, en: { panel: 'Anime tracking' } }), 'anime-release: locale');
  const t = ctx.locale.bind(NS);
  ctx.effect(() => {
    const style = document.createElement('style');
    style.dataset.animeRelease = 'panel'; style.textContent = css;
    document.head.append(style);
    return () => style.remove();
  }, 'anime-release: styles');
  const loadSnapshot = async (signal) => {
    const result = await ctx.connection.rpc.call('/api', 'anime-release/snapshot', {}, signal);
    if (!result.ok) throw new Error(result.error.code);
    return result.value;
  };
  const openDraft = (prompt) => ctx.uiWorkspace.startSession(undefined, { prompt, whenDraftExists: 'append' });
  ctx.slots.inject('main', () => ctx.slots.register({
    name: 'main', key: PANEL, locale: NS, inject: () => ({ loadSnapshot, openDraft }),
  }, Panel));
  ctx.slots.inject('sidebar.panellist', () => ctx.slots.register({
    name: 'sidebar.panellist', id: PANEL, order: 25, locale: NS, label: () => t('panel'),
  }, Icon));
}
