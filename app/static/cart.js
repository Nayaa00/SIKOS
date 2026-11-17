const cartForm = document.getElementById('cart-form');
if (cartForm) {
  const money = value => 'Rp' + value.toLocaleString('id-ID');
  const inputs = [...cartForm.querySelectorAll('[data-price]')];
  inputs.forEach(input => input.addEventListener('input', () => {
    let total = 0, units = 0;
    inputs.forEach(field => {
      const qty = Math.max(0, Math.trunc(Number(field.value) || 0));
      const subtotal = qty * Number(field.dataset.price);
      total += subtotal; units += qty;
      document.querySelector('[data-subtotal="' + field.id.slice(4) + '"]').textContent = money(subtotal);
    });
    document.getElementById('cart-total').textContent = money(total);
    document.getElementById('cart-units').textContent = units;
  }));
}
