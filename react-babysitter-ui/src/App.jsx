import { Routes, Route } from 'react-router-dom'
import JobTable from './components/JobTable.jsx'
import JobDetailView from './components/JobDetailView.jsx'
import './App.css'

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
