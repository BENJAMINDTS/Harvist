/**
 * Punto de entrada de la aplicación React.
 * Monta el componente raíz en el div#root del index.html.
 *
 * @author BenjaminDTS | Carlos Vico
 */
import React from 'react'
import ReactDOM from 'react-dom/client'
import App from './App'
import './index.css'

ReactDOM.createRoot(document.getElementById('root')!).render(
  <React.StrictMode>
    <App />
  </React.StrictMode>,
)
