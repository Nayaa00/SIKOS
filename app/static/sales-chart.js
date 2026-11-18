(() => {
  'use strict';
  const canvas = document.getElementById('trend');
  const buttons = [...document.querySelectorAll('[data-chart-type]')];
  const payload = document.getElementById('trend-data');
  const fallback = document.getElementById('chart-fallback');
  if (!canvas) { buttons.forEach(button => { button.disabled = true; }); return; }
  if (!window.Chart) {
    canvas.hidden = true;
    fallback.hidden = false;
    buttons.forEach(button => { button.disabled = true; });
    return;
  }
  const {rows, kind, start, end} = JSON.parse(payload.textContent);
  const rupiah = value => 'Rp' + new Intl.NumberFormat('id-ID').format(value);
  const dateLabel = (key, full = false) => new Intl.DateTimeFormat('id-ID', {
    ...(kind === 'tahunan' ? {month: full ? 'long' : 'short', year: full ? 'numeric' : undefined} :
      {day: 'numeric', month: 'short', year: full ? 'numeric' : undefined}), timeZone: 'UTC'
  }).format(new Date(key + (key.length === 7 ? '-01' : '') + 'T00:00:00Z'));
  // Server bounds are naive UTC; shift to WIB dates, then iterate calendar days in UTC.
  const boundary = value => new Date(new Date(value + 'Z').getTime() + 7 * 3600000);
  const first = boundary(start), last = boundary(end);
  const values = new Map();
  for (let date = new Date(first); date < last; date.setUTCDate(date.getUTCDate() + 1)) {
    const key = date.toISOString().slice(0, kind === 'tahunan' ? 7 : 10);
    values.set(key, 0);
  }
  rows.forEach(row => {
    const key = row.hari.slice(0, kind === 'tahunan' ? 7 : 10);
    values.set(key, (values.get(key) || 0) + Number(row.subtotal));
  });
  const keys = [...values.keys()], amounts = [...values.values()];
  const peak = Math.max(...amounts), peakIndex = amounts.indexOf(peak);
  document.getElementById('chart-peak').textContent = 'Tertinggi: ' + rupiah(peak) + ' · ' + dateLabel(keys[peakIndex], true);
  const reduced = matchMedia('(prefers-reduced-motion: reduce)').matches;
  const options = {
    responsive: true, maintainAspectRatio: false,
    animation: reduced ? false : {duration: 420},
    interaction: {mode: 'index', intersect: false},
    layout: {padding: {top: 16, right: 12, bottom: 4}},
    plugins: {
      legend: {display: false},
      tooltip: {
        backgroundColor: '#153f34', titleColor: '#e8f0e7', bodyColor: '#ffffff',
        padding: 14, cornerRadius: 12, displayColors: false,
        titleFont: {size: 11, weight: 'normal'}, bodyFont: {size: 15, weight: 'bold'},
        callbacks: {title: items => dateLabel(keys[items[0].dataIndex], true), label: item => rupiah(item.parsed.y)}
      }
    },
    scales: {
      x: {offset: true, grid: {display: false}, border: {display: false},
        ticks: {color: '#829087', maxRotation: 0, autoSkip: true, maxTicksLimit: 7, font: {size: 10}, padding: 10}},
      y: {beginAtZero: true, grace: '15%', border: {display: false},
        grid: {color: '#edf0eb', drawTicks: false},
        ticks: {color: '#829087', maxTicksLimit: 5, padding: 10, font: {size: 10},
          callback: value => value >= 1000000000 ? 'Rp' + new Intl.NumberFormat('id-ID',{maximumFractionDigits:1}).format(value/1000000000) + ' M' :
            value >= 1000000 ? 'Rp' + new Intl.NumberFormat('id-ID',{maximumFractionDigits:1}).format(value/1000000) + ' jt' :
            value >= 1000 ? 'Rp' + new Intl.NumberFormat('id-ID',{maximumFractionDigits:1}).format(value/1000) + ' rb' : rupiah(value)}}
    }
  };
  let chart;
  function render(type) {
    if (chart) chart.destroy();
    chart = new Chart(canvas, {
      type,
      data: {labels: keys.map(key => dateLabel(key)), datasets: [{
        label: 'Penjualan', data: amounts, borderColor: '#287258', borderWidth: type === 'line' ? 2.5 : 0,
        backgroundColor: context => {
          const area = context.chart.chartArea;
          if (!area) return '#c9decd';
          const gradient = context.chart.ctx.createLinearGradient(0, area.top, 0, area.bottom);
          gradient.addColorStop(0, type === 'line' ? 'rgba(72,143,104,0.28)' : '#287258');
          gradient.addColorStop(1, type === 'line' ? 'rgba(72,143,104,0.01)' : '#9fc5a5');
          return gradient;
        },
        fill: type === 'line', tension: 0, pointRadius: keys.length === 1 ? 5 : 2,
        pointHoverRadius: 6, pointBackgroundColor: '#287258', pointBorderColor: '#fff', pointBorderWidth: 2,
        borderRadius: 6, maxBarThickness: 38, barPercentage: 0.65, categoryPercentage: 0.8
      }]}, options
    });
    buttons.forEach(button => button.setAttribute('aria-pressed',String(button.dataset.chartType === type)));
  }
  Chart.defaults.font.family = '"Segoe UI", system-ui, sans-serif';
  render(keys.length === 1 ? 'bar' : 'line');
  buttons.forEach(button => button.addEventListener('click', () => render(button.dataset.chartType)));
})();
