// Debe ir de primero: instala los polyfills de funciones modernas que usa el
// visor de PDF (Promise.withResolvers, URL.parse) antes de que se cargue
// cualquier otro módulo, para soportar navegadores anteriores a mediados de 2024.
import './lib/polyfills'
import { StrictMode } from 'react'
import { createRoot } from 'react-dom/client'
import './index.css'
import { App } from './App.tsx'

createRoot(document.getElementById('root')!).render(
  <StrictMode>
    <App />
  </StrictMode>,
)
