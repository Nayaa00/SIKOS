document.querySelectorAll('[data-product-code-form]').forEach(form => {
  const category=form.querySelector('[name="category_id"]');
  const code=form.querySelector('[name="kode"]');
  const hint=form.querySelector('[data-code-hint]');
  let controller;
  const update=async()=>{
    if(controller)controller.abort();
    code.value='';
    if(!category.value){code.placeholder='Pilih kategori terlebih dahulu';hint.textContent='Kode terisi otomatis setelah kategori dipilih.';return;}
    controller=new AbortController();
    code.placeholder='Menyiapkan kode…';
    try{
      const query=new URLSearchParams({category_id:category.value});
      if(code.dataset.productId)query.set('product_id',code.dataset.productId);
      const response=await fetch('/produk/kode-berikutnya?'+query,{signal:controller.signal,headers:{Accept:'application/json'}});
      if(!response.ok)throw new Error('Kode belum dapat dimuat. Muat ulang halaman atau pilih kategori aktif.');
      const result=await response.json();
      code.value=result.kode;
      hint.textContent=result.tetap?'Kode produk saat ini.':'Kode final ditetapkan saat disimpan agar tetap unik.';
    }catch(error){if(error.name!=='AbortError'){hint.textContent=error.message;code.placeholder='Kode otomatis saat disimpan';}}
  };
  category.addEventListener('change',update);
  if(category.value&&!code.value)update();
});
