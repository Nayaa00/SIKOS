(() => {
 const cost=document.getElementById('product-hpp'),category=document.getElementById('product-category'),price=document.getElementById('selling-price'),note=document.getElementById('pricing-note');
 if(!cost||!category||!price)return;
 function update(){
   const percentage=Number(category.selectedOptions[0]?.dataset.markup),hpp=Number(cost.value);
   if(!category.value||!cost.value||!Number.isInteger(hpp)||hpp<1||!Number.isFinite(percentage)){price.value='';return;}
   // Integer basis points keep the preview identical to server Decimal rounding.
   const basis=Math.round(percentage*100),value=Math.ceil(hpp*(10000+basis)/1000000)*100;
   price.value=value<=1000000000?value:'';
   note.textContent='Markup kategori '+percentage.toLocaleString('id-ID')+'% dari HPP · pembulatan ke atas kelipatan Rp100. Harga final dihitung server saat disimpan.';
 }
 cost.addEventListener('input',update);category.addEventListener('change',update);update();
})();
