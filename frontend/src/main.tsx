// Debe ir de primero: instala el polyfill de Promise.withResolvers (que usa el
// visor de PDF) antes de que se cargue cualquier otro módulo, para soportar
// navegadores anteriores a finales de 2023.
import './lib/promiseWithResolvers'
import { StrictMode } from 'react'
import { createRoot } from 'react-dom/client'
import './index.css'
import { App } from './App.tsx'

createRoot(document.getElementById('root')!).render(
  <StrictMode>
    <App />
  </StrictMode>,
)
