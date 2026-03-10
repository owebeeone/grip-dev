import ReactDOM from 'react-dom/client'
import { GripProvider } from '@owebeeone/grip-react'
import App from './App'
import { viewerGrok } from './viewer_runtime'

ReactDOM.createRoot(document.getElementById('root')!).render(
  <GripProvider grok={viewerGrok} context={viewerGrok.mainPresentationContext}>
    <App />
  </GripProvider>,
)
