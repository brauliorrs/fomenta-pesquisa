const state = {
  items: [],
  filtered: [],
  queueMap: new Map(),
  queueMeta: null,
};

const statsEl = document.getElementById('stats');
const cardsEl = document.getElementById('cards');
const resultCountEl = document.getElementById('resultCount');
const lastCollectedEl = document.getElementById('lastCollected');
const queueInfoEl = document.getElementById('queueInfo');
const template = document.getElementById('cardTemplate');

const searchInput = document.getElementById('searchInput');
const sourceFilter = document.getElementById('sourceFilter');
const statusFilter = document.getElementById('statusFilter');
const deadlineFilter = document.getElementById('deadlineFilter');
const queueFilter = document.getElementById('queueFilter');
const resetButton = document.getElementById('resetButton');

const suspiciousTokens = ['Ã', 'Â', 'â€™', 'â€œ', 'â€', '�'];
const displayRepairs = new Map([
  ['Coordenacao', 'Coordenação'],
  ['coordenacao', 'coordenação'],
  ['Aperfeicoamento', 'Aperfeiçoamento'],
  ['aperfeicoamento', 'aperfeiçoamento'],
  ['Nivel', 'Nível'],
  ['nivel', 'nível'],
  ['academica', 'acadêmica'],
  ['Academica', 'Acadêmica'],
  ['cientifico', 'científico'],
  ['Cientifico', 'Científico'],
  ['tecnologico', 'tecnológico'],
  ['Tecnologico', 'Tecnológico'],
]);

function repairText(value) {
  if (!value) return '';
  let text = String(value).trim();
  if (suspiciousTokens.some((token) => text.includes(token))) {
    try {
      text = decodeURIComponent(escape(text));
    } catch {
      text = text;
    }
  }
  for (const [source, target] of displayRepairs.entries()) {
    text = text.replaceAll(source, target);
  }
  return text.replace(/\s+/g, ' ').trim();
}

function repairMultilineText(value) {
  if (!value) return '';
  let text = String(value).trim();
  if (suspiciousTokens.some((token) => text.includes(token))) {
    try {
      text = decodeURIComponent(escape(text));
    } catch {
      text = text;
    }
  }
  for (const [source, target] of displayRepairs.entries()) {
    text = text.replaceAll(source, target);
  }
  return text
    .replace(/\r\n/g, '\n')
    .replace(/\r/g, '\n')
    .split('\n')
    .map((line) => line.replace(/\s+/g, ' ').trim())
    .join('\n')
    .trim();
}

function formatDate(value) {
  if (!value) return 'Não informado';
  const date = new Date(`${value}T00:00:00`);
  if (Number.isNaN(date.getTime())) return value;
  return new Intl.DateTimeFormat('pt-BR', { dateStyle: 'medium' }).format(date);
}

function formatDateTime(value) {
  if (!value) return 'Não informado';
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return value;
  return new Intl.DateTimeFormat('pt-BR', { dateStyle: 'medium', timeStyle: 'short' }).format(date);
}

function daysUntil(value) {
  if (!value) return null;
  const now = new Date();
  const target = new Date(`${value}T00:00:00`);
  if (Number.isNaN(target.getTime())) return null;
  return Math.ceil((target - now) / (1000 * 60 * 60 * 24));
}

function isOpenItem(item) {
  const days = daysUntil(item.data_expiracao);
  return days !== null && days >= 0 && item.status !== 'encerrado';
}

function deadlineBadge(item) {
  const days = daysUntil(item.data_expiracao);
  if (days === null) return { text: 'Sem prazo', level: '' };
  if (days < 0) return { text: 'Encerrado', level: 'danger' };
  if (days === 0) return { text: 'Hoje', level: 'danger' };
  if (days === 1) return { text: '1 dia', level: 'danger' };
  if (days <= 7) return { text: `${days} dias`, level: 'danger' };
  if (days <= 30) return { text: `${days} dias`, level: 'warning' };
  return { text: `${days} dias`, level: '' };
}

function normalizeItem(item) {
  const queueEntry = state.queueMap.get(item.id);
  return {
    ...item,
    titulo: repairText(item.titulo),
    orgao: repairText(item.orgao),
    fonte: repairText(item.fonte),
    resumo: repairText(item.resumo),
    publico_alvo: repairText(item.publico_alvo),
    status: repairText(item.status),
    instagram_caption: repairMultilineText(item.instagram_caption),
    instagram_asset: repairText(item.instagram_asset),
    instagram_mock_asset: repairText(item.instagram_mock_asset),
    motivo_bloqueio_postagem: repairText(item.motivo_bloqueio_postagem),
    bloqueio_editorial_definitivo: Boolean(item.bloqueio_editorial_definitivo),
    revisao_humana_obrigatoria: Boolean(item.revisao_humana_obrigatoria),
    pendencias_editoriais: Array.isArray(item.pendencias_editoriais)
      ? item.pendencias_editoriais.map((value) => repairText(value))
      : [],
    card_header: repairText(queueEntry?.card_header ?? item.card_header),
    card_title: repairText(queueEntry?.card_title ?? item.card_title),
    card_deadline: repairText(queueEntry?.card_deadline ?? item.card_deadline),
    card_summary: repairText(queueEntry?.card_summary ?? item.card_summary),
    card_handle: repairText(queueEntry?.card_handle ?? item.card_handle),
    card_footer_note: repairText(queueEntry?.card_footer_note ?? item.card_footer_note),
    queuePosition: queueEntry?.posicao_fila ?? null,
    queueUrgency: queueEntry?.urgencia_dias ?? null,
  };
}

function sourceClassName(source) {
  const normalized = repairText(source).toLowerCase();
  if (normalized === 'capes') return 'source-capes';
  if (normalized === 'cnpq') return 'source-cnpq';
  if (normalized === 'confap') return 'source-confap';
  if (normalized === 'ipea') return 'source-ipea';
  return '';
}

function toneClassNames(item) {
  const classes = [];
  const days = daysUntil(item.data_expiracao);
  const category = repairText(item.categoria).toLowerCase();
  const title = repairText(item.titulo).toLowerCase();

  if (days !== null && days <= 3) {
    classes.push('tone-urgent');
  } else if (days !== null && days <= 14) {
    classes.push('tone-soon');
  } else {
    classes.push('tone-open');
  }

  if (category.includes('bolsa') || title.includes('bolsa')) {
    classes.push('tone-bolsa');
  }

  if (
    category.includes('inov') ||
    title.includes('inov') ||
    title.includes('empreendedor') ||
    title.includes('centelha')
  ) {
    classes.push('tone-inovacao');
  }

  return classes;
}

function populateSources(items) {
  const sources = [...new Set(items.map((item) => item.fonte).filter(Boolean))].sort();
  for (const source of sources) {
    const option = document.createElement('option');
    option.value = source;
    option.textContent = source;
    sourceFilter.appendChild(option);
  }
}

function renderStats(items) {
  const metrics = [
    ['Inscrições abertas', items.filter((item) => isOpenItem(item)).length],
    ['Prontos para postar', items.filter((item) => item.pronto_para_postagem && isOpenItem(item)).length],
    ['Top 10 da fila', items.filter((item) => item.queuePosition && item.queuePosition <= 10).length],
    ['Revisão humana', items.filter((item) => item.revisao_humana_obrigatoria && isOpenItem(item)).length],
    ['Bloqueio editorial', items.filter((item) => item.bloqueio_editorial_definitivo && isOpenItem(item)).length],
  ];

  statsEl.innerHTML = '';
  for (const [label, value] of metrics) {
    const card = document.createElement('article');
    card.className = 'stat-card';
    card.innerHTML = `<span>${label}</span><strong>${value}</strong>`;
    statsEl.appendChild(card);
  }
}

function applyFilters() {
  const query = repairText(searchInput.value).toLowerCase();
  const source = sourceFilter.value;
  const status = statusFilter.value;
  const deadline = deadlineFilter.value;
  const queue = queueFilter.value;

  state.filtered = state.items.filter((item) => {
    const haystack = [item.titulo, item.orgao, item.resumo, item.instagram_caption, ...(item.pendencias_editoriais || [])].join(' ').toLowerCase();
    if (query && !haystack.includes(query)) return false;
    if (source && item.fonte !== source) return false;

    const days = daysUntil(item.data_expiracao);
    if (!status && !isOpenItem(item)) return false;
    if (status && item.status !== status) return false;

    if (deadline === 'urgent' && !(days !== null && days >= 0 && days <= 7)) return false;
    if (deadline === 'soon' && !(days !== null && days >= 0 && days <= 30)) return false;
    if (deadline === 'open' && !(days !== null && days > 30)) return false;
    if (deadline === 'missing' && item.data_expiracao) return false;

    if (queue === 'ready' && !item.pronto_para_postagem) return false;
    if (queue === 'review' && !item.revisao_humana_obrigatoria) return false;
    if (queue === 'blocked' && !item.bloqueio_editorial_definitivo) return false;
    if (queue === 'top' && !(item.queuePosition && item.queuePosition <= 10)) return false;

    return true;
  });

  state.filtered.sort((a, b) => {
    const aPos = a.queuePosition ?? 9999;
    const bPos = b.queuePosition ?? 9999;
    if (aPos !== bPos) return aPos - bPos;
    const aDays = daysUntil(a.data_expiracao) ?? 9999;
    const bDays = daysUntil(b.data_expiracao) ?? 9999;
    return aDays - bDays;
  });

  renderCards(state.filtered);
}

function renderCards(items) {
  cardsEl.innerHTML = '';
  resultCountEl.textContent = `${items.length} edital(is)`;

  if (!items.length) {
    const empty = document.createElement('div');
    empty.className = 'empty';
    empty.textContent = 'Nenhum edital encontrado com os filtros atuais.';
    cardsEl.appendChild(empty);
    return;
  }

  for (const item of items) {
    const fragment = template.content.cloneNode(true);
    const sourceChip = fragment.querySelector('.chip.source');
    const deadlineChip = fragment.querySelector('.chip.deadline');
    const queueChip = fragment.querySelector('.chip.queue');
    const title = fragment.querySelector('.card-title');
    const summary = fragment.querySelector('.card-summary');
    const meta = fragment.querySelector('.meta');
    const caption = fragment.querySelector('.caption-content');
    const sourceLink = fragment.querySelector('.source-link');
    const cardLink = fragment.querySelector('.card-link');
    const mockLink = fragment.querySelector('.mock-link');
    const instagramCard = fragment.querySelector('.instagram-card');
    const instagramCardHeader = fragment.querySelector('.instagram-card-header');
    const instagramCardTitle = fragment.querySelector('.instagram-card-title');
    const instagramCardDeadline = fragment.querySelector('.instagram-card-deadline');
    const instagramCardSummary = fragment.querySelector('.instagram-card-summary');
    const instagramCardHandle = fragment.querySelector('.instagram-card-handle');
    const instagramCardFooterNote = fragment.querySelector('.instagram-card-footer-note');

    const badge = deadlineBadge(item);
    const quality = Number.isFinite(Number(item.score_editorial)) ? Number(item.score_editorial) : 0;
    const pendencias = item.pendencias_editoriais && item.pendencias_editoriais.length
      ? item.pendencias_editoriais.join(' | ')
      : 'Sem pendencias editoriais.';

    if (item.pronto_para_postagem) {
      sourceChip.textContent = `${item.fonte} • pronto`;
    } else if (item.bloqueio_editorial_definitivo) {
      sourceChip.textContent = `${item.fonte} • bloqueado`;
    } else if (item.revisao_humana_obrigatoria) {
      sourceChip.textContent = `${item.fonte} • revisão`;
    } else {
      sourceChip.textContent = `${item.fonte} • analisar`;
    }
    deadlineChip.textContent = badge.text;
    deadlineChip.className = 'chip deadline';
    if (badge.level) {
      deadlineChip.classList.add(badge.level);
    }
    queueChip.textContent = item.queuePosition ? `Fila #${item.queuePosition}` : 'Fora da fila';
    instagramCard.className = 'instagram-card';
    const sourceClass = sourceClassName(item.fonte);
    if (sourceClass) {
      instagramCard.classList.add(sourceClass);
    }
    for (const toneClass of toneClassNames(item)) {
      instagramCard.classList.add(toneClass);
    }
    instagramCardHeader.textContent = item.card_header || `EDITAL ${item.fonte}`;
    instagramCardTitle.textContent = item.card_title || item.titulo;
    instagramCardDeadline.textContent = item.card_deadline || 'PRAZO A DEFINIR';
    instagramCardSummary.textContent = item.card_summary || item.resumo || 'Resumo não informado.';
    instagramCardHandle.textContent = item.card_handle || '@editais.pesquisa';
    instagramCardFooterNote.textContent = item.card_footer_note || 'Link e detalhes no post do perfil';
    title.textContent = item.titulo;
    summary.textContent = item.resumo || 'Resumo não informado.';
    caption.textContent = item.instagram_caption || 'Legenda indisponível.';

    sourceLink.href = item.link;
    if (item.instagram_asset) {
      cardLink.href = `../posts/${item.instagram_asset.split('\\').pop()}`;
      cardLink.style.display = 'inline-flex';
      cardLink.textContent = 'Abrir card';
      cardLink.style.pointerEvents = 'auto';
      cardLink.style.opacity = '1';
    } else {
      cardLink.removeAttribute('href');
      cardLink.textContent = 'Card pendente';
      cardLink.style.pointerEvents = 'none';
      cardLink.style.opacity = '0.65';
    }

    if (item.instagram_mock_asset) {
      mockLink.href = `../posts/${item.instagram_mock_asset.split('\\').pop()}`;
      mockLink.style.display = 'inline-flex';
      mockLink.textContent = 'Abrir mock';
      mockLink.style.pointerEvents = 'auto';
      mockLink.style.opacity = '1';
    } else {
      mockLink.removeAttribute('href');
      mockLink.textContent = 'Mock pendente';
      mockLink.style.pointerEvents = 'none';
      mockLink.style.opacity = '0.65';
    }

    const rows = [
      ['Órgão', item.orgao || 'Não informado'],
      ['Status', item.status || 'Não informado'],
      ['Score editorial', `${quality}/100`],
      ['Prazo', formatDate(item.data_expiracao)],
      ['Abertura', formatDate(item.data_abertura)],
      ['Última coleta', formatDateTime(item.data_ultima_coleta)],
      ['Público', item.publico_alvo || 'Não informado'],
      ['Postagem', item.pronto_para_postagem ? 'Liberada' : item.bloqueio_editorial_definitivo ? 'Bloqueada' : item.revisao_humana_obrigatoria ? 'Em revisão' : 'Analisar'],
      ['Pendências', pendencias],
    ];

    meta.innerHTML = rows.map(([label, value]) => `<dt>${label}</dt><dd>${value}</dd>`).join('');
    cardsEl.appendChild(fragment);
  }
}

async function loadQueue() {
  try {
    const response = await fetch('../data/fila_publicacao.json', { cache: 'no-store' });
    const queue = await response.json();
    state.queueMeta = queue;
    state.queueMap = new Map((queue.itens || []).map((item) => [item.id, item]));
    queueInfoEl.textContent = `${queue.total_prontos || 0} itens prontos na fila editorial`;
  } catch {
    state.queueMeta = null;
    state.queueMap = new Map();
    queueInfoEl.textContent = 'Fila editorial indisponível';
  }
}

async function loadData() {
  await loadQueue();
  const response = await fetch('../data/editais.json', { cache: 'no-store' });
  const rawItems = await response.json();
  state.items = rawItems.map(normalizeItem);

  const collectedDates = state.items.map((item) => item.data_ultima_coleta).filter(Boolean).sort();
  const latest = collectedDates.at(-1);
  lastCollectedEl.textContent = latest ? formatDateTime(latest) : 'Sem coleta';

  populateSources(state.items);
  renderStats(state.items);
  applyFilters();
}

[searchInput, sourceFilter, statusFilter, deadlineFilter, queueFilter].forEach((element) => {
  element.addEventListener('input', applyFilters);
  element.addEventListener('change', applyFilters);
});

resetButton.addEventListener('click', () => {
  searchInput.value = '';
  sourceFilter.value = '';
  statusFilter.value = '';
  deadlineFilter.value = '';
  queueFilter.value = '';
  applyFilters();
});

loadData().catch((error) => {
  cardsEl.innerHTML = `<div class="empty">Não foi possível carregar os editais. Rode a página por um servidor local e tente novamente.<br>${error}</div>`;
});
