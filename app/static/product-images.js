document.querySelectorAll('img[data-fallback]').forEach(image => {
  const fallback = () => {
    if (image.dataset.usedFallback) {
      image.src = '/static/products/placeholder.svg';
      image.onerror = null;
    } else {
      image.dataset.usedFallback = '1';
      image.src = image.dataset.fallback;
    }
  };
  image.onerror = fallback;
  if (image.complete && image.naturalWidth === 0) fallback();
});
