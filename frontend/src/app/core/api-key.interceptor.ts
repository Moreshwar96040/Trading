import { HttpInterceptorFn } from '@angular/common/http';

/**
 * Attaches X-Api-Key to every backend call when a key has been saved.
 * Pairs with the backend's ApiKeyFilter: no key configured = everything open
 * locally as before; key configured (for ngrok exposure) = set the same value
 * once in the browser:  localStorage.setItem('api_key', '<your key>')
 */
export const apiKeyInterceptor: HttpInterceptorFn = (req, next) => {
  const key = localStorage.getItem('api_key');
  if (key && req.url.includes('/api/')) {
    return next(req.clone({ setHeaders: { 'X-Api-Key': key } }));
  }
  return next(req);
};
