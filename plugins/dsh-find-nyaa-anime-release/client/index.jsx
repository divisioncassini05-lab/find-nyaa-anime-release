import React from 'react';
import { TelevisionIcon } from './TelevisionIcon.jsx';
import { Panel } from './Panel.jsx';
import css from './panel.css';

export const name = 'anime-release-panel';
export const inject = ['slots', 'locale', 'connection', 'uiWorkspace'];
const NS = 'anime-release.panel';
const PANEL = 'anime-release';
const Icon = ({ size = 20 }) => <TelevisionIcon size={size}/>;

async function panelCall(ctx, endpoint, payload, signal) {
  let result;
  try { result = await ctx.connection.rpc.call('/api', `anime-release/${endpoint}`, payload, signal); }
  catch (error) { throw new Error(signal?.aborted ? 'cancelled' : 'panel_transport_unavailable'); }
  if (!result.ok) throw new Error(result.error.code);
  return result.value;
}

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
    return panelCall(ctx, 'snapshot', {}, signal);
  };
  const loadBangumi = async (signal, refresh = false) => {
    return panelCall(ctx, 'bangumi/library', refresh ? { refresh: true } : {}, signal);
  };
  const loadConfig = async (signal) => {
    return panelCall(ctx, 'config/status', {}, signal);
  };
  const loadMetadata = (ids, signal) => panelCall(ctx, 'bangumi/metadata', { ids }, signal);
  const saveConfig = async (endpoint, payload) => {
    return panelCall(ctx, endpoint, payload);
  };
  const loadPlans = async (signal) => {
    return panelCall(ctx, 'plans/list', {}, signal);
  };
  const openDraft = (prompt) => ctx.uiWorkspace.startSession(undefined, { prompt, whenDraftExists: 'append' });
  ctx.slots.inject('main', () => ctx.slots.register({
    name: 'main', key: PANEL, locale: NS, inject: () => ({ loadSnapshot, loadBangumi, loadMetadata, loadConfig, saveConfig, loadPlans, openDraft }),
  }, Panel));
  ctx.slots.inject('sidebar.panellist', () => ctx.slots.register({
    name: 'sidebar.panellist', id: PANEL, order: 25, locale: NS, label: () => t('panel'),
  }, Icon));
}
