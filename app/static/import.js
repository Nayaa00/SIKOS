const importFile = document.getElementById('import-file');
const importForm = document.getElementById('import-form');
if (importFile && importForm) {
  importFile.addEventListener('change', () => {
    const file = importFile.files[0];
    importFile.setCustomValidity(file && file.size > 10 * 1024 * 1024 ? 'Ukuran file maksimal 10 MB.' : '');
    document.getElementById('selected-file').textContent = file ? file.name : 'Belum ada file dipilih';
  });
  importForm.addEventListener('submit', () => {
    const button = document.getElementById('import-submit');
    button.disabled = true;
    button.textContent = 'Memproses impor…';
  });
  window.addEventListener('pageshow', () => {
    const button = document.getElementById('import-submit');
    button.disabled = false;
    button.textContent = 'Validasi & impor →';
  });
}
