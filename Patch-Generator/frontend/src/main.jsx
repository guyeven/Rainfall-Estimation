import { StrictMode } from 'react'
import { createRoot } from 'react-dom/client'
import './index.css'
import { Component } from 'react'

class RootErrorBoundary extends Component {
  constructor(props) {
    super(props)
    this.state = { error: null }
  }

  static getDerivedStateFromError(error) {
    return { error }
  }

  render() {
    if (this.state.error) {
      return (
        <div style={{ padding: 16, fontFamily: 'system-ui, sans-serif' }}>
          <h2 style={{ marginTop: 0 }}>Frontend runtime error</h2>
          <pre style={{ whiteSpace: 'pre-wrap' }}>{String(this.state.error)}</pre>
        </div>
      )
    }
    return this.props.children
  }
}

function renderFatal(message) {
  document.body.innerHTML = `<div style="padding:16px;font-family:system-ui,sans-serif"><h2 style="margin-top:0">Frontend fatal error</h2><pre style="white-space:pre-wrap">${String(message)}</pre></div>`
}

try {
  const rootEl = document.getElementById('root')
  if (!rootEl) {
    renderFatal('Missing #root element in index.html')
  } else {
    const root = createRoot(rootEl)
    import('./App.jsx')
      .then(({ default: App }) => {
        root.render(
          <StrictMode>
            <RootErrorBoundary>
              <App />
            </RootErrorBoundary>
          </StrictMode>,
        )
      })
      .catch((error) => {
        root.render(
          <div style={{ padding: 16, fontFamily: 'system-ui, sans-serif' }}>
            <h2 style={{ marginTop: 0 }}>Frontend startup error</h2>
            <pre style={{ whiteSpace: 'pre-wrap' }}>{String(error)}</pre>
          </div>,
        )
      })
  }
} catch (error) {
  renderFatal(error)
}
