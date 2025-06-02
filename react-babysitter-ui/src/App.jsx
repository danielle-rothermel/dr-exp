import { Routes, Route } from 'react-router-dom'
import JobTable from './components/JobTable.jsx'
import JobDetailView from './components/JobDetailView.jsx'
import './App.css'

/**
 * Root component that defines the navigation for the Babysitter UI.
 *
 * @component
 * @example
 * ```jsx
 * import { BrowserRouter } from 'react-router-dom'
 * import App from './App.jsx'
 *
 * createRoot(el).render(
 *   <BrowserRouter>
 *     <App />
 *   </BrowserRouter>
 * )
 * ```
 */
export default function App() {

  return (
    <div className="p-4">
      <h1 className="text-2xl font-bold mb-4">Babysitter UI</h1>
      <Routes>
        <Route path="/" element={<JobTable />} />
        <Route path="/job/:jobId" element={<JobDetailView />} />
      </Routes>
    </div>
  )
}
