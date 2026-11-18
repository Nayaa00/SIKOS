const form = document.getElementById('cash-form');
if (form) {
  const method = document.getElementById('payment-method');
  const amount = document.getElementById('cash-amount');
  const change = document.getElementById('cash-change');
  const message = document.getElementById('cash-message');
  const button = document.getElementById('cash-submit');
  const proofInput = document.getElementById('payment-proof');

  const video = document.getElementById('payment-camera');
  const panel = document.getElementById('camera-panel');
  const status = document.getElementById('camera-message');
  let stream, previewUrl;
  function stopCamera() {
    if (stream) stream.getTracks().forEach(track => track.stop());
    stream = null; video.srcObject = null; panel.hidden = true;
  }
  function preview() {
    const file = proofInput.files[0];
    proofInput.setCustomValidity(file && (file.size > 5*1024*1024 || !['image/jpeg','image/png','image/webp'].includes(file.type)) ? 'Pilih gambar JPG, PNG atau WebP maksimal 5 MB.' : '');
    const image = document.getElementById('proof-preview');
    if (previewUrl) URL.revokeObjectURL(previewUrl);
    image.hidden = !file || !proofInput.validity.valid;
    if (!image.hidden) { previewUrl = URL.createObjectURL(file); image.src = previewUrl; }
    update();
  }
  proofInput.addEventListener('change', preview);
  document.getElementById('open-camera').addEventListener('click', async () => {
    stopCamera(); status.textContent = '';
    try {
      if (!navigator.mediaDevices?.getUserMedia) throw new Error('unavailable');
      stream = await navigator.mediaDevices.getUserMedia({video:{facingMode:'environment'},audio:false});
      if (method.value !== 'Cashless') { stopCamera(); return; }
      video.srcObject = stream; panel.hidden = false;
    } catch (_) { status.textContent = 'Kamera tidak tersedia atau izin ditolak. Gunakan Unggah Gambar.'; }
  });
  document.getElementById('close-camera').addEventListener('click', stopCamera);
  document.getElementById('capture-photo').addEventListener('click', () => {
    if (!video.videoWidth) return;
    const canvas = document.createElement('canvas');
    canvas.width = video.videoWidth; canvas.height = video.videoHeight;
    canvas.getContext('2d').drawImage(video,0,0);
    canvas.toBlob(blob => {
      if (!blob) return;
      const data = new DataTransfer(); data.items.add(new File([blob],'bukti-kamera.jpg',{type:'image/jpeg'}));
      proofInput.files = data.files; stopCamera(); preview();
    },'image/jpeg',0.9);
  });
  window.addEventListener('pagehide', stopCamera);
  function update() {
    const cash = method.value === 'Cash';
    document.getElementById('cash-fields').hidden = !cash;
    amount.disabled = !cash;
    const value = Number(amount.value);
    const enough = amount.value !== '' && Number.isInteger(value) && value >= Number(form.dataset.total) && value <= 1000000000;
    change.value = enough ? 'Rp' + (value - Number(form.dataset.total)).toLocaleString('id-ID') : '—';
    document.getElementById('cashless-fields').hidden = cash;
    proofInput.disabled = cash;
    proofInput.required = false;
    if (cash) stopCamera();
    message.textContent = !cash ? '' : (amount.value && !enough ? 'Uang pembayaran kurang atau nominal tidak valid.' : 'Kembalian dihitung otomatis. Pastikan uang sudah diterima.');
    button.disabled = cash ? !enough : !((proofInput.files.length && proofInput.validity.valid) || (form.dataset.submittedProof === '1' && !proofInput.files.length));
  }
  form.addEventListener('submit', event => { if (method.value === 'Cashless' && ((!proofInput.files.length && form.dataset.submittedProof !== '1') || !proofInput.validity.valid)) { event.preventDefault(); status.textContent = 'Pilih bukti pembayaran yang valid terlebih dahulu.'; } });
  method.addEventListener('change', update); amount.addEventListener('input', update); update();
}
